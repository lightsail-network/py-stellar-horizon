"""Cancelling an async stream, which only the async client can be."""

import anyio
import pytest

from stellar_horizon import AsyncHorizonClient
from tests.local_server import Connection, LocalHorizon
from tests.support import OPEN

pytestmark = pytest.mark.anyio


async def test_cancelling_a_read_releases_the_connection() -> None:
    def silent(connection: Connection) -> None:
        connection.send(OPEN)
        connection.wait_until_released()

    with LocalHorizon(silent) as local:
        async with AsyncHorizonClient(local.url) as client:
            stream = client.payments.stream(cursor="1")
            with anyio.move_on_after(0.2) as scope:
                await anext(stream)
            assert scope.cancelled_caught
            assert local.released.wait(5)
            # The stream ended with the cancellation.
            with pytest.raises(StopAsyncIteration):
                await anext(stream)
    assert local.failures == []
