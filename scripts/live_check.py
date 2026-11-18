"""Call every reading method against a live server, and report what the models missed.

Nothing is submitted. Each method is called once with arguments taken from the
server's own answers, every record is checked for fields that the models do not know,
and each stream is read until its first record. The async client is checked on a few
calls as well.

Usage:
    uv run python scripts/live_check.py                       # the test network
    uv run python scripts/live_check.py https://horizon.stellar.org
"""

import argparse
import asyncio
import sys
import time
from collections.abc import Callable, Iterable
from typing import Any, cast

from pydantic import BaseModel

from stellar_horizon import (
    AsyncHorizonClient,
    HorizonClient,
    HorizonError,
    Stream,
)

TESTNET = "https://horizon-testnet.stellar.org"


def unknown_fields(value: object, path: str = "") -> list[str]:
    """Return the paths of the fields, at any depth, that a model did not know."""
    found: list[str] = []
    if isinstance(value, BaseModel):
        found.extend(f"{path}.{name}" for name in value.model_extra or {})
        for name in type(value).model_fields:
            found.extend(unknown_fields(getattr(value, name), f"{path}.{name}"))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(cast("list[object]", value)):
            found.extend(unknown_fields(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in cast("dict[object, object]", value).items():
            found.extend(unknown_fields(item, f"{path}[{key!r}]"))
    return found


def records_of(value: object) -> list[object]:
    """The records of a page, a list or a stream, or a single resource as a list."""
    if isinstance(value, Iterable) and not isinstance(value, BaseModel):
        return list(cast("Iterable[object]", value))
    return [value]


class Checker:
    """Runs the checks and counts what failed."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.count = 0

    def check(self, name: str, call: Callable[[], Any]) -> Any:  # noqa: ANN401
        """Run `call`, report its result, and return it, or `None` if it failed."""
        self.count += 1
        started = time.monotonic()
        try:
            value: Any = call()
        except HorizonError as error:
            self.failures.append(f"{name}: {type(error).__name__}: {error}")
            print(f"FAIL  {name}: {type(error).__name__}: {error}")
            return None
        records = records_of(value)
        unknown = [field for record in records for field in unknown_fields(record)]
        took = time.monotonic() - started
        if unknown:
            self.failures.append(f"{name}: unknown fields {sorted(set(unknown))}")
            print(f"FAIL  {name}: unknown fields {sorted(set(unknown))}")
        else:
            print(f"ok    {name} ({len(records)} records, {took:.1f}s)")
        return value


def first(stream: Stream[Any]) -> list[Any]:
    """Read a stream until its first record, then close it."""
    with stream:
        return [next(stream)]


def check_sync(checker: Checker, base_url: str) -> None:  # noqa: PLR0915
    """Every reading method of the sync client."""
    check = checker.check
    with HorizonClient(base_url, max_retries=2) as client:
        root = check("root", client.root)
        check("fee_stats", client.fee_stats)

        ledgers = check(
            "ledgers.list", lambda: client.ledgers.list(order="desc", limit=3)
        )
        if ledgers:
            check(
                "ledgers.get", lambda: client.ledgers.get(ledgers.records[0].sequence)
            )
            check("page.next", ledgers.next)
            check("page.prev", ledgers.prev)
        check("ledgers.stream (now)", lambda: first(client.ledgers.stream()))

        transactions = check(
            "transactions.list",
            lambda: client.transactions.list(
                order="desc", limit=10, include_failed=True
            ),
        )
        if transactions:
            latest = transactions.records[0]
            check("transactions.get", lambda: client.transactions.get(latest.hash))
            check(
                "transactions.list (ledger)",
                lambda: client.transactions.list(ledger=latest.ledger),
            )
            account_id = latest.source_account
            check("accounts.get", lambda: client.accounts.get(account_id))
            check(
                "accounts.list (signer)",
                lambda: client.accounts.list(signer=account_id, limit=2),
            )
            check(
                "accounts.requires_memo",
                lambda: [client.accounts.requires_memo(account_id)],
            )
            check(
                "transactions.list (account)",
                lambda: client.transactions.list(account=account_id, limit=5),
            )
            check(
                "operations.list (transaction, joined)",
                lambda: client.operations.list(
                    transaction=latest.hash, join_transactions=True
                ),
            )
            check(
                "effects.list (transaction)",
                lambda: client.effects.list(transaction=latest.hash),
            )
            check(
                "payments.list (account)",
                lambda: client.payments.list(account=account_id, limit=5),
            )
        check(
            "transactions.stream",
            lambda: first(client.transactions.stream(cursor=None)),
        )

        operations = check(
            "operations.list", lambda: client.operations.list(order="desc", limit=50)
        )
        if operations:
            operation_id = operations.records[0].id
            check("operations.get", lambda: client.operations.get(operation_id))
            check(
                "effects.list (operation)",
                lambda: client.effects.list(operation=operation_id),
            )
        check("operations.stream", lambda: first(client.operations.stream(cursor=None)))
        check("payments.list", lambda: client.payments.list(order="desc", limit=50))
        check("payments.stream", lambda: first(client.payments.stream(cursor=None)))
        check("effects.list", lambda: client.effects.list(order="desc", limit=100))
        check("effects.stream", lambda: first(client.effects.stream(cursor=None)))

        offers = check(
            "offers.list", lambda: client.offers.list(order="desc", limit=10)
        )
        if offers and offers.records:
            offer = offers.records[0]
            check("offers.get", lambda: client.offers.get(offer.id))
            check(
                "offers.stream (seller)",
                lambda: first(client.offers.stream(seller=offer.seller)),
            )
            check(
                "order_book.get",
                lambda: client.order_book.get(offer.selling, offer.buying, limit=5),
            )
            check(
                "order_book.stream",
                lambda: first(client.order_book.stream(offer.selling, offer.buying)),
            )

        trades = check(
            "trades.list", lambda: client.trades.list(order="desc", limit=10)
        )
        check("trades.stream", lambda: first(client.trades.stream(cursor=None)))
        if trades and trades.records:
            trade = trades.records[0]
            base = (
                trade.base_asset_code
                and f"{trade.base_asset_code}:{trade.base_asset_issuer}"
            )
            counter = (
                trade.counter_asset_code
                and f"{trade.counter_asset_code}:{trade.counter_asset_issuer}"
            )
            base, counter = base or "native", counter or "native"
            check(
                "trades.list (pair)",
                lambda: client.trades.list(base_asset=base, counter_asset=counter),
            )
            aggregations = check(
                "trade_aggregations.list",
                lambda: client.trade_aggregations.list(
                    base, counter, 3_600_000, order="desc", limit=5
                ),
            )
            if aggregations:
                check("trade_aggregations next", aggregations.next)
            check(
                "paths.strict_send",
                lambda: client.paths.strict_send(
                    source_asset=base, source_amount="1", destination_assets=[counter]
                ),
            )
            check(
                "paths.strict_receive",
                lambda: client.paths.strict_receive(
                    destination_asset=counter,
                    destination_amount="1",
                    source_assets=[base],
                ),
            )

        check("assets.list", lambda: client.assets.list(limit=20))
        balances = check(
            "claimable_balances.list",
            lambda: client.claimable_balances.list(order="desc", limit=10),
        )
        if balances and balances.records:
            balance_id = balances.records[0].id
            check(
                "claimable_balances.get",
                lambda: client.claimable_balances.get(balance_id),
            )
            check(
                "operations.list (claimable balance)",
                lambda: client.operations.list(claimable_balance=balance_id),
            )
        pools = check(
            "liquidity_pools.list",
            lambda: client.liquidity_pools.list(order="desc", limit=10),
        )
        if pools and pools.records:
            pool_id = pools.records[0].id
            check("liquidity_pools.get", lambda: client.liquidity_pools.get(pool_id))
            check(
                "trades.list (pool)",
                lambda: client.trades.list(liquidity_pool=pool_id, limit=5),
            )
            check(
                "effects.list (pool)",
                lambda: client.effects.list(liquidity_pool=pool_id, limit=5),
            )
        if root:
            check(
                "request",
                lambda: [client.request("GET", "/fee_stats").json()["last_ledger"]],
            )


async def check_async(checker: Checker, base_url: str) -> None:
    """A few calls of the async client."""
    async with AsyncHorizonClient(base_url) as client:
        root = await client.root()
        checker.check("async root", lambda: root)
        page = await client.transactions.list(order="desc", limit=5)
        checker.check("async transactions.list", lambda: page)
        following = await page.next()
        checker.check("async page.next", lambda: following)
        async with client.ledgers.stream() as stream:
            ledger = await anext(stream)
        checker.check("async ledgers.stream (now)", lambda: [ledger])


def main() -> int:
    """Run the checks, and fail if any did."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default=TESTNET)
    args = parser.parse_args()
    checker = Checker()
    check_sync(checker, args.base_url)
    asyncio.run(check_async(checker, args.base_url))
    print(f"\n{checker.count} checks, {len(checker.failures)} failed")
    for failure in checker.failures:
        print(f"  {failure}")
    return 1 if checker.failures else 0


if __name__ == "__main__":
    sys.exit(main())
