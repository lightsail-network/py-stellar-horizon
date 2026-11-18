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
            closed = f"{payment.created_at:%H:%M:%S}"
            print(f"{closed} {payment.type} in {payment.transaction_hash}")


anyio.run(main)
