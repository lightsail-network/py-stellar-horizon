"""Each resource against the responses captured for it.

Every call is made with the arguments that give the request a fixture was captured
with, and the test checks that the request matches it. Streams of records that no
fixture holds are made of captured records, framed as Horizon frames them.
"""

import json
from typing import Any

import httpx2
import pytest

from stellar_horizon import PagingError
from stellar_horizon.models import (
    AccountCreditedEffect,
    AssetStat,
    ClaimableBalance,
    Ledger,
    LiquidityPool,
    Offer,
    Operation,
    Path,
    PaymentOperation,
    Trade,
    TradeAggregation,
    Transaction,
)
from tests._async.clients import client_for
from tests.support import (
    CLOSE,
    OPEN,
    FakeHorizon,
    captured,
    json_response,
    load,
    manifest,
    records,
    sse,
)

pytestmark = pytest.mark.anyio

USDC = "USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"


def serve(horizon: FakeHorizon, name: str) -> httpx2.URL:
    """Answer the path that `name` was captured from with it; return that URL."""
    url = httpx2.URL(manifest()[name]["url"])
    horizon.on(url.raw_path.split(b"?", 1)[0].decode("ascii"), captured(name))
    return url


def assert_sent(horizon: FakeHorizon, url: httpx2.URL) -> None:
    """The last request asked for what `url` asks for, parameters in any order."""
    sent = horizon.requests[-1].url
    assert sent.raw_path.split(b"?", 1)[0] == url.raw_path.split(b"?", 1)[0]
    assert sorted(sent.params.multi_items()) == sorted(url.params.multi_items())


def events(*bodies: dict[str, Any]) -> list[str]:
    return [f"id: {body['paging_token']}\ndata: {json.dumps(body)}" for body in bodies]


async def test_fee_stats(horizon: FakeHorizon) -> None:
    url = serve(horizon, "fee_stats.json")
    async with client_for(horizon) as client:
        stats = await client.fee_stats()
    assert_sent(horizon, url)
    assert stats.last_ledger_base_fee == int(
        load("fee_stats.json")["last_ledger_base_fee"]
    )


async def test_ledgers(horizon: FakeHorizon) -> None:
    one = serve(horizon, "ledger.json")
    page_url = serve(horizon, "ledgers.json")
    sequence = load("ledger.json")["sequence"]
    async with client_for(horizon) as client:
        ledger = await client.ledgers.get(sequence)
        assert_sent(horizon, one)
        page = await client.ledgers.list(order="desc", limit=5)
        assert_sent(horizon, page_url)
    assert ledger.sequence == sequence
    assert all(isinstance(record, Ledger) for record in page)


async def test_ledger_stream(horizon: FakeHorizon) -> None:
    horizon.on("/ledgers", sse(OPEN, *events(*records("ledgers.json")[:2]), CLOSE))
    async with (
        client_for(horizon) as client,
        client.ledgers.stream(cursor="5") as stream,
    ):
        ledger = await anext(stream)
    assert ledger.sequence == records("ledgers.json")[0]["sequence"]
    assert horizon.requests[0].url.params["cursor"] == "5"


async def test_operations(horizon: FakeHorizon) -> None:
    one = serve(horizon, "operations/payment.json")
    page_url = serve(horizon, "operations.json")
    operation_id = load("operations/payment.json")["id"]
    async with client_for(horizon) as client:
        operation = await client.operations.get(operation_id)
        assert_sent(horizon, one)
        await client.operations.get(operation_id, join_transactions=True)
        assert horizon.requests[-1].url.params["join"] == "transactions"
        page = await client.operations.list(order="desc", limit=50)
        assert_sent(horizon, page_url)
    assert isinstance(operation, PaymentOperation)
    assert len(page) == len(records("operations.json"))


async def test_operation_stream(horizon: FakeHorizon) -> None:
    record = load("operations/payment.json")
    account = record["source_account"]
    horizon.on(f"/accounts/{account}/operations", sse(OPEN, *events(record), CLOSE))
    async with (
        client_for(horizon) as client,
        client.operations.stream(account=account, include_failed=True) as stream,
    ):
        operation: Operation = await anext(stream)
    assert operation.id == record["id"]
    assert horizon.requests[-1].url.params["include_failed"] == "true"


async def test_transaction_stream(horizon: FakeHorizon) -> None:
    record = records("transactions.json")[0]
    horizon.on(f"/ledgers/{record['ledger']}/transactions", sse(OPEN, *events(record)))
    async with (
        client_for(horizon) as client,
        client.transactions.stream(ledger=record["ledger"], cursor=None) as stream,
    ):
        transaction: Transaction = await anext(stream)
    assert transaction.hash == record["hash"]


async def test_effects(horizon: FakeHorizon) -> None:
    name = "effects/account_removed.json"
    url = serve(horizon, name)
    operation_id = url.path.split("/")[2]
    async with client_for(horizon) as client:
        page = await client.effects.list(
            operation=operation_id, order="asc", limit=1, cursor=url.params["cursor"]
        )
    assert_sent(horizon, url)
    assert page.records[0].type == "account_removed"


async def test_effect_stream(horizon: FakeHorizon) -> None:
    record = records("effects/account_credited.json")[0]
    horizon.on(f"/accounts/{record['account']}/effects", sse(OPEN, *events(record)))
    async with (
        client_for(horizon) as client,
        client.effects.stream(account=record["account"]) as stream,
    ):
        effect = await anext(stream)
    assert isinstance(effect, AccountCreditedEffect)
    assert stream.cursor == record["paging_token"]


async def test_offers(horizon: FakeHorizon) -> None:
    one = serve(horizon, "offer.json")
    page_url = serve(horizon, "offers.json")
    async with client_for(horizon) as client:
        offer = await client.offers.get(load("offer.json")["id"])
        assert_sent(horizon, one)
        page = await client.offers.list(order="desc", limit=10)
        assert_sent(horizon, page_url)
    assert offer.id == load("offer.json")["id"]
    assert all(isinstance(record, Offer) for record in page)


async def test_offer_stream(horizon: FakeHorizon) -> None:
    url = serve(horizon, "streams/offers.sse")
    seller = url.path.split("/")[2]
    async with (
        client_for(horizon) as client,
        client.offers.stream(seller=seller) as stream,
    ):
        assert stream.cursor is None
        offer = await anext(stream)
        assert stream.cursor == offer.paging_token
    assert offer.seller == seller
    # The paging of a stream of records, without a cursor at the start.
    assert dict(horizon.requests[0].url.params) == {"limit": "200"}
    assert horizon.paths() == [url.path]


async def test_offer_stream_refuses_now(horizon: FakeHorizon) -> None:
    # Checked on the test network: with `now`, Horizon sends neither the offers that
    # are open nor those created later.
    async with client_for(horizon) as client:
        with pytest.raises(ValueError, match="offer ID"):
            client.offers.stream(seller="GS", cursor="now")
    assert horizon.requests == []


async def test_trades(horizon: FakeHorizon) -> None:
    url = serve(horizon, "trades.json")
    async with client_for(horizon) as client:
        page = await client.trades.list(order="desc", limit=10)
        assert_sent(horizon, url)
        pools = await client.trades.list(
            trade_type="liquidity_pool", order="desc", limit=5
        )
    assert all(isinstance(record, Trade) for record in [*page, *pools])
    assert horizon.requests[-1].url.params["trade_type"] == "liquidity_pool"


async def test_trade_stream(horizon: FakeHorizon) -> None:
    record = records("trades.json")[0]
    horizon.on("/trades", sse(OPEN, *events(record)))
    async with (
        client_for(horizon) as client,
        client.trades.stream(base_asset=USDC, counter_asset="native") as stream,
    ):
        trade = await anext(stream)
    assert trade.id == record["id"]
    assert horizon.requests[-1].url.params["base_asset_code"] == "USDC"


async def test_trade_aggregations(horizon: FakeHorizon) -> None:
    url = serve(horizon, "trade_aggregations.json")
    async with client_for(horizon) as client:
        page = await client.trade_aggregations.list(
            "native", USDC, 3_600_000, order="desc", limit=5
        )
        assert_sent(horizon, url)
        await page.next()
        # The time of the next bucket comes from the link.
        assert "end_time" in horizon.requests[-1].url.params
        with pytest.raises(PagingError):
            await page.prev()
    assert all(isinstance(record, TradeAggregation) for record in page)


async def test_trade_aggregations_follow_horizon_link_as_written(
    horizon: FakeHorizon,
) -> None:
    # Synthetic links around real records: what Horizon 30.0.1 writes in ascending
    # order without end_time. The package follows it, like the other SDKs.
    body = load("trade_aggregations.json")
    body["_links"]["next"]["href"] = (
        "https://horizon.stellar.org/trade_aggregations?base_asset_type=native"
        "&resolution=3600000&order=asc&start_time=0"
    )
    horizon.on("/trade_aggregations", json_response(200, body))
    async with client_for(horizon) as client:
        page = await client.trade_aggregations.list("native", USDC, 3_600_000)
        again = await page.next()
    assert horizon.requests[-1].url.params["start_time"] == "0"
    assert again.records == page.records


async def test_order_book(horizon: FakeHorizon) -> None:
    url = serve(horizon, "order_book.json")
    async with client_for(horizon) as client:
        book = await client.order_book.get("native", USDC, limit=5)
    assert_sent(horizon, url)
    assert book.base.asset_type == "native"
    assert book.counter.asset_code == "USDC"


async def test_order_book_stream(horizon: FakeHorizon) -> None:
    url = serve(horizon, "streams/order_book.sse")
    async with (
        client_for(horizon) as client,
        client.order_book.stream("native", USDC, limit=5) as stream,
    ):
        book = await anext(stream)
    # `limit` is the depth of the book here; the stream adds no paging.
    assert_sent(horizon, url)
    assert stream.cursor is None
    assert book.counter.asset_code == "USDC"


async def test_paths(horizon: FakeHorizon) -> None:
    receive = serve(horizon, "paths_strict_receive.json")
    send = serve(horizon, "paths_strict_send.json")
    async with client_for(horizon) as client:
        received = await client.paths.strict_receive(
            destination_asset=USDC, destination_amount="10", source_assets="native"
        )
        assert_sent(horizon, receive)
        sent = await client.paths.strict_send(
            source_asset="native", source_amount="10", destination_assets=[USDC]
        )
        assert_sent(horizon, send)
    assert all(isinstance(path, Path) for path in [*received, *sent])
    assert isinstance(received, list)


async def test_assets(horizon: FakeHorizon) -> None:
    url = serve(horizon, "assets.json")
    async with client_for(horizon) as client:
        page = await client.assets.list(code="USDC", limit=10)
    assert_sent(horizon, url)
    assert all(isinstance(record, AssetStat) for record in page)


async def test_claimable_balances(horizon: FakeHorizon) -> None:
    one = serve(horizon, "claimable_balance.json")
    page_url = serve(horizon, "claimable_balances.json")
    async with client_for(horizon) as client:
        balance = await client.claimable_balances.get(
            load("claimable_balance.json")["id"].upper()
        )
        assert_sent(horizon, one)
        page = await client.claimable_balances.list(order="desc", limit=10)
        assert_sent(horizon, page_url)
    assert balance.id == load("claimable_balance.json")["id"]
    assert all(isinstance(record, ClaimableBalance) for record in page)


async def test_liquidity_pools(horizon: FakeHorizon) -> None:
    one = serve(horizon, "liquidity_pool.json")
    page_url = serve(horizon, "liquidity_pools.json")
    async with client_for(horizon) as client:
        pool = await client.liquidity_pools.get(load("liquidity_pool.json")["id"])
        assert_sent(horizon, one)
        page = await client.liquidity_pools.list(order="desc", limit=10)
        assert_sent(horizon, page_url)
    assert pool.id == load("liquidity_pool.json")["id"]
    assert all(isinstance(record, LiquidityPool) for record in page)
