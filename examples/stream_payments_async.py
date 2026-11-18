"""Print the payments of the network as they happen, with the async client."""

import anyio

from stellar_horizon import AsyncHorizonClient


async def main() -> None:
    """Stream payments until interrupted."""
    async with (
        AsyncHorizonClient("https://horizon.stellar.org") as client,
        client.payments.stream() as stream,
    ):
        async for payment in stream:
            print(payment.type, payment.id, payment.created_at)


anyio.run(main)
