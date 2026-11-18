# pyright: reportPrivateUsage=false
import pytest

from stellar_horizon._async import _stream


@pytest.fixture(autouse=True)
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Note the waits of a stream between its connections, without waiting.

    Every test in this directory gets it, so that none sleeps. A test that looks at
    the waits asks for the list by name.
    """
    waited: list[float] = []

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(_stream, "_sleep", sleep)
    return waited
