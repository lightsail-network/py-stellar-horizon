from decimal import Decimal
from typing import Any

import pytest

from stellar_horizon import _requests as rq
from stellar_horizon.models import Asset

ISSUER = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
HASH = "AB" * 32


def test_root() -> None:
    request = rq.root()
    assert (request.method, request.endpoint, request.params) == ("GET", "", ())


def test_account_path_is_encoded() -> None:
    assert rq.account("G/A?B").endpoint == "/accounts/G%2FA%3FB"
    # A data entry can be named `.` or `..`, which a URL would resolve away.
    assert rq.account_data("GA", "..").endpoint == "/accounts/GA/data/%2E%2E"
    assert rq.account_data("GA", ".").endpoint == "/accounts/GA/data/%2E"
    assert rq.account_data("GA", "a.b").endpoint == "/accounts/GA/data/a.b"


def test_accounts_needs_exactly_one_filter() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        rq.accounts()
    with pytest.raises(ValueError, match="exactly one"):
        rq.accounts(signer="G1", sponsor="G2")
    request = rq.accounts(sponsor="G2", cursor=5, order="desc", limit=20)
    assert request.endpoint == "/accounts"
    assert request.params == (
        ("sponsor", "G2"),
        ("cursor", "5"),
        ("order", "desc"),
        ("limit", "20"),
    )


@pytest.mark.parametrize(
    ("asset", "written"),
    [
        ("USD:" + ISSUER, "USD:" + ISSUER),
        (
            Asset(asset_type="credit_alphanum4", asset_code="USD", asset_issuer=ISSUER),
            "USD:" + ISSUER,
        ),
        (Asset(asset_type="native"), "native"),
    ],
)
def test_assets_are_written_in_canonical_form(asset: str | Asset, written: str) -> None:
    assert rq.accounts(asset=asset).params == (("asset", written),)


def test_pool_ids_are_lower_case() -> None:
    assert rq.accounts(liquidity_pool="ABCD").params == (("liquidity_pool", "abcd"),)
    assert rq.transactions(liquidity_pool="ABCD").endpoint == (
        "/liquidity_pools/abcd/transactions"
    )


def test_paging_arguments_are_checked() -> None:
    with pytest.raises(ValueError, match="order"):
        rq.transactions(order="up")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="limit"):
        rq.transactions(limit="10")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="limit"):
        rq.transactions(limit=True)


def test_transaction_hash_is_lower_case() -> None:
    assert rq.transaction(HASH).endpoint == "/transactions/" + HASH.lower()


@pytest.mark.parametrize(
    ("scope", "endpoint"),
    [
        ({}, "/transactions"),
        ({"account": "GX"}, "/accounts/GX/transactions"),
        ({"ledger": 7}, "/ledgers/7/transactions"),
        ({"claimable_balance": "00ab"}, "/claimable_balances/00ab/transactions"),
        ({"liquidity_pool": "ab"}, "/liquidity_pools/ab/transactions"),
    ],
)
def test_transaction_scopes(scope: dict[str, Any], endpoint: str) -> None:
    assert rq.transactions(**scope).endpoint == endpoint


def test_at_most_one_scope() -> None:
    with pytest.raises(ValueError, match="at most one of account, ledger"):
        rq.transactions(account="GX", ledger=7)


def test_transactions_flags() -> None:
    assert rq.transactions(include_failed=True).params == (("include_failed", "true"),)
    assert rq.transactions(include_failed=False).params == (
        ("include_failed", "false"),
    )


@pytest.mark.parametrize(
    ("scope", "endpoint"),
    [
        ({}, "/payments"),
        ({"account": "GX"}, "/accounts/GX/payments"),
        ({"ledger": "7"}, "/ledgers/7/payments"),
        ({"transaction": HASH}, f"/transactions/{HASH.lower()}/payments"),
    ],
)
def test_payment_scopes(scope: dict[str, Any], endpoint: str) -> None:
    assert rq.payments(**scope).endpoint == endpoint


def test_payments_join() -> None:
    assert rq.payments(join_transactions=True).params == (("join", "transactions"),)


def test_submit_sends_the_envelope_as_a_form() -> None:
    request = rq.submit_transaction("AAAA")
    assert (request.method, request.endpoint, request.form) == (
        "POST",
        "/transactions",
        (("tx", "AAAA"),),
    )
    with pytest.raises(TypeError, match="base64 XDR"):
        rq.submit_transaction(b"AAAA")  # type: ignore[arg-type]


def test_with_param_replaces_and_removes() -> None:
    request = rq.transactions(cursor="1", limit=10)
    assert request.with_param("cursor", "2").params == (
        ("limit", "10"),
        ("cursor", "2"),
    )
    assert request.with_param("cursor", None).params == (("limit", "10"),)
    assert request.with_params(()).params == ()


def test_fee_stats_and_ledgers() -> None:
    assert rq.fee_stats().endpoint == "/fee_stats"
    assert rq.ledger(7).endpoint == "/ledgers/7"
    assert rq.ledgers(cursor=5, order="desc", limit=3).params == (
        ("cursor", "5"),
        ("order", "desc"),
        ("limit", "3"),
    )


def test_operation() -> None:
    assert rq.operation(12).endpoint == "/operations/12"
    assert rq.operation("12", join_transactions=True).params == (
        ("join", "transactions"),
    )


@pytest.mark.parametrize(
    ("scope", "endpoint"),
    [
        ({}, "/operations"),
        ({"account": "GX"}, "/accounts/GX/operations"),
        ({"ledger": 7}, "/ledgers/7/operations"),
        ({"transaction": HASH}, f"/transactions/{HASH.lower()}/operations"),
        ({"claimable_balance": "00AB"}, "/claimable_balances/00ab/operations"),
        ({"liquidity_pool": "AB"}, "/liquidity_pools/ab/operations"),
    ],
)
def test_operation_scopes(scope: dict[str, Any], endpoint: str) -> None:
    assert rq.operations(**scope).endpoint == endpoint


def test_operations_flags() -> None:
    assert rq.operations(include_failed=True, join_transactions=True).params == (
        ("include_failed", "true"),
        ("join", "transactions"),
    )


@pytest.mark.parametrize(
    ("scope", "endpoint"),
    [
        ({}, "/effects"),
        ({"account": "GX"}, "/accounts/GX/effects"),
        ({"ledger": 7}, "/ledgers/7/effects"),
        ({"transaction": HASH}, f"/transactions/{HASH.lower()}/effects"),
        ({"operation": 12}, "/operations/12/effects"),
        ({"liquidity_pool": "AB"}, "/liquidity_pools/ab/effects"),
    ],
)
def test_effect_scopes(scope: dict[str, Any], endpoint: str) -> None:
    assert rq.effects(**scope).endpoint == endpoint


def test_offers() -> None:
    assert rq.offer(5).endpoint == "/offers/5"
    request = rq.offers(
        seller="GS", selling="native", buying="USD:" + ISSUER, sponsor="GP", limit=2
    )
    assert request.params == (
        ("seller", "GS"),
        ("selling", "native"),
        ("buying", "USD:" + ISSUER),
        ("sponsor", "GP"),
        ("limit", "2"),
    )
    assert rq.offers().params == ()
    assert rq.account_offers("GS", cursor=9).endpoint == "/accounts/GS/offers"
    assert rq.account_offers("GS", cursor=9).params == (("cursor", "9"),)
    # Horizon would take `now` for a place in the history, above every offer ID.
    with pytest.raises(ValueError, match="offer ID"):
        rq.account_offers("GS", cursor="now")


@pytest.mark.parametrize(
    ("asset", "params"),
    [
        ("native", [("p_asset_type", "native")]),
        (
            "USD:" + ISSUER,
            [
                ("p_asset_type", "credit_alphanum4"),
                ("p_asset_code", "USD"),
                ("p_asset_issuer", ISSUER),
            ],
        ),
        (
            Asset(
                asset_type="credit_alphanum12", asset_code="LONGER", asset_issuer=ISSUER
            ),
            [
                ("p_asset_type", "credit_alphanum12"),
                ("p_asset_code", "LONGER"),
                ("p_asset_issuer", ISSUER),
            ],
        ),
    ],
)
def test_asset_params(asset: str | Asset, params: list[tuple[str, str]]) -> None:
    assert rq.asset_params("p", asset) == params


@pytest.mark.parametrize("asset", ["USD", "USD:", ":" + ISSUER, "XLM"])
def test_asset_params_need_code_and_issuer(asset: str) -> None:
    with pytest.raises(ValueError, match="CODE:ISSUER"):
        rq.asset_params("p", asset)


@pytest.mark.parametrize(
    ("scope", "endpoint"),
    [
        ({}, "/trades"),
        ({"account": "GX"}, "/accounts/GX/trades"),
        ({"offer": 5}, "/offers/5/trades"),
        ({"liquidity_pool": "AB"}, "/liquidity_pools/ab/trades"),
    ],
)
def test_trade_scopes(scope: dict[str, Any], endpoint: str) -> None:
    assert rq.trades(**scope).endpoint == endpoint


def test_trades_pair_and_type() -> None:
    request = rq.trades(
        account="GX",
        base_asset="native",
        counter_asset="USD:" + ISSUER,
        trade_type="all",
    )
    assert request.params == (
        ("base_asset_type", "native"),
        ("counter_asset_type", "credit_alphanum4"),
        ("counter_asset_code", "USD"),
        ("counter_asset_issuer", ISSUER),
        ("trade_type", "all"),
    )


def test_trades_rules() -> None:
    with pytest.raises(ValueError, match="together"):
        rq.trades(base_asset="native")
    with pytest.raises(ValueError, match="together with offer"):
        rq.trades(offer=5, base_asset="native", counter_asset="USD:" + ISSUER)
    with pytest.raises(ValueError, match="trade_type"):
        rq.trades(trade_type="pool")  # type: ignore[arg-type]
    # Horizon answers these with 400:
    # https://github.com/stellar/stellar-horizon/blob/01ba44a988b3ebc2d68d3cb6747fa2c2733773cd/internal/actions/trade.go#L136-L148
    with pytest.raises(ValueError, match="together with offer"):
        rq.trades(offer=5, trade_type="liquidity_pool")
    with pytest.raises(ValueError, match="together with liquidity_pool"):
        rq.trades(liquidity_pool="AB", trade_type="orderbook")
    assert rq.trades(offer=5, trade_type="orderbook").params == (
        ("trade_type", "orderbook"),
    )
    assert rq.trades(liquidity_pool="AB", trade_type="all").params == (
        ("trade_type", "all"),
    )


def test_trade_aggregations() -> None:
    request = rq.trade_aggregations(
        "native",
        "USD:" + ISSUER,
        60_000,
        start_time=1,
        end_time=2,
        offset=0,
        order="desc",
        limit=3,
    )
    assert request.endpoint == "/trade_aggregations"
    assert request.params == (
        ("base_asset_type", "native"),
        ("counter_asset_type", "credit_alphanum4"),
        ("counter_asset_code", "USD"),
        ("counter_asset_issuer", ISSUER),
        ("resolution", "60000"),
        ("start_time", "1"),
        ("end_time", "2"),
        ("offset", "0"),
        ("order", "desc"),
        ("limit", "3"),
    )


@pytest.mark.parametrize("value", [1.5, "60000", True])
def test_trade_aggregation_times_are_ints(value: object) -> None:
    with pytest.raises(TypeError, match="resolution must be an int"):
        rq.trade_aggregations("native", "USD:" + ISSUER, value)  # type: ignore[arg-type]


def test_order_book() -> None:
    request = rq.order_book("USD:" + ISSUER, "native", limit=5)
    assert request.params == (
        ("selling_asset_type", "credit_alphanum4"),
        ("selling_asset_code", "USD"),
        ("selling_asset_issuer", ISSUER),
        ("buying_asset_type", "native"),
        ("limit", "5"),
    )


def test_strict_receive_paths() -> None:
    request = rq.strict_receive_paths(
        destination_asset="native",
        destination_amount="10",
        source_assets=["USD:" + ISSUER, Asset(asset_type="native")],
    )
    assert request.endpoint == "/paths/strict-receive"
    assert request.params == (
        ("destination_asset_type", "native"),
        ("destination_amount", "10"),
        ("source_assets", f"USD:{ISSUER},native"),
    )
    request = rq.strict_receive_paths(
        destination_asset="native", destination_amount="10", source_account="GX"
    )
    assert request.params[-1] == ("source_account", "GX")
    with pytest.raises(ValueError, match="exactly one of source_account"):
        rq.strict_receive_paths(destination_asset="native", destination_amount="1")


def test_strict_send_paths() -> None:
    request = rq.strict_send_paths(
        source_asset="native", source_amount="10", destination_assets="USD:" + ISSUER
    )
    assert request.endpoint == "/paths/strict-send"
    assert request.params == (
        ("source_asset_type", "native"),
        ("source_amount", "10"),
        ("destination_assets", "USD:" + ISSUER),
    )
    request = rq.strict_send_paths(
        source_asset="native", source_amount="10", destination_account="GX"
    )
    assert request.params[-1] == ("destination_account", "GX")
    with pytest.raises(ValueError, match="exactly one of destination_account"):
        rq.strict_send_paths(
            source_asset="native",
            source_amount="1",
            destination_account="GX",
            destination_assets="native",
        )


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("0.0000001"), "0.0000001"),
        (Decimal(100).normalize(), "100"),
        (Decimal("12.50"), "12.50"),
        ("1E-7", "1E-7"),
    ],
)
def test_paths_write_decimal_amounts_without_an_exponent(
    amount: Decimal | str, expected: str
) -> None:
    receive = rq.strict_receive_paths(
        destination_asset="native", destination_amount=amount, source_account="GX"
    )
    send = rq.strict_send_paths(
        source_asset="native", source_amount=amount, destination_account="GX"
    )
    assert ("destination_amount", expected) in receive.params
    assert ("source_amount", expected) in send.params


def test_assets() -> None:
    assert rq.assets(code="USD", issuer=ISSUER, limit=2).params == (
        ("asset_code", "USD"),
        ("asset_issuer", ISSUER),
        ("limit", "2"),
    )


def test_claimable_balances() -> None:
    assert rq.claimable_balance("00AB").endpoint == "/claimable_balances/00ab"
    request = rq.claimable_balances(sponsor="GS", claimant="GC", asset="native")
    assert request.params == (
        ("sponsor", "GS"),
        ("claimant", "GC"),
        ("asset", "native"),
    )


def test_liquidity_pools() -> None:
    assert rq.liquidity_pool("AB").endpoint == "/liquidity_pools/ab"
    assert rq.liquidity_pools(reserves=["native", "USD:" + ISSUER]).params == (
        ("reserves", f"native,USD:{ISSUER}"),
    )
    assert rq.liquidity_pools(account="GX", limit=1).params == (
        ("account", "GX"),
        ("limit", "1"),
    )


def test_liquidity_pools_rules() -> None:
    with pytest.raises(ValueError, match="at most one of reserves, account"):
        rq.liquidity_pools(reserves="native", account="GX")
    with pytest.raises(ValueError, match="at most two"):
        rq.liquidity_pools(reserves=["native", "A:" + ISSUER, "B:" + ISSUER])


def test_enqueue_sends_the_envelope_as_a_form() -> None:
    request = rq.enqueue_transaction("AAAA")
    assert (request.endpoint, request.form) == (
        "/transactions_async",
        (("tx", "AAAA"),),
    )
