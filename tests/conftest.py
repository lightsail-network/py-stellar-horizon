import pytest

from tests.support import FakeHorizon, captured


@pytest.fixture
def anyio_backend() -> str:
    """Run the async tests on asyncio only.

    Older releases of anyio run them on trio as well when no backend is named, and trio
    is not a dependency.
    """
    return "asyncio"


@pytest.fixture
def horizon() -> FakeHorizon:
    """A fake server that knows its root, which a stream reads to start at `now`."""
    fake = FakeHorizon()
    fake.on("/", captured("root.json"))
    return fake
