"""What a stream does after a connection ends. Nothing here does I/O.

Horizon ends every stream response after some records or some seconds, so connecting
again is the normal path. A connection that worked is never a failure, however it ended;
only not getting a working connection is. The stream gives up when failures have gone
on for a while without one connection that worked.
"""

import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

__all__ = ["Attempt", "StreamPolicy", "passing_problem"]

WORKING_AFTER = 15.0
"""Seconds a connection must stay open to count as working, if nothing else shows it.

The read timeout of a stream is as long, so a quiet connection ends by that timeout at
about this age. It counts as working because it timed out, not by its age: two timers
need not agree to the millisecond.
"""
FIRST_WAIT = 1.0
MAX_WAIT = 30.0
AFTER_WORKING = 1.0
"""Seconds to wait after a connection that worked but did not end with `close`.

There is no wait after one that the client ended by its read timeout.
"""

# Problems that a stream reports in an `error` event and that pass.
_PASSING = frozenset(
    {
        "rate_limit_exceeded",
        "timeout",
        "service_unavailable",
        "still_ingesting",
        "stale_history",
    }
)
_PROBLEM = re.compile(r"problem: ([a-z_]+)\.")


def passing_problem(data: str) -> bool:
    """Tell whether the data of an `error` event reports a problem that passes."""
    if data.strip() == "Unexpected stream error":
        return True
    match = _PROBLEM.match(data)
    return match is not None and match.group(1) in _PASSING


@dataclass(slots=True)
class Attempt:
    """What happened on one connection."""

    opened_at: float | None = None
    """When the server's `open` event arrived, if it did."""
    delivered: bool = False
    """Whether a record was yielded."""
    closed_by_server: bool = False
    """Whether the server ended the connection with a `close` event."""
    timed_out: bool = False
    """Whether the client ended the connection after its read timeout, in silence."""
    server_retry: int | None = None
    """The last `retry` time the server sent, in milliseconds."""
    retry_after: float | None = None
    """The `Retry-After` of an error response, in seconds."""


class StreamPolicy:
    """Decides how long to wait before connecting again, or that it is time to stop."""

    def __init__(
        self,
        *,
        give_up_after: float | None,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        if give_up_after is not None and give_up_after < 0:
            msg = "give_up_after must not be negative"
            raise ValueError(msg)
        self.give_up_after = give_up_after
        self.clock = clock
        self.jitter = jitter
        self.failing_since: float | None = None
        self.next_wait = FIRST_WAIT

    def worked(self, attempt: Attempt) -> bool:
        """Tell whether a connection that has ended worked."""
        if attempt.opened_at is None:
            return False
        return (
            attempt.delivered
            or attempt.closed_by_server
            or attempt.timed_out
            or self.clock() - attempt.opened_at >= WORKING_AFTER
        )

    def reset(self) -> None:
        """Forget the failures, as after a connection that worked."""
        self.failing_since = None
        self.next_wait = FIRST_WAIT

    def after(self, attempt: Attempt) -> float | None:
        """Return the seconds to wait before connecting again, or `None` to give up."""
        if self.worked(attempt):
            self.reset()
            if attempt.timed_out:
                # The client ended a quiet connection itself, and replaces it at once.
                # A wait would only make late the records that come during it, and
                # such connections cannot spin: each one lasts the read timeout.
                return 0.0
            if attempt.closed_by_server and attempt.server_retry is not None:
                return attempt.server_retry / 1000
            return AFTER_WORKING
        now = self.clock()
        if self.failing_since is None:
            self.failing_since = now
        elif (
            self.give_up_after is not None
            and now - self.failing_since >= self.give_up_after
        ):
            return None
        wait = self.next_wait * (0.5 + self.jitter() / 2)
        self.next_wait = min(self.next_wait * 2, MAX_WAIT)
        if attempt.retry_after is not None:
            wait = max(wait, attempt.retry_after)
        if self.give_up_after is not None:
            # Don't sleep past the moment of giving up: one more attempt is due then.
            left = self.failing_since + self.give_up_after - now
            wait = min(wait, max(left, 0.0))
        return wait
