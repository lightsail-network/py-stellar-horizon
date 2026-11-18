import pytest

from stellar_horizon._stream_policy import (
    FIRST_WAIT,
    MAX_WAIT,
    WORKING_AFTER,
    Attempt,
    StreamPolicy,
    passing_problem,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def policy(give_up_after: float | None = 300) -> tuple[StreamPolicy, Clock]:
    clock = Clock()
    return StreamPolicy(
        give_up_after=give_up_after, clock=clock, jitter=lambda: 1.0
    ), clock


def test_close_from_the_server_waits_its_retry_time() -> None:
    p, clock = policy()
    attempt = Attempt(opened_at=clock.now, closed_by_server=True, server_retry=10)
    assert p.after(attempt) == pytest.approx(0.01)


def test_close_without_retry_waits_a_second() -> None:
    p, clock = policy()
    assert p.after(Attempt(opened_at=clock.now, closed_by_server=True)) == 1.0


@pytest.mark.parametrize(
    "attempt",
    [
        Attempt(opened_at=1000.0, delivered=True),
        Attempt(opened_at=1000.0 - WORKING_AFTER),
    ],
    ids=["delivered", "stayed-open"],
)
def test_a_connection_that_worked_is_not_a_failure(attempt: Attempt) -> None:
    p, _ = policy()
    p.failing_since = 1.0
    assert p.after(attempt) == 1.0
    assert p.failing_since is None
    assert p.next_wait == FIRST_WAIT


def test_failures_wait_longer_each_time() -> None:
    p, clock = policy(give_up_after=None)
    waits: list[float | None] = []
    for _ in range(8):
        waits.append(p.after(Attempt()))
        clock.now += 1
    assert waits == [1, 2, 4, 8, 16, 30, 30, 30]
    assert p.next_wait == MAX_WAIT


def test_a_connection_that_opens_and_dies_is_a_failure() -> None:
    p, clock = policy()
    assert p.after(Attempt(opened_at=clock.now)) == 1
    assert p.failing_since == clock.now


@pytest.mark.parametrize("delivered", [False, True])
def test_a_quiet_connection_is_replaced_at_once(delivered: bool) -> None:  # noqa: FBT001
    # The client ended it by its read timeout. That timeout is as long as
    # `WORKING_AFTER`, so the age of the connection alone could fall just short.
    p, clock = policy()
    p.failing_since = 1.0
    opened_at = clock.now - WORKING_AFTER + 0.01
    attempt = Attempt(opened_at=opened_at, delivered=delivered, timed_out=True)
    assert p.after(attempt) == 0
    assert p.failing_since is None
    assert p.next_wait == FIRST_WAIT


def test_a_timeout_before_the_connection_opens_is_a_failure() -> None:
    # No `open`: the server did not answer at all in the time.
    p, clock = policy()
    assert p.after(Attempt(timed_out=True)) == 1
    assert p.failing_since == clock.now


def test_jitter_shortens_the_wait() -> None:
    p = StreamPolicy(give_up_after=None, clock=Clock(), jitter=lambda: 0.0)
    assert p.after(Attempt()) == 0.5


def test_retry_after_is_respected() -> None:
    p, _ = policy()
    assert p.after(Attempt(retry_after=12)) == 12


def test_gives_up_after_the_time_without_a_working_connection() -> None:
    p, clock = policy(give_up_after=60)
    assert p.after(Attempt()) == 1
    clock.now += 59
    assert p.after(Attempt()) == 1  # what is left before giving up
    clock.now += 1
    assert p.after(Attempt()) is None


def test_a_working_connection_restarts_the_time() -> None:
    p, clock = policy(give_up_after=60)
    p.after(Attempt())
    clock.now += 50
    p.after(Attempt(opened_at=clock.now, delivered=True))
    clock.now += 50
    assert p.after(Attempt()) == 1


def test_give_up_after_must_not_be_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        StreamPolicy(give_up_after=-1)


@pytest.mark.parametrize(
    ("data", "passing"),
    [
        ("problem: rate_limit_exceeded. full details: slow down", True),
        ("problem: timeout. full details: ", True),
        ("problem: still_ingesting. full details: x", True),
        ("Unexpected stream error", True),
        ("problem: not_found. full details: gone", False),
        ("problem: bad_request. full details: x", False),
        ("something else", False),
    ],
)
def test_passing_problems(data: str, passing: bool) -> None:  # noqa: FBT001
    assert passing_problem(data) is passing
