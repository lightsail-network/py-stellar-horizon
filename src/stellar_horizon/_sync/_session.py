# Generated from _async/_session.py by scripts/unasync.py. Do not edit.
"""The connection to one server, which the client, its pages and streams share."""

import logging
import time
from collections.abc import Mapping
from typing import TypeVar

import httpx2

from stellar_horizon._reading import read_object, read_page, read_result
from stellar_horizon._requests import Request
from stellar_horizon._retry_policy import RetryPolicy
from stellar_horizon.errors import (
    InvalidResponseError,
    OutcomeUnknownError,
    ResponseError,
    TransportError,
    error_for,
)

from ._page import Page
from ._stream import READ_TIMEOUT, Stream, StreamKind

__all__ = ["Session"]

T = TypeVar("T")

_LOGGER = logging.getLogger("stellar_horizon")
_sleep = time.sleep

# Errors raised before any byte of the request left: nothing was sent.
_NOT_SENT = (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout)


class Session:
    """Sends requests to one server and reads the responses."""

    def __init__(
        self,
        http: httpx2.Client,
        *,
        base_url: httpx2.URL,
        timeout: httpx2.Timeout,
        headers: httpx2.Headers,
        max_retries: int,
    ) -> None:
        self.http: httpx2.Client = http
        self.max_retries: int = max_retries
        """How often a single `GET` is tried again; never a `POST` or a stream."""
        self.base_url: httpx2.URL = base_url
        self.timeout: httpx2.Timeout = timeout
        self.stream_timeout: httpx2.Timeout = httpx2.Timeout(
            connect=timeout.connect,
            read=READ_TIMEOUT,
            write=timeout.write,
            pool=timeout.pool,
        )
        self.headers: httpx2.Headers = headers
        """Sent with every request; they win over the HTTP client's own."""
        self.base_params: tuple[tuple[str, str], ...] = tuple(
            base_url.params.multi_items()
        )
        """Query parameters of the base URL, which every request carries."""

    def params(
        self, params: Mapping[str, str] | tuple[tuple[str, str], ...] | None
    ) -> tuple[tuple[str, str], ...]:
        """Add the base URL's parameters to `params`, replacing any of the same name.

        A server can echo a key that was sent as a parameter in the links it returns;
        the base URL's value wins, and the key is sent once.
        """
        pairs = (
            list(params.items()) if isinstance(params, Mapping) else list(params or ())
        )
        names = {name for name, _ in self.base_params}
        kept = tuple(pair for pair in pairs if pair[0] not in names)
        return kept + self.base_params

    def with_headers(self, extra: Mapping[str, str] | None) -> httpx2.Headers:
        """The session's headers, with `extra` winning over them by name."""
        merged = httpx2.Headers(self.headers)
        if extra:
            merged.update(extra)
        return merged

    def url(self, endpoint: str) -> httpx2.URL:
        prefix = self.base_url.raw_path.split(b"?", 1)[0].rstrip(b"/")
        return self.base_url.copy_with(raw_path=prefix + endpoint.encode("ascii"))

    def send(
        self,
        method: str,
        url: httpx2.URL,
        *,
        params: Mapping[str, str] | tuple[tuple[str, str], ...] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        try:
            response = self.http.request(
                method,
                url,
                params=self.params(params) or None,
                data=data or None,
                headers=self.with_headers(headers),
                timeout=self.timeout,
                follow_redirects=False,
            )
        except httpx2.RequestError as error:
            # Not only `httpx2.TransportError`: a body that cannot be decoded, such
            # as broken gzip, is a `RequestError` that is not one.
            raise TransportError(str(error) or type(error).__name__) from error
        if not response.is_success:
            # A redirect too: it is not followed, and its body is not a resource.
            raise error_for(response)
        return response

    def fetch(self, request: Request[T]) -> httpx2.Response:
        """Send a `GET`, and try it again as `max_retries` allows."""
        policy = RetryPolicy(self.max_retries)
        while True:
            try:
                return self.send(
                    request.method, self.url(request.endpoint), params=request.params
                )
            except (TransportError, ResponseError) as error:
                wait = policy.after(error)
                if wait is None:
                    raise
                _LOGGER.warning(
                    "GET %s failed (%s); trying again in %.1f seconds",
                    request.endpoint,
                    error,
                    wait,
                )
                _sleep(wait)

    def get(self, request: Request[T]) -> T:
        response = self.fetch(request)
        return read_object(request.adapter, response)

    def page(self, request: Request[T]) -> Page[T]:
        response = self.fetch(request)
        records, links = read_page(request.adapter, response)
        return Page(self, request, records, links)

    def records(self, request: Request[T]) -> list[T]:
        """Fetch the records of a body that has no links to other pages."""
        response = self.fetch(request)
        records, _ = read_page(request.adapter, response)
        return records

    def stream(
        self,
        request: Request[T],
        *,
        kind: StreamKind,
        cursor: str | int | None,
        give_up_after: float | None,
    ) -> Stream[T]:
        return Stream(
            self, request, kind=kind, cursor=cursor, give_up_after=give_up_after
        )

    def submit(self, request: Request[T], *, any_status: bool = False) -> T:
        """Send a submission, and tell a refusal from an outcome that is not known.

        With `any_status`, a body that reads as a result is returned whatever the
        status of the response: `/transactions_async` answers with 4xx and 5xx results.
        """
        envelope = dict(request.form)["tx"]
        try:
            response = self.http.request(
                request.method,
                self.url(request.endpoint),
                params=self.params(()) or None,
                data=dict(request.form),
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=False,
            )
        except _NOT_SENT as error:
            raise TransportError(str(error) or type(error).__name__) from error
        except httpx2.RequestError as error:
            # Every other failure of the request, an answer that cannot be decoded
            # included: the server may have acted on what it was sent.
            msg = f"no answer to the submission: {error or type(error).__name__}"
            raise OutcomeUnknownError(msg, envelope_xdr=envelope) from error
        if any_status and response.is_error:
            result = read_result(request.adapter, response)
            if result is not None:
                return result
        if not response.is_success:
            # A redirect is a refusal: whoever sent it did not take the submission.
            refused = error_for(response)
            if response.status_code >= 500 and refused.type != "stale_history":  # noqa: PLR2004
                hash_ = refused.extras.get("hash")
                raise OutcomeUnknownError(
                    str(refused),
                    envelope_xdr=envelope,
                    hash=hash_ if isinstance(hash_, str) else None,
                    response=response,
                ) from refused
            raise refused
        try:
            return read_object(request.adapter, response)
        except InvalidResponseError as error:
            msg = f"the answer to the submission cannot be read: {error}"
            raise OutcomeUnknownError(
                msg, envelope_xdr=envelope, response=response
            ) from error
