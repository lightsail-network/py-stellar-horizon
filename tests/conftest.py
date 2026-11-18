import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run the async tests on asyncio only.

    Older releases of anyio run them on trio as well when no backend is named, and trio
    is not a dependency.
    """
    return "asyncio"
