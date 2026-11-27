"""One request definition per endpoint. Nothing here does I/O.

Each function checks its arguments and returns a `Request`, which both clients send.
Values are left to the server to judge; combinations that the server would refuse, or
answer wrongly, are rejected here with a `ValueError` that names the arguments.
"""

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import TYPE_CHECKING, Generic, Literal, TypeVar
from urllib.parse import quote

from pydantic import TypeAdapter

from .models import (
    Account,
    AccountData,
    Asset,
    AssetStat,
    ClaimableBalance,
    Effect,
    EnqueueResult,
    FeeStats,
    Ledger,
    LiquidityPool,
    Offer,
    Operation,
    OrderBook,
    Path,
    Root,
    Trade,
    TradeAggregation,
    Transaction,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "Order",
    "Request",
    "TradeType",
    "account",
    "account_data",
    "account_offers",
    "accounts",
    "asset_param",
    "asset_params",
    "assets",
    "claimable_balance",
    "claimable_balances",
    "effects",
    "enqueue_transaction",
    "fee_stats",
    "ledger",
    "ledgers",
    "liquidity_pool",
    "liquidity_pools",
    "offer",
    "offers",
    "operation",
    "operations",
    "order_book",
    "payments",
    "root",
    "strict_receive_paths",
    "strict_send_paths",
    "submit_transaction",
    "trade_aggregations",
    "trades",
    "transaction",
    "transactions",
]

T = TypeVar("T")
Order = Literal["asc", "desc"]

ROOT: TypeAdapter[Root] = TypeAdapter(Root)
ACCOUNT: TypeAdapter[Account] = TypeAdapter(Account)
ACCOUNT_DATA: TypeAdapter[AccountData] = TypeAdapter(AccountData)
TRANSACTION: TypeAdapter[Transaction] = TypeAdapter(Transaction)
OPERATION: TypeAdapter[Operation] = TypeAdapter(Operation)
ENQUEUE_RESULT: TypeAdapter[EnqueueResult] = TypeAdapter(EnqueueResult)
FEE_STATS: TypeAdapter[FeeStats] = TypeAdapter(FeeStats)
LEDGER: TypeAdapter[Ledger] = TypeAdapter(Ledger)
EFFECT: TypeAdapter[Effect] = TypeAdapter(Effect)
OFFER: TypeAdapter[Offer] = TypeAdapter(Offer)
TRADE: TypeAdapter[Trade] = TypeAdapter(Trade)
TRADE_AGGREGATION: TypeAdapter[TradeAggregation] = TypeAdapter(TradeAggregation)
ORDER_BOOK: TypeAdapter[OrderBook] = TypeAdapter(OrderBook)
PATH: TypeAdapter[Path] = TypeAdapter(Path)
ASSET_STAT: TypeAdapter[AssetStat] = TypeAdapter(AssetStat)
CLAIMABLE_BALANCE: TypeAdapter[ClaimableBalance] = TypeAdapter(ClaimableBalance)
LIQUIDITY_POOL: TypeAdapter[LiquidityPool] = TypeAdapter(LiquidityPool)


@dataclass(frozen=True, slots=True)
class Request(Generic[T]):
    """What to send, and how to read what comes back.

    For a page or a stream, `adapter` reads one record.
    """

    method: Literal["GET", "POST"]
    path: tuple[str, ...]
    """The segments of the path, not encoded."""
    adapter: TypeAdapter[T]
    params: tuple[tuple[str, str], ...] = ()
    form: tuple[tuple[str, str], ...] = ()

    @property
    def endpoint(self) -> str:
        """The path with every segment percent-encoded, starting with `/`."""
        return "".join("/" + _encoded(segment) for segment in self.path)

    def with_params(self, params: tuple[tuple[str, str], ...]) -> "Request[T]":
        """Return the same request with other query parameters."""
        return replace(self, params=params)

    def with_param(self, name: str, value: str | None) -> "Request[T]":
        """Return the same request with `name` set to `value`, or removed if `None`."""
        params = tuple(pair for pair in self.params if pair[0] != name)
        if value is not None:
            params = (*params, (name, value))
        return replace(self, params=params)


def _encoded(segment: str) -> str:
    """Percent-encode a segment of a path, so that it stays one segment and a name.

    `.` and `..` are written out as well. Left as they are, a URL takes them for a
    directory and its parent, and httpx2 resolves them before it sends the request;
    a data entry of an account can have either as its name.
    """
    if segment in {".", ".."}:
        return segment.replace(".", "%2E")
    return quote(segment, safe="")


def asset_param(asset: str | Asset) -> str:
    """Write an asset as Horizon's canonical form, `native` or `CODE:ISSUER`."""
    if isinstance(asset, str):
        return asset
    if asset.asset_type == "native":
        return "native"
    if not asset.asset_code or not asset.asset_issuer:
        msg = (
            "an asset is 'native' or 'CODE:ISSUER', not an Asset of type "
            f"{asset.asset_type!r} without a code or an issuer"
        )
        raise ValueError(msg)
    return f"{asset.asset_code}:{asset.asset_issuer}"


def asset_params(prefix: str, asset: str | Asset) -> list[tuple[str, str]]:
    """Write an asset as the parameters `{prefix}_asset_type`, `_code` and `_issuer`."""
    canonical = asset_param(asset)
    if canonical == "native":
        return [(f"{prefix}_asset_type", "native")]
    code, separator, issuer = canonical.partition(":")
    if not separator or not code or not issuer:
        msg = f"an asset is 'native' or 'CODE:ISSUER', not {canonical!r}"
        raise ValueError(msg)
    kind = "credit_alphanum4" if len(code) <= 4 else "credit_alphanum12"  # noqa: PLR2004
    return [
        (f"{prefix}_asset_type", kind),
        (f"{prefix}_asset_code", code),
        (f"{prefix}_asset_issuer", issuer),
    ]


def _asset_list(assets: "str | Asset | Sequence[str | Asset]") -> str:
    if isinstance(assets, str | Asset):
        assets = [assets]
    return ",".join(asset_param(asset) for asset in assets)


def _paging(
    cursor: str | int | None, order: Order | None, limit: int | None
) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    if cursor is not None:
        params.append(("cursor", str(cursor)))
    if order is not None:
        if order not in {"asc", "desc"}:
            msg = f"order must be 'asc' or 'desc', not {order!r}"
            raise ValueError(msg)
        params.append(("order", order))
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int):  # pyright: ignore[reportUnnecessaryIsInstance]
            msg = f"limit must be an int, not {type(limit).__name__}"
            raise TypeError(msg)
        params.append(("limit", str(limit)))
    return params


def _flag(name: str, value: bool | None) -> list[tuple[str, str]]:  # noqa: FBT001
    return [] if value is None else [(name, "true" if value else "false")]


def _scope(**scopes: str | int | None) -> tuple[str, str] | None:
    given = [(name, value) for name, value in scopes.items() if value is not None]
    if len(given) > 1:
        names = ", ".join(name for name, _ in given)
        msg = f"give at most one of {', '.join(scopes)}; got {names}"
        raise ValueError(msg)
    if not given:
        return None
    name, value = given[0]
    return name, str(value)


_SCOPE_PATHS = {
    "account": "accounts",
    "ledger": "ledgers",
    "transaction": "transactions",
    "operation": "operations",
    "claimable_balance": "claimable_balances",
    "liquidity_pool": "liquidity_pools",
    "offer": "offers",
}
_LOWER_CASE = {"transaction", "claimable_balance", "liquidity_pool"}


def _scoped(resource: str, scope: tuple[str, str] | None) -> tuple[str, ...]:
    if scope is None:
        return (resource,)
    name, value = scope
    if name in _LOWER_CASE:
        value = value.lower()
    return (_SCOPE_PATHS[name], value, resource)


def root() -> Request[Root]:
    """`GET /`."""
    return Request("GET", (), ROOT)


def account(account_id: str) -> Request[Account]:
    """`GET /accounts/{account_id}`."""
    return Request("GET", ("accounts", account_id), ACCOUNT)


def account_data(account_id: str, key: str) -> Request[AccountData]:
    """`GET /accounts/{account_id}/data/{key}`."""
    return Request("GET", ("accounts", account_id, "data", key), ACCOUNT_DATA)


def accounts(
    *,
    signer: str | None = None,
    asset: str | Asset | None = None,
    sponsor: str | None = None,
    liquidity_pool: str | None = None,
    cursor: str | int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[Account]:
    """`GET /accounts`, which needs exactly one filter."""
    filters = {
        "signer": signer,
        "asset": None if asset is None else asset_param(asset),
        "sponsor": sponsor,
        "liquidity_pool": None if liquidity_pool is None else liquidity_pool.lower(),
    }
    given = [(name, value) for name, value in filters.items() if value is not None]
    if len(given) != 1:
        msg = "give exactly one of signer, asset, sponsor, liquidity_pool"
        raise ValueError(msg)
    params = [*given, *_paging(cursor, order, limit)]
    return Request("GET", ("accounts",), ACCOUNT, tuple(params))


def transaction(transaction_hash: str) -> Request[Transaction]:
    """`GET /transactions/{hash}`."""
    return Request("GET", ("transactions", transaction_hash.lower()), TRANSACTION)


def transactions(
    *,
    account: str | None = None,
    ledger: int | str | None = None,
    claimable_balance: str | None = None,
    liquidity_pool: str | None = None,
    include_failed: bool | None = None,
    cursor: str | int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[Transaction]:
    """`GET /transactions`, or the transactions of one resource."""
    scope = _scope(
        account=account,
        ledger=ledger,
        claimable_balance=claimable_balance,
        liquidity_pool=liquidity_pool,
    )
    params = [*_flag("include_failed", include_failed), *_paging(cursor, order, limit)]
    return Request("GET", _scoped("transactions", scope), TRANSACTION, tuple(params))


def payments(
    *,
    account: str | None = None,
    ledger: int | str | None = None,
    transaction: str | None = None,
    include_failed: bool | None = None,
    join_transactions: bool = False,
    cursor: str | int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[Operation]:
    """`GET /payments`, or the payments of one resource."""
    # No `liquidity_pool` or `claimable_balance` scope, on purpose. Horizon's handler
    # reads `liquidity_pool_id` and `claimable_balance_id` on `/payments` too, in
    # `OperationsQuery`:
    # https://github.com/stellar/stellar-horizon/blob/01ba44a988b3ebc2d68d3cb6747fa2c2733773cd/internal/actions/operation.go#L29-L37
    # but only as query parameters: there is no `/liquidity_pools/{id}/payments` or
    # `/claimable_balances/{id}/payments` route, the filters are not documented, and
    # the other SDKs do not offer them. This package uses the documented path form of
    # each filter only. The operations of a pool or a balance, payments among them,
    # are `operations.list(liquidity_pool=...)` and `(claimable_balance=...)`; the
    # query form can be sent with `client.request()`.
    scope = _scope(account=account, ledger=ledger, transaction=transaction)
    params = [
        *_flag("include_failed", include_failed),
        *([("join", "transactions")] if join_transactions else []),
        *_paging(cursor, order, limit),
    ]
    return Request("GET", _scoped("payments", scope), OPERATION, tuple(params))


def _envelope(transaction: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(transaction, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = (
            "transaction must be the envelope as base64 XDR, a str; "
            f"got {type(transaction).__name__}"
        )
        raise TypeError(msg)
    return (("tx", transaction),)


def fee_stats() -> Request[FeeStats]:
    """`GET /fee_stats`."""
    return Request("GET", ("fee_stats",), FEE_STATS)


def ledger(sequence: int | str) -> Request[Ledger]:
    """`GET /ledgers/{sequence}`."""
    return Request("GET", ("ledgers", str(sequence)), LEDGER)


def ledgers(
    *,
    cursor: str | int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[Ledger]:
    """`GET /ledgers`."""
    return Request("GET", ("ledgers",), LEDGER, tuple(_paging(cursor, order, limit)))


def operation(
    operation_id: str | int, *, join_transactions: bool = False
) -> Request[Operation]:
    """`GET /operations/{id}`."""
    params = (("join", "transactions"),) if join_transactions else ()
    return Request("GET", ("operations", str(operation_id)), OPERATION, params)


def operations(
    *,
    account: str | None = None,
    ledger: int | str | None = None,
    transaction: str | None = None,
    claimable_balance: str | None = None,
    liquidity_pool: str | None = None,
    include_failed: bool | None = None,
    join_transactions: bool = False,
    cursor: str | int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[Operation]:
    """`GET /operations`, or the operations of one resource."""
    scope = _scope(
        account=account,
        ledger=ledger,
        transaction=transaction,
        claimable_balance=claimable_balance,
        liquidity_pool=liquidity_pool,
    )
    params = [
        *_flag("include_failed", include_failed),
        *([("join", "transactions")] if join_transactions else []),
        *_paging(cursor, order, limit),
    ]
    return Request("GET", _scoped("operations", scope), OPERATION, tuple(params))


def effects(
    *,
    account: str | None = None,
    ledger: int | str | None = None,
    transaction: str | None = None,
    operation: str | int | None = None,
    liquidity_pool: str | None = None,
    cursor: str | int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[Effect]:
    """`GET /effects`, or the effects of one resource."""
    scope = _scope(
        account=account,
        ledger=ledger,
        transaction=transaction,
        operation=operation,
        liquidity_pool=liquidity_pool,
    )
    params = _paging(cursor, order, limit)
    return Request("GET", _scoped("effects", scope), EFFECT, tuple(params))


def offer(offer_id: str | int) -> Request[Offer]:
    """`GET /offers/{id}`."""
    return Request("GET", ("offers", str(offer_id)), OFFER)


def offers(
    *,
    seller: str | None = None,
    selling: str | Asset | None = None,
    buying: str | Asset | None = None,
    sponsor: str | None = None,
    cursor: str | int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[Offer]:
    """`GET /offers`, filtered by any of its filters."""
    params = [
        *([("seller", seller)] if seller is not None else []),
        *([("selling", asset_param(selling))] if selling is not None else []),
        *([("buying", asset_param(buying))] if buying is not None else []),
        *([("sponsor", sponsor)] if sponsor is not None else []),
        *_paging(cursor, order, limit),
    ]
    return Request("GET", ("offers",), OFFER, tuple(params))


def account_offers(seller: str, *, cursor: str | int | None = None) -> Request[Offer]:
    """`GET /accounts/{seller}/offers`, the route that streams offers."""
    if cursor == "now":
        # Horizon turns `now` into a place in the history on every route:
        # https://github.com/stellar/stellar-horizon/blob/01ba44a988b3ebc2d68d3cb6747fa2c2733773cd/internal/actions/helpers.go#L68-L71
        # Here the cursor is an offer ID, and that place is above every offer ID. On
        # the test network a stream with `now` sent neither the offer that was open
        # nor the one created while it ran.
        msg = (
            "cursor must be an offer ID or None, not 'now': "
            "Horizon would send no offer at all"
        )
        raise ValueError(msg)
    params = _paging(cursor, None, None)
    return Request("GET", ("accounts", seller, "offers"), OFFER, tuple(params))


TradeType = Literal["all", "orderbook", "liquidity_pool"]


def trades(
    *,
    account: str | None = None,
    offer: str | int | None = None,
    liquidity_pool: str | None = None,
    base_asset: str | Asset | None = None,
    counter_asset: str | Asset | None = None,
    trade_type: TradeType | None = None,
    cursor: str | int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[Trade]:
    """`GET /trades`, or the trades of one resource."""
    scope = _scope(account=account, offer=offer, liquidity_pool=liquidity_pool)
    if (base_asset is None) != (counter_asset is None):
        msg = "give base_asset and counter_asset together, or neither"
        raise ValueError(msg)
    if base_asset is not None and scope is not None and scope[0] != "account":
        msg = f"an asset pair cannot be given together with {scope[0]}"
        raise ValueError(msg)
    if scope is not None and (scope[0], trade_type) in {
        ("offer", "liquidity_pool"),
        ("liquidity_pool", "orderbook"),
    }:
        msg = f"trade_type {trade_type!r} cannot be given together with {scope[0]}"
        raise ValueError(msg)
    if trade_type is not None and trade_type not in {
        "all",
        "orderbook",
        "liquidity_pool",
    }:
        msg = (
            "trade_type must be 'all', 'orderbook' or 'liquidity_pool', "
            f"not {trade_type!r}"
        )
        raise ValueError(msg)
    params = [
        *(asset_params("base", base_asset) if base_asset is not None else []),
        *(asset_params("counter", counter_asset) if counter_asset is not None else []),
        *([("trade_type", trade_type)] if trade_type is not None else []),
        *_paging(cursor, order, limit),
    ]
    return Request("GET", _scoped("trades", scope), TRADE, tuple(params))


def trade_aggregations(
    base_asset: str | Asset,
    counter_asset: str | Asset,
    resolution: int,
    *,
    start_time: int | None = None,
    end_time: int | None = None,
    offset: int | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[TradeAggregation]:
    """`GET /trade_aggregations`. Times and durations are in milliseconds."""
    times: dict[str, object] = {
        "resolution": resolution,
        "start_time": start_time,
        "end_time": end_time,
        "offset": offset,
    }
    for name, value in times.items():
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            msg = f"{name} must be an int of milliseconds, not {type(value).__name__}"
            raise TypeError(msg)
    params = [
        *asset_params("base", base_asset),
        *asset_params("counter", counter_asset),
        *((name, str(value)) for name, value in times.items() if value is not None),
        *_paging(None, order, limit),
    ]
    return Request("GET", ("trade_aggregations",), TRADE_AGGREGATION, tuple(params))


def order_book(
    selling: str | Asset, buying: str | Asset, *, limit: int | None = None
) -> Request[OrderBook]:
    """`GET /order_book`. Here `limit` is the number of price levels on each side."""
    params = [
        *asset_params("selling", selling),
        *asset_params("buying", buying),
        *_paging(None, None, limit),
    ]
    return Request("GET", ("order_book",), ORDER_BOOK, tuple(params))


def _amount(amount: str | Decimal) -> str:
    # Horizon accepts only plain decimal numbers, while str() writes a Decimal such as
    # Decimal("0.0000001") or Decimal(100).normalize() as 1E-7 or 1E+2.
    return format(amount, "f") if isinstance(amount, Decimal) else amount


def strict_receive_paths(
    *,
    destination_asset: str | Asset,
    destination_amount: str | Decimal,
    source_account: str | None = None,
    source_assets: "str | Asset | Sequence[str | Asset] | None" = None,
) -> Request[Path]:
    """`GET /paths/strict-receive`: paths that deliver an exact amount."""
    if (source_account is None) == (source_assets is None):
        msg = "give exactly one of source_account, source_assets"
        raise ValueError(msg)
    params = [
        *asset_params("destination", destination_asset),
        ("destination_amount", _amount(destination_amount)),
        *([("source_account", source_account)] if source_account is not None else []),
        *(
            [("source_assets", _asset_list(source_assets))]
            if source_assets is not None
            else []
        ),
    ]
    return Request("GET", ("paths", "strict-receive"), PATH, tuple(params))


def strict_send_paths(
    *,
    source_asset: str | Asset,
    source_amount: str | Decimal,
    destination_account: str | None = None,
    destination_assets: "str | Asset | Sequence[str | Asset] | None" = None,
) -> Request[Path]:
    """`GET /paths/strict-send`: paths that send an exact amount."""
    if (destination_account is None) == (destination_assets is None):
        msg = "give exactly one of destination_account, destination_assets"
        raise ValueError(msg)
    params = [
        *asset_params("source", source_asset),
        ("source_amount", _amount(source_amount)),
        *(
            [("destination_account", destination_account)]
            if destination_account is not None
            else []
        ),
        *(
            [("destination_assets", _asset_list(destination_assets))]
            if destination_assets is not None
            else []
        ),
    ]
    return Request("GET", ("paths", "strict-send"), PATH, tuple(params))


def assets(
    *,
    code: str | None = None,
    issuer: str | None = None,
    cursor: str | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[AssetStat]:
    """`GET /assets`."""
    params = [
        *([("asset_code", code)] if code is not None else []),
        *([("asset_issuer", issuer)] if issuer is not None else []),
        *_paging(cursor, order, limit),
    ]
    return Request("GET", ("assets",), ASSET_STAT, tuple(params))


def claimable_balance(balance_id: str) -> Request[ClaimableBalance]:
    """`GET /claimable_balances/{id}`."""
    return Request("GET", ("claimable_balances", balance_id.lower()), CLAIMABLE_BALANCE)


def claimable_balances(
    *,
    sponsor: str | None = None,
    claimant: str | None = None,
    asset: str | Asset | None = None,
    cursor: str | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[ClaimableBalance]:
    """`GET /claimable_balances`, filtered by any of its filters."""
    params = [
        *([("sponsor", sponsor)] if sponsor is not None else []),
        *([("claimant", claimant)] if claimant is not None else []),
        *([("asset", asset_param(asset))] if asset is not None else []),
        *_paging(cursor, order, limit),
    ]
    return Request("GET", ("claimable_balances",), CLAIMABLE_BALANCE, tuple(params))


def liquidity_pool(pool_id: str) -> Request[LiquidityPool]:
    """`GET /liquidity_pools/{id}`."""
    return Request("GET", ("liquidity_pools", pool_id.lower()), LIQUIDITY_POOL)


def liquidity_pools(
    *,
    reserves: "str | Asset | Sequence[str | Asset] | None" = None,
    account: str | None = None,
    cursor: str | None = None,
    order: Order | None = None,
    limit: int | None = None,
) -> Request[LiquidityPool]:
    """`GET /liquidity_pools`: all pools, those with these reserves, or an account's."""
    if reserves is not None and account is not None:
        msg = "give at most one of reserves, account"
        raise ValueError(msg)
    params: list[tuple[str, str]] = []
    if reserves is not None:
        joined = _asset_list(reserves)
        if joined.count(",") > 1:
            msg = "a liquidity pool has two reserves; give at most two assets"
            raise ValueError(msg)
        params.append(("reserves", joined))
    if account is not None:
        params.append(("account", account))
    params += _paging(cursor, order, limit)
    return Request("GET", ("liquidity_pools",), LIQUIDITY_POOL, tuple(params))


def submit_transaction(transaction: str) -> Request[Transaction]:
    """`POST /transactions` with the envelope in the form field `tx`."""
    return Request("POST", ("transactions",), TRANSACTION, form=_envelope(transaction))


def enqueue_transaction(transaction: str) -> Request[EnqueueResult]:
    """`POST /transactions_async` with the envelope in the form field `tx`."""
    return Request(
        "POST", ("transactions_async",), ENQUEUE_RESULT, form=_envelope(transaction)
    )
