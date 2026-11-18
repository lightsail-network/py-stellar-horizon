# Generated from _async/conftest.py by scripts/unasync.py. Do not edit.
# pyright: reportPrivateUsage=false
import pytest

from stellar_horizon._sync import _stream


@pytest.fixture(autouse=True)
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Note the waits of a stream between its connections, without waiting.

    Every test in this directory gets it, so that none sleeps. A test that looks at
    the waits asks for the list by name.
    """
    waited: list[float] = []

    def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(_stream, "_sleep", sleep)
    return waited
