# Generated from _async/_stream.py by scripts/unasync.py. Do not edit.
"""Streams: new records as Horizon ingests them."""

import logging
import time
from collections.abc import Generator
from contextlib import closing
from typing import TYPE_CHECKING, Any, Generic, Literal, Self, TypeVar

import httpx2

from stellar_horizon import _requests
from stellar_horizon._reading import read_object, read_record
from stellar_horizon._requests import Request
from stellar_horizon._stream_policy import Attempt, StreamPolicy, passing_problem
from stellar_horizon.errors import (
    HorizonError,
    ResponseError,
    StreamError,
    TransportError,
    error_for,
    retry_after,
)

if TYPE_CHECKING:
    from ._session import Session

__all__ = ["Stream", "StreamKind"]

T = TypeVar("T")
StreamKind = Literal["records", "object"]
"""What a stream yields: records, each after the cursor of the last, or one object."""

STREAM_LIMIT = "200"
"""Records per connection: the most the server allows."""
READ_TIMEOUT = 15.0
"""Seconds of silence after which a stream connection is taken for dead.

Horizon sends nothing between `open` and `close` while it has no records, and ends a
response only after its `--connection-timeout`, 55 seconds by default. So a quiet
connection is usually ended here first. That is no failure: the connection opened and
stayed open, so the stream connects again at once, from its cursor, and loses nothing.
The time also covers the wait for `open`, which Horizon sends after its first query.
"""
NOW_TRANSACTION_AND_OPERATION = 0xFFFFFFFF

_LOGGER = logging.getLogger("stellar_horizon")
_sleep = time.sleep


class Stream(Generic[T]):
    """New records as Horizon ingests them, across as many connections as it takes.

    Use it as a context manager and iterate it. `cursor` is the place to continue from
    later. A connection that ends is replaced at once; only failing to get a working
    connection for `give_up_after` seconds raises `StreamError`.

    A cursor older than the history the server keeps is not an error: the server starts
    at the oldest ledger it has, without saying so, and the records in between are
    missed. `client.root().history_elder_ledger` says where its history starts.

    An empty cursor, `""`, is not an error either. Horizon reads it as no cursor, so
    the stream starts at the oldest history the server keeps, as with `None`; the
    client sends it as it is.
    """

    def __init__(
        self,
        session: "Session",
        request: Request[T],
        *,
        kind: StreamKind,
        cursor: str | int | None,
        give_up_after: float | None,
    ) -> None:
        self._session = session
        self._request = request
        self._kind = kind
        self._wants_now = cursor == "now"
        self._cursor = None if cursor is None or self._wants_now else str(cursor)
        self._policy = StreamPolicy(give_up_after=give_up_after)
        self._records: Generator[T, None, None] | None = None
        self._last: Any = None
        self._closed = False

    @property
    def cursor(self) -> str | None:
        """Where the stream is: the starting cursor, then the token of the last record.

        `None` for a stream that starts at the oldest history, until a record arrives,
        and always for a stream of one object.
        """
        return self._cursor

    def __enter__(self) -> Self:
        if not self._closed:
            self._start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> T:
        if self._closed:
            raise StopIteration
        if self._records is None:
            self._start()
            self._records = self._run()
        return next(self._records)

    def close(self) -> None:
        """Stop the stream and release its connection; it yields nothing more."""
        if self._records is not None:
            self._records.close()
        self._closed = True

    def _start(self) -> None:
        """Turn `now` into a cursor, before the first connection.

        The root is read under the rule of the connections: a failure that passes is
        waited out, until `give_up_after`. `now` counts as resolved only once the
        cursor is known, so a stream whose start failed tries again when it is read
        again, instead of connecting without a cursor, which would start at the oldest
        history the server keeps.
        """
        if not self._wants_now:
            return
        request = _requests.root()
        while True:
            attempt = Attempt()
            try:
                response = self._session.send(
                    request.method, self._session.url(request.endpoint)
                )
            except TransportError as error:
                failure: HorizonError = error
            except ResponseError as error:
                if not _passing(error):
                    raise
                attempt.retry_after = retry_after(error.response)
                failure = error
            else:
                root = read_object(request.adapter, response)
                ledger = root.history_latest_ledger
                self._cursor = str(ledger << 32 | NOW_TRANSACTION_AND_OPERATION)
                self._wants_now = False
                return
            self._wait_after(attempt, failure)

    def _params(self) -> tuple[tuple[str, str], ...]:
        request = self._request
        if self._kind != "object":
            request = request.with_param("cursor", self._cursor).with_param(
                "limit", STREAM_LIMIT
            )
        return request.params

    def _run(self) -> Generator[T, None, None]:
        while True:
            attempt = Attempt()
            failure: BaseException | None = None
            try:
                with closing(self._connect(attempt)) as records:
                    for record in records:
                        yield record
            except _Passing as error:
                failure = error.__cause__
            except httpx2.ReadTimeout as error:
                # Nothing came for `READ_TIMEOUT`. After `open` that is what a quiet
                # connection looks like: the policy takes it for one that worked, and
                # asks for no wait before the next.
                attempt.timed_out = True
                failure = error
            except httpx2.RequestError as error:
                # A connection that broke, or a body that cannot be decoded.
                failure = error
            if self._policy.worked(attempt):
                failure = None
            elif failure is None:
                failure = StreamError(
                    "the connection ended before it delivered anything",
                    cursor=self._cursor,
                )
            self._wait_after(attempt, failure)

    def _wait_after(self, attempt: Attempt, failure: BaseException | None) -> None:
        """Wait as the policy says after an attempt, or raise if it is time to stop."""
        wait = self._policy.after(attempt)
        if wait is None:
            msg = (
                f"no working connection for {self._policy.give_up_after} seconds; "
                f"the last error was: {_describe(failure)}"
            )
            raise StreamError(msg, cursor=self._cursor) from failure
        if failure is not None:
            _LOGGER.warning(
                "stream of %s failed (%s); connecting again in %.1f seconds",
                self._request.endpoint,
                _describe(failure),
                wait,
            )
        _sleep(wait)

    def _connect(self, attempt: Attempt) -> Generator[T, None, None]:
        """Yield the records of one connection, and note in `attempt` how it went."""
        session = self._session
        with session.http.sse(
            session.url(self._request.endpoint),
            params=session.params(self._params()),
            headers=session.headers,
            timeout=session.stream_timeout,
            max_event_size=None,
        ) as source:
            response = source.response
            if not response.is_success:
                response.read()
                error = error_for(response)
                if not _passing(error):
                    raise error
                attempt.retry_after = retry_after(response)
                raise _Passing from error
            for event in source:
                record = self._read(event, attempt, response)
                if attempt.closed_by_server:
                    return
                if record is not None:
                    yield record

    def _read(
        self, event: httpx2.ServerSentEvent, attempt: Attempt, response: httpx2.Response
    ) -> T | None:
        """Note what an event says, and return its record if it brings a new one."""
        if event.retry is not None:
            attempt.server_retry = event.retry
        if event.event == "open":
            attempt.opened_at = self._policy.clock()
        elif event.event == "close":
            attempt.closed_by_server = True
        elif event.event == "error":
            if not passing_problem(event.data):
                msg = f"the stream reported: {event.data}"
                raise StreamError(msg, cursor=self._cursor)
            raise _Passing from StreamError(event.data, cursor=self._cursor)
        elif event.event == "message":
            record = read_record(self._request.adapter, event.data, response)
            attempt.delivered = True
            if self._kind == "object":
                if record == self._last:
                    return None
                self._last = record
            else:
                self._cursor = str(record.paging_token)  # type: ignore[attr-defined]
            return record
        return None


class _Passing(Exception):  # noqa: N818
    """A connection failed in a way that passes; the cause says how."""


def _passing(error: ResponseError) -> bool:
    return error.status_code == 429 or error.status_code >= 500  # noqa: PLR2004


def _describe(error: BaseException | None) -> str:
    """The message of an error, or its class when it has none, as timeouts often do."""
    return str(error) or type(error).__name__
