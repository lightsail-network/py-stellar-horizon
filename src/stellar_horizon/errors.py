"""The exceptions that this package raises.

Every error that comes from talking to Horizon is a `HorizonError`. Wrong arguments
raise `ValueError` or `TypeError` instead, before anything is sent.

The errors can be pickled and copied, with what they carry, so that a worker process
can hand one to its parent.
"""

import json
import math
from typing import Any, TypeVar, cast

import httpx2
from pydantic import ValidationError

from .models import Problem, TransactionResultCodes

__all__ = [
    "BadRequestError",
    "BeforeHistoryError",
    "HorizonError",
    "InvalidResponseError",
    "NotFoundError",
    "OutcomeUnknownError",
    "PagingError",
    "RateLimitError",
    "ResponseError",
    "ServerError",
    "StreamError",
    "TransactionFailedError",
    "TransportError",
]


_E = TypeVar("_E", bound="HorizonError")


def _rebuild(cls: type[_E], args: tuple[Any, ...], kwargs: dict[str, Any]) -> _E:
    """Build an error again from the arguments that `_reduced` kept."""
    return cls(*args, **kwargs)


def _reduced(error: "HorizonError", *args: Any, **kwargs: Any) -> tuple[Any, ...]:  # noqa: ANN401
    """Return what `__reduce__` gives for an error built from these arguments.

    Pickle and copy rebuild an exception from its message alone by default, which
    fails for a class whose constructor needs more. The last item is what else the
    error holds, such as notes added to it, as the default keeps it too.
    """
    return _rebuild, (type(error), args, kwargs), vars(error)


class HorizonError(Exception):
    """The base class of every error that comes from talking to Horizon."""


class TransportError(HorizonError):
    """No response came that can be used.

    The connection failed, TLS failed, a timeout passed, or the body of the response
    could not be decoded. The httpx2 exception is available as `__cause__`.
    """


class ResponseError(HorizonError):
    """Horizon answered with a status that is not a success.

    That is a 4xx or a 5xx, and also a redirect: the client does not follow
    redirects, so a base URL that redirects, such as `http://` for a server that
    wants `https://`, raises this error.

    Attributes:
        response: The response, already read.
        problem: The decoded problem document, or `None` when the body was not one.
    """

    def __init__(self, response: httpx2.Response, problem: Problem | None) -> None:
        self.response = response
        self.problem = problem
        if problem is not None:
            message = f"HTTP {response.status_code} {problem.short_type}: "
            message += problem.detail or problem.title
        elif response.is_redirect:
            message = f"HTTP {response.status_code}: {_redirect(response)}"
        else:
            message = f"HTTP {response.status_code}"
        super().__init__(message)

    def __reduce__(self) -> tuple[Any, ...]:
        return _reduced(self, self.response, self.problem)

    @property
    def status_code(self) -> int:
        """The HTTP status of the response."""
        return self.response.status_code

    @property
    def type(self) -> str | None:
        """The short problem type, such as `not_found`, or `None` without a problem."""
        return None if self.problem is None else self.problem.short_type

    @property
    def extras(self) -> dict[str, Any]:
        """The `extras` of the problem document; empty when there are none."""
        if self.problem is None or self.problem.extras is None:
            return {}
        return self.problem.extras

    def _extra(self, name: str) -> Any:  # noqa: ANN401
        return self.extras.get(name)


class BadRequestError(ResponseError):
    """Horizon rejected the request, usually because of a parameter: 400."""

    @property
    def invalid_field(self) -> str | None:
        """The parameter that Horizon named, if it named one."""
        value = self._extra("invalid_field")
        return value if isinstance(value, str) else None

    @property
    def reason(self) -> str | None:
        """Why Horizon rejected the parameter, if it said."""
        value = self._extra("reason")
        return value if isinstance(value, str) else None


class NotFoundError(ResponseError):
    """The resource does not exist: 404."""


class BeforeHistoryError(ResponseError):
    """The data asked for is older than the history the server keeps: 410."""


class RateLimitError(ResponseError):
    """Too many requests from this address: 429."""

    @property
    def retry_after(self) -> float | None:
        """The seconds to wait that the server asked for, if it did."""
        return retry_after(self.response)


class TransactionFailedError(ResponseError):
    """The transaction did not succeed: 400 `transaction_failed`.

    It happens in two ways. stellar-core can refuse the transaction before it reaches
    a ledger, for example when its sequence number is not the next one or its fee is
    too low to get in; then nothing was charged, and the same envelope may pass later.
    Or the transaction is in a ledger and failed when it was applied, for example when
    a payment's source lacked the funds; then its fee was charged, its sequence number
    is used, and it cannot succeed any more.

    `result_codes` says why. `transactions.get()` with the hash tells whether the
    transaction is in a ledger.
    """

    @property
    def result_codes(self) -> TransactionResultCodes | None:
        """The result codes of the transaction and of its operations."""
        value = self._extra("result_codes")
        try:
            return TransactionResultCodes.model_validate(value)
        except ValidationError:
            return None

    @property
    def envelope_xdr(self) -> str | None:
        """The envelope that was submitted, as base64 XDR."""
        value = self._extra("envelope_xdr")
        return value if isinstance(value, str) else None

    @property
    def result_xdr(self) -> str | None:
        """The `TransactionResult`, as base64 XDR."""
        value = self._extra("result_xdr")
        return value if isinstance(value, str) else None

    @property
    def diagnostic_events(self) -> list[str]:
        """Diagnostic events of a contract call, as base64 XDR; empty when none."""
        value = self._extra("diagnostic_events")
        if not isinstance(value, list):
            return []
        return [item for item in cast("list[object]", value) if isinstance(item, str)]


class ServerError(ResponseError):
    """Horizon failed or was not able to answer: 5xx."""


class OutcomeUnknownError(HorizonError):
    """A submission may or may not have been accepted.

    The request was sent, but no answer came that says what happened: the connection
    broke or timed out, the response could not be read, or Horizon answered with a 5xx
    such as its own submission timeout. Send the same envelope again, which is safe
    because it is the same transaction, or look the hash up later.

    Attributes:
        envelope_xdr: The envelope that was sent.
        hash: The hash of the transaction, when Horizon gave it.
        response: The response, when there was one.
    """

    def __init__(
        self,
        message: str,
        *,
        envelope_xdr: str,
        hash: str | None = None,  # noqa: A002
        response: httpx2.Response | None = None,
    ) -> None:
        super().__init__(message)
        self.envelope_xdr = envelope_xdr
        self.hash = hash
        self.response = response

    def __reduce__(self) -> tuple[Any, ...]:
        return _reduced(
            self,
            str(self),
            envelope_xdr=self.envelope_xdr,
            hash=self.hash,
            response=self.response,
        )


class InvalidResponseError(HorizonError):
    """A successful response that the models cannot read.

    The pydantic error, or the JSON error, is available as `__cause__`.

    Attributes:
        body: The decoded JSON, or the text when it is not JSON.
        response: The response.
    """

    def __init__(
        self, message: str, *, body: object, response: httpx2.Response
    ) -> None:
        super().__init__(message)
        self.body = body
        self.response = response

    def __reduce__(self) -> tuple[Any, ...]:
        return _reduced(self, str(self), body=self.body, response=self.response)


class StreamError(HorizonError):
    """A stream could not go on.

    Attributes:
        cursor: Where the stream got to: pass it as `cursor=` to continue later.
    """

    def __init__(self, message: str, *, cursor: str | None) -> None:
        super().__init__(message)
        self.cursor = cursor

    def __reduce__(self) -> tuple[Any, ...]:
        return _reduced(self, str(self), cursor=self.cursor)


class PagingError(HorizonError):
    """There is no page to go to, or the link to it cannot be followed."""


_BY_TYPE: dict[str, type[ResponseError]] = {
    "bad_request": BadRequestError,
    "invalid_accounts_params": BadRequestError,
    "invalid_order_book": BadRequestError,
    "transaction_malformed": BadRequestError,
    "transaction_failed": TransactionFailedError,
    "not_found": NotFoundError,
    "before_history": BeforeHistoryError,
    "rate_limit_exceeded": RateLimitError,
}
_BY_STATUS: dict[int, type[ResponseError]] = {
    400: BadRequestError,
    404: NotFoundError,
    410: BeforeHistoryError,
    429: RateLimitError,
}


def problem_of(response: httpx2.Response) -> Problem | None:
    """Return the problem document of a read response, or `None` if it has none."""
    try:
        body = json.loads(response.content)
        return Problem.model_validate(body)
    except (ValueError, RecursionError, ValidationError):
        # A body nested deeper than the interpreter recurses is not a problem either.
        return None


def _redirect(response: httpx2.Response) -> str:
    """Say where a redirect points to, by scheme and host only.

    The path and the query of the address are left out, as in the `repr()` of a
    client: either can hold a key.
    """
    where = ""
    try:
        target = httpx2.URL(response.headers.get("location", ""))
    except httpx2.InvalidURL:
        target = httpx2.URL("")
    if target.host:
        port = f":{target.port}" if target.port else ""
        where = f" to {target.scheme}://{target.host}{port}"
    return f"a redirect{where}, which the client does not follow"


def error_for(response: httpx2.Response) -> ResponseError:
    """Return the exception for a read response whose status is not a success."""
    problem = problem_of(response)
    cls = None if problem is None else _BY_TYPE.get(problem.short_type)
    if cls is None:
        if response.status_code >= 500:  # noqa: PLR2004
            cls = ServerError
        else:
            cls = _BY_STATUS.get(response.status_code, ResponseError)
    return cls(response, problem)


def retry_after(response: httpx2.Response) -> float | None:
    """Return the seconds of a `Retry-After` header, if it has a finite number of them.

    A negative number counts as none.
    """
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None
