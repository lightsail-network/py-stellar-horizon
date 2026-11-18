import httpx2
import pytest

from stellar_horizon._retry_policy import (
    BUDGET,
    RetryPolicy,
    check_max_retries,
)
from stellar_horizon.errors import (
    HorizonError,
    InvalidResponseError,
    TransportError,
    error_for,
)
from tests.support import json_response, problem


def answer(status: int, **headers: str) -> HorizonError:
    return error_for(json_response(status, problem("x", status), **headers))


def policy(max_retries: int = 10) -> RetryPolicy:
    # No jitter: each wait is the lower end of its range.
    return RetryPolicy(max_retries, jitter=lambda: 0.0)


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_passing_statuses_are_tried_again(status: int) -> None:
    assert policy().after(answer(status)) == 0.25


@pytest.mark.parametrize("status", [400, 404, 410, 500])
def test_other_statuses_are_not(status: int) -> None:
    assert policy().after(answer(status)) is None


def test_transport_errors_are_tried_again() -> None:
    assert policy().after(TransportError("reset")) is not None


def test_unreadable_responses_are_not() -> None:
    error = InvalidResponseError("bad", body="", response=httpx2.Response(200))
    assert policy().after(error) is None


def test_waits_double_with_jitter() -> None:
    plain = policy()
    assert [plain.after(answer(503)) for _ in range(4)] == [0.25, 0.5, 1.0, 2.0]
    jittered = RetryPolicy(3, jitter=lambda: 1.0)
    assert jittered.after(answer(503)) == 0.5


def test_retries_are_counted() -> None:
    limited = policy(2)
    assert limited.after(answer(503)) is not None
    assert limited.after(answer(503)) is not None
    assert limited.after(answer(503)) is None
    assert policy(0).after(answer(503)) is None


def test_retry_after_is_a_floor() -> None:
    assert policy().after(answer(429, **{"Retry-After": "7"})) == 7
    assert policy().after(answer(503, **{"Retry-After": "0"})) == 0.25


def test_waits_stay_within_the_budget() -> None:
    assert policy().after(answer(429, **{"Retry-After": str(BUDGET + 1)})) is None
    spent = policy()
    assert spent.after(answer(429, **{"Retry-After": str(BUDGET - 0.25)})) is not None
    # The next wait, half a second without jitter, would go past the budget.
    assert spent.after(answer(503)) is None


@pytest.mark.parametrize(
    ("value", "error"),
    [(-1, ValueError), (True, TypeError), (1.0, TypeError), ("2", TypeError)],
)
def test_max_retries_is_checked(value: object, error: type[Exception]) -> None:
    with pytest.raises(error, match="max_retries"):
        check_max_retries(value)  # type: ignore[arg-type]
    assert check_max_retries(3) == 3
