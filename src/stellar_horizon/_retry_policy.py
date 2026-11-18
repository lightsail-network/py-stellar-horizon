"""When a single `GET` is tried again. Nothing here does I/O.

The client's `max_retries` says how often, twice by default. A `POST` is never tried
again, because the server may have acted on it; streams have their own rule.
"""

import random
from collections.abc import Callable

from .errors import HorizonError, ResponseError, TransportError, retry_after

__all__ = [
    "BUDGET",
    "FIRST_WAIT",
    "RETRIED_STATUSES",
    "RetryPolicy",
    "check_max_retries",
]

FIRST_WAIT = 0.5
"""Seconds before the first retry, before jitter; each retry doubles it."""
BUDGET = 60.0
"""The most seconds that the waits of one call may add up to."""
RETRIED_STATUSES = frozenset({429, 502, 503, 504})
"""Statuses that say the server or a proxy may answer if asked again."""


def check_max_retries(max_retries: int) -> int:
    """Return `max_retries` if it is a whole number of retries, or raise."""
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"max_retries must be an int, not {type(max_retries).__name__}"
        raise TypeError(msg)
    if max_retries < 0:
        msg = "max_retries must not be negative"
        raise ValueError(msg)
    return max_retries


class RetryPolicy:
    """Decides, for one call, whether to try a failed `GET` again, and when."""

    def __init__(
        self,
        max_retries: int,
        *,
        jitter: Callable[[], float] = random.random,
        budget: float = BUDGET,
    ) -> None:
        self.retries_left = max_retries
        self.jitter = jitter
        self.budget = budget
        self.next_wait = FIRST_WAIT
        self.waited = 0.0

    def after(self, error: HorizonError) -> float | None:
        """Return the seconds to wait before trying again, or `None` to raise `error`.

        A transport error and the statuses 429, 502, 503 and 504 are tried again,
        after a wait no shorter than the server's `Retry-After`. Nothing else is: not a
        404 or another 4xx, nor a response that cannot be read.
        """
        if self.retries_left <= 0:
            return None
        if isinstance(error, ResponseError):
            if error.status_code not in RETRIED_STATUSES:
                return None
        elif not isinstance(error, TransportError):
            return None
        wait = self.next_wait * (0.5 + self.jitter() / 2)
        if isinstance(error, ResponseError):
            asked = retry_after(error.response)
            if asked is not None:
                wait = max(wait, asked)
        if self.waited + wait > self.budget:
            return None
        self.retries_left -= 1
        self.next_wait *= 2
        self.waited += wait
        return wait
