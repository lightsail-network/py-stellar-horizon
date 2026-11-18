"""The resources of a client: `client.accounts`, `client.transactions` and so on."""

from decimal import Decimal
from typing import TYPE_CHECKING

from stellar_horizon import _requests
from stellar_horizon._requests import Order, TradeType
from stellar_horizon.errors import NotFoundError
from stellar_horizon.models import (
    Account,
    AccountData,
    Asset,
    AssetStat,
    ClaimableBalance,
    Effect,
    EnqueueResult,
    Ledger,
    LiquidityPool,
    Offer,
    Operation,
    OrderBook,
    Path,
    Trade,
    TradeAggregation,
    Transaction,
)

from ._page import AsyncPage
from ._stream import AsyncStream

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ._session import AsyncSession

__all__ = [
    "AsyncAccounts",
    "AsyncAssets",
    "AsyncClaimableBalances",
    "AsyncEffects",
    "AsyncLedgers",
    "AsyncLiquidityPools",
    "AsyncOffers",
    "AsyncOperations",
    "AsyncOrderBooks",
    "AsyncPaths",
    "AsyncPayments",
    "AsyncTradeAggregations",
    "AsyncTrades",
    "AsyncTransactions",
]

MEMO_REQUIRED = "config.memo_required"
"""The data entry by which an account asks for a memo, as SEP-29 defines it."""

GIVE_UP_AFTER = 300.0
"""Seconds without a working connection after which a stream raises `StreamError`."""


class AsyncResource:
    """What every resource of a client is made of: the session it sends with."""

    def __init__(self, session: "AsyncSession") -> None:
        self._session = session


class AsyncAccounts(AsyncResource):
    """Accounts: `client.accounts`."""

    async def get(self, account_id: str) -> Account:
        """Fetch an account: `GET /accounts/{account_id}`.

        Raises:
            NotFoundError: The account does not exist.
        """
        return await self._session.get(_requests.account(account_id))

    async def data(self, account_id: str, key: str) -> AccountData:
        """Fetch one data entry of an account: `GET /accounts/{account_id}/data/{key}`.

        Raises:
            NotFoundError: The account has no such entry, or does not exist.
        """
        return await self._session.get(_requests.account_data(account_id, key))

    def stream_data(
        self,
        account_id: str,
        key: str,
        *,
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[AccountData]:
        """Stream one data entry of an account: its value now, and each change.

        Args:
            account_id: The account.
            key: The name of the entry.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.

        The stream yields the entry when it opens and again whenever it changes. A
        value equal to the one before is not yielded twice, also across reconnects.
        """
        request = _requests.account_data(account_id, key)
        return self._session.stream(
            request, kind="object", cursor=None, give_up_after=give_up_after
        )

    async def requires_memo(self, account_id: str) -> bool:
        """Tell whether payments to an account must carry a memo, as SEP-29 asks.

        An account asks for a memo with the data entry `config.memo_required` set to
        `1`. This method fetches only that entry. It is the lookup that a SEP-29
        check needs; the check itself, which reads the transaction, belongs to
        `stellar-sdk`.

        Args:
            account_id: The destination, `G...` or muxed `M...`.

        Returns:
            `True` if the entry is `1`. `False` if it is anything else, if the
            account has no such entry or does not exist, and for a muxed address,
            which SEP-29 exempts, without a request.
        """
        if account_id.startswith("M"):
            return False
        try:
            entry = await self.data(account_id, MEMO_REQUIRED)
        except NotFoundError:
            return False
        return entry.value == b"1"

    async def list(
        self,
        *,
        signer: str | None = None,
        asset: str | Asset | None = None,
        sponsor: str | None = None,
        liquidity_pool: str | None = None,
        cursor: str | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[Account]:
        """Fetch a page of accounts: `GET /accounts`. Give exactly one filter.

        Args:
            signer: Accounts that have this signer.
            asset: Accounts that hold this asset, as `CODE:ISSUER` or an `Asset`.
            sponsor: Accounts whose reserves this account pays, in whole or in part.
            liquidity_pool: Accounts that hold shares of this pool.
            cursor: An account ID to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.
        """
        request = _requests.accounts(
            signer=signer,
            asset=asset,
            sponsor=sponsor,
            liquidity_pool=liquidity_pool,
            cursor=cursor,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)


class AsyncTransactions(AsyncResource):
    """Transactions, and submitting them: `client.transactions`."""

    async def get(self, transaction_hash: str) -> Transaction:
        """Fetch a transaction, successful or not: `GET /transactions/{hash}`.

        Raises:
            NotFoundError: The server has no such transaction.
        """
        return await self._session.get(_requests.transaction(transaction_hash))

    async def list(
        self,
        *,
        account: str | None = None,
        ledger: int | str | None = None,
        claimable_balance: str | None = None,
        liquidity_pool: str | None = None,
        include_failed: bool | None = None,
        cursor: str | int | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[Transaction]:
        """Fetch a page of transactions: of the network, or of one resource.

        Args:
            account: The transactions of this account.
            ledger: The transactions of this ledger.
            claimable_balance: The transactions of this claimable balance, by ID in hex.
            liquidity_pool: The transactions of this liquidity pool, by ID in hex.
            include_failed: Also return failed transactions.
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.

        Give at most one of `account`, `ledger`, `claimable_balance` and
        `liquidity_pool`.
        """
        request = _requests.transactions(
            account=account,
            ledger=ledger,
            claimable_balance=claimable_balance,
            liquidity_pool=liquidity_pool,
            include_failed=include_failed,
            cursor=cursor,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)

    def stream(
        self,
        *,
        account: str | None = None,
        ledger: int | str | None = None,
        claimable_balance: str | None = None,
        liquidity_pool: str | None = None,
        include_failed: bool | None = None,
        cursor: str | int | None = "now",
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[Transaction]:
        """Stream transactions as Horizon ingests them, of the network or of a resource.

        Args:
            account: The transactions of this account.
            ledger: The transactions of this ledger.
            claimable_balance: The transactions of this claimable balance, by ID in hex.
            liquidity_pool: The transactions of this liquidity pool, by ID in hex.
            include_failed: Also return failed transactions.
            cursor: `now` for what is ingested from now on, a paging token to start
                after, or `None` for the oldest history the server keeps. An empty
                string starts there too.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.

        Give at most one of `account`, `ledger`, `claimable_balance` and
        `liquidity_pool`.

        A cursor older than the history the server keeps is moved forward by the
        server, without notice, to the oldest ledger it has.
        """
        request = _requests.transactions(
            account=account,
            ledger=ledger,
            claimable_balance=claimable_balance,
            liquidity_pool=liquidity_pool,
            include_failed=include_failed,
        )
        return self._session.stream(
            request, kind="records", cursor=cursor, give_up_after=give_up_after
        )

    async def submit(self, transaction: str) -> Transaction:
        """Submit a transaction and wait until it is in a ledger: `POST /transactions`.

        Horizon waits up to 30 seconds. The SEP-29 memo requirements of the
        destinations are not checked; see `client.accounts.requires_memo()`.

        Args:
            transaction: The signed envelope, as base64 XDR.

        Returns:
            The transaction, as Horizon ingested it.

        Raises:
            TransactionFailedError: The transaction did not succeed: stellar-core
                refused it, or it is in a ledger and failed, with its fee charged.
            BadRequestError: The envelope is malformed.
            TransportError: The server could not be reached, so nothing was sent.
            OutcomeUnknownError: The transaction may or may not have been accepted.
                Send the same envelope again, or look the hash up later.
        """
        return await self._session.submit(_requests.submit_transaction(transaction))

    async def enqueue(self, transaction: str) -> EnqueueResult:
        """Hand a transaction to stellar-core without waiting for a ledger.

        `POST /transactions_async`. Horizon answers as soon as stellar-core has looked
        at the transaction. Look at `tx_status` of the result: only `PENDING` means
        that the transaction is on its way into a ledger. `DUPLICATE`,
        `TRY_AGAIN_LATER` and `ERROR` are returned too, not raised. The SEP-29 memo
        requirements of the destinations are not checked; see
        `client.accounts.requires_memo()`.

        Args:
            transaction: The signed envelope, as base64 XDR.

        Returns:
            What stellar-core made of the transaction.

        Raises:
            BadRequestError: The envelope is malformed.
            TransportError: The server could not be reached, so nothing was sent.
            OutcomeUnknownError: The transaction may or may not have been accepted.
                Send the same envelope again, or look the hash up later.
        """
        request = _requests.enqueue_transaction(transaction)
        return await self._session.submit(request, any_status=True)


class AsyncPayments(AsyncResource):
    """Payments: the operations that move assets. `client.payments`."""

    async def list(
        self,
        *,
        account: str | None = None,
        ledger: int | str | None = None,
        transaction: str | None = None,
        include_failed: bool | None = None,
        join_transactions: bool = False,
        cursor: str | int | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[Operation]:
        """Fetch a page of payments: of the network, or of one resource.

        Payments are `create_account`, `payment`, the two path payments,
        `account_merge`, and contract calls that moved an asset.

        Args:
            account: The payments of this account.
            ledger: The payments of this ledger.
            transaction: The payments of this transaction.
            include_failed: Also return payments of failed transactions.
            join_transactions: Return each payment with its transaction.
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.

        Give at most one of `account`, `ledger` and `transaction`.
        """
        request = _requests.payments(
            account=account,
            ledger=ledger,
            transaction=transaction,
            include_failed=include_failed,
            join_transactions=join_transactions,
            cursor=cursor,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)

    def stream(
        self,
        *,
        account: str | None = None,
        ledger: int | str | None = None,
        transaction: str | None = None,
        include_failed: bool | None = None,
        join_transactions: bool = False,
        cursor: str | int | None = "now",
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[Operation]:
        """Stream payments as Horizon ingests them.

        Args:
            account: The payments of this account.
            ledger: The payments of this ledger.
            transaction: The payments of this transaction.
            include_failed: Also return payments of failed transactions.
            join_transactions: Return each payment with its transaction.
            cursor: `now` for what is ingested from now on, a paging token to start
                after, or `None` for the oldest history the server keeps. An empty
                string starts there too.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.

        A cursor older than the history the server keeps is moved forward by the
        server, without notice, to the oldest ledger it has.
        """
        request = _requests.payments(
            account=account,
            ledger=ledger,
            transaction=transaction,
            include_failed=include_failed,
            join_transactions=join_transactions,
        )
        return self._session.stream(
            request, kind="records", cursor=cursor, give_up_after=give_up_after
        )


class AsyncLedgers(AsyncResource):
    """Ledgers: `client.ledgers`."""

    async def get(self, sequence: int | str) -> Ledger:
        """Fetch a ledger by its sequence number: `GET /ledgers/{sequence}`.

        Raises:
            NotFoundError: The ledger has not closed yet.
            BeforeHistoryError: The ledger is older than the history the server keeps.
        """
        return await self._session.get(_requests.ledger(sequence))

    async def list(
        self,
        *,
        cursor: str | int | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[Ledger]:
        """Fetch a page of ledgers: `GET /ledgers`.

        Args:
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.
        """
        request = _requests.ledgers(cursor=cursor, order=order, limit=limit)
        return await self._session.page(request)

    def stream(
        self,
        *,
        cursor: str | int | None = "now",
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[Ledger]:
        """Stream ledgers as Horizon ingests them, one about every five seconds.

        Args:
            cursor: `now` for what is ingested from now on, a paging token to start
                after, or `None` for the oldest history the server keeps. An empty
                string starts there too.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.

        A cursor older than the history the server keeps is moved forward by the
        server, without notice, to the oldest ledger it has.
        """
        return self._session.stream(
            _requests.ledgers(),
            kind="records",
            cursor=cursor,
            give_up_after=give_up_after,
        )


class AsyncOperations(AsyncResource):
    """Operations: `client.operations`."""

    async def get(
        self, operation_id: str | int, *, join_transactions: bool = False
    ) -> Operation:
        """Fetch an operation, successful or not: `GET /operations/{id}`.

        Args:
            operation_id: The ID of the operation.
            join_transactions: Return the operation with its transaction.

        Raises:
            NotFoundError: The server has no such operation.
        """
        request = _requests.operation(operation_id, join_transactions=join_transactions)
        return await self._session.get(request)

    async def list(
        self,
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
    ) -> AsyncPage[Operation]:
        """Fetch a page of operations: of the network, or of one resource.

        Args:
            account: The operations of this account.
            ledger: The operations of this ledger.
            transaction: The operations of this transaction.
            claimable_balance: The operations of this claimable balance, by ID in hex.
            liquidity_pool: The operations of this liquidity pool, by ID in hex.
            include_failed: Also return operations of failed transactions.
            join_transactions: Return each operation with its transaction.
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.

        Give at most one of `account`, `ledger`, `transaction`, `claimable_balance`
        and `liquidity_pool`.
        """
        request = _requests.operations(
            account=account,
            ledger=ledger,
            transaction=transaction,
            claimable_balance=claimable_balance,
            liquidity_pool=liquidity_pool,
            include_failed=include_failed,
            join_transactions=join_transactions,
            cursor=cursor,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)

    def stream(
        self,
        *,
        account: str | None = None,
        ledger: int | str | None = None,
        transaction: str | None = None,
        claimable_balance: str | None = None,
        liquidity_pool: str | None = None,
        include_failed: bool | None = None,
        join_transactions: bool = False,
        cursor: str | int | None = "now",
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[Operation]:
        """Stream operations as Horizon ingests them, of the network or of a resource.

        Args:
            account: The operations of this account.
            ledger: The operations of this ledger.
            transaction: The operations of this transaction.
            claimable_balance: The operations of this claimable balance, by ID in hex.
            liquidity_pool: The operations of this liquidity pool, by ID in hex.
            include_failed: Also return operations of failed transactions.
            join_transactions: Return each operation with its transaction.
            cursor: `now` for what is ingested from now on, a paging token to start
                after, or `None` for the oldest history the server keeps. An empty
                string starts there too.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.

        Give at most one of `account`, `ledger`, `transaction`, `claimable_balance`
        and `liquidity_pool`.

        A cursor older than the history the server keeps is moved forward by the
        server, without notice, to the oldest ledger it has.
        """
        request = _requests.operations(
            account=account,
            ledger=ledger,
            transaction=transaction,
            claimable_balance=claimable_balance,
            liquidity_pool=liquidity_pool,
            include_failed=include_failed,
            join_transactions=join_transactions,
        )
        return self._session.stream(
            request, kind="records", cursor=cursor, give_up_after=give_up_after
        )


class AsyncEffects(AsyncResource):
    """Effects, the changes that operations made: `client.effects`."""

    async def list(
        self,
        *,
        account: str | None = None,
        ledger: int | str | None = None,
        transaction: str | None = None,
        operation: str | int | None = None,
        liquidity_pool: str | None = None,
        cursor: str | int | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[Effect]:
        """Fetch a page of effects: of the network, or of one resource.

        Args:
            account: The effects on this account.
            ledger: The effects of this ledger.
            transaction: The effects of this transaction.
            operation: The effects of this operation.
            liquidity_pool: The effects on this liquidity pool, by ID in hex.
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.

        Give at most one of `account`, `ledger`, `transaction`, `operation` and
        `liquidity_pool`. Only effects of successful transactions exist.
        """
        request = _requests.effects(
            account=account,
            ledger=ledger,
            transaction=transaction,
            operation=operation,
            liquidity_pool=liquidity_pool,
            cursor=cursor,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)

    def stream(
        self,
        *,
        account: str | None = None,
        ledger: int | str | None = None,
        transaction: str | None = None,
        operation: str | int | None = None,
        liquidity_pool: str | None = None,
        cursor: str | int | None = "now",
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[Effect]:
        """Stream effects as Horizon ingests them, of the network or of a resource.

        Args:
            account: The effects on this account.
            ledger: The effects of this ledger.
            transaction: The effects of this transaction.
            operation: The effects of this operation.
            liquidity_pool: The effects on this liquidity pool, by ID in hex.
            cursor: `now` for what is ingested from now on, a paging token to start
                after, or `None` for the oldest history the server keeps. An empty
                string starts there too.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.

        Give at most one of `account`, `ledger`, `transaction`, `operation` and
        `liquidity_pool`.

        A cursor older than the history the server keeps is moved forward by the
        server, without notice, to the oldest ledger it has.
        """
        request = _requests.effects(
            account=account,
            ledger=ledger,
            transaction=transaction,
            operation=operation,
            liquidity_pool=liquidity_pool,
        )
        return self._session.stream(
            request, kind="records", cursor=cursor, give_up_after=give_up_after
        )


class AsyncOffers(AsyncResource):
    """Offers that are open on the order book: `client.offers`."""

    async def get(self, offer_id: str | int) -> Offer:
        """Fetch an open offer: `GET /offers/{id}`.

        Raises:
            NotFoundError: No open offer has this ID: it was filled, removed, or
                never existed.
        """
        return await self._session.get(_requests.offer(offer_id))

    async def list(
        self,
        *,
        seller: str | None = None,
        selling: str | Asset | None = None,
        buying: str | Asset | None = None,
        sponsor: str | None = None,
        cursor: str | int | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[Offer]:
        """Fetch a page of open offers: `GET /offers`. The filters can be combined.

        Args:
            seller: The offers of this account.
            selling: Offers that sell this asset, as `native`, `CODE:ISSUER` or an
                `Asset`.
            buying: Offers that buy this asset.
            sponsor: Offers whose reserve this account pays.
            cursor: An offer ID to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.
        """
        request = _requests.offers(
            seller=seller,
            selling=selling,
            buying=buying,
            sponsor=sponsor,
            cursor=cursor,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)

    def stream(
        self,
        *,
        seller: str,
        cursor: str | int | None = None,
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[Offer]:
        """Stream the open offers of an account: `GET /accounts/{seller}/offers`.

        This is not a feed of changes. The stream yields the offers of `seller` that
        are open now, by increasing ID, and then each new offer with a higher ID.
        It never yields a change to an offer, or its removal, and an offer that was
        created and removed between two polls of the server is not seen.

        Args:
            seller: The account.
            cursor: An offer ID to start after, or `None` to start with the first.
                `now` raises `ValueError`: Horizon would send no offer at all.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.
        """
        request = _requests.account_offers(seller, cursor=cursor)
        return self._session.stream(
            request, kind="records", cursor=cursor, give_up_after=give_up_after
        )


class AsyncTrades(AsyncResource):
    """Trades, against offers or liquidity pools: `client.trades`."""

    async def list(
        self,
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
    ) -> AsyncPage[Trade]:
        """Fetch a page of trades: of the network, of an asset pair, or of a resource.

        Args:
            account: The trades of this account.
            offer: The trades of this offer.
            liquidity_pool: The trades of this liquidity pool, by ID in hex.
            base_asset: With `counter_asset`, the trades of this asset pair, as
                `native`, `CODE:ISSUER` or an `Asset`.
            counter_asset: The other asset of the pair.
            trade_type: `orderbook`, `liquidity_pool`, or `all`, the default.
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.

        Give at most one of `account`, `offer` and `liquidity_pool`. An asset pair
        can be combined with `account` only. The trades of an offer are not of type
        `liquidity_pool`, and those of a pool not of type `orderbook`.
        """
        request = _requests.trades(
            account=account,
            offer=offer,
            liquidity_pool=liquidity_pool,
            base_asset=base_asset,
            counter_asset=counter_asset,
            trade_type=trade_type,
            cursor=cursor,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)

    def stream(
        self,
        *,
        account: str | None = None,
        offer: str | int | None = None,
        liquidity_pool: str | None = None,
        base_asset: str | Asset | None = None,
        counter_asset: str | Asset | None = None,
        trade_type: TradeType | None = None,
        cursor: str | int | None = "now",
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[Trade]:
        """Stream trades as Horizon ingests them.

        Args:
            account: The trades of this account.
            offer: The trades of this offer.
            liquidity_pool: The trades of this liquidity pool, by ID in hex.
            base_asset: With `counter_asset`, the trades of this asset pair.
            counter_asset: The other asset of the pair.
            trade_type: `orderbook`, `liquidity_pool`, or `all`, the default.
            cursor: `now` for what is ingested from now on, a paging token to start
                after, or `None` for the oldest history the server keeps. An empty
                string starts there too.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.

        The arguments combine as for `list()`. A cursor older than the history the
        server keeps is moved forward by the server, without notice, to the oldest
        ledger it has.
        """
        request = _requests.trades(
            account=account,
            offer=offer,
            liquidity_pool=liquidity_pool,
            base_asset=base_asset,
            counter_asset=counter_asset,
            trade_type=trade_type,
        )
        return self._session.stream(
            request, kind="records", cursor=cursor, give_up_after=give_up_after
        )


class AsyncTradeAggregations(AsyncResource):
    """Trades of an asset pair summed up by time: `client.trade_aggregations`."""

    async def list(
        self,
        base_asset: str | Asset,
        counter_asset: str | Asset,
        resolution: int,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
        offset: int | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[TradeAggregation]:
        """Fetch a page of trade aggregations: `GET /trade_aggregations`.

        Args:
            base_asset: The base asset, as `native`, `CODE:ISSUER` or an `Asset`.
            counter_asset: The counter asset.
            resolution: The length of each bucket in milliseconds: one minute,
                5 minutes, 15 minutes, an hour, a day or a week.
            start_time: The start of the first bucket, in Unix milliseconds.
            end_time: The end of the last bucket, in Unix milliseconds.
            offset: Moves the buckets by this many milliseconds: a whole number of
                hours, less than a day and no more than `resolution`.
            order: `asc` or `desc`.
            limit: Buckets per page, at most 200.

        `next()` follows the time the server wrote in the link. `prev()` raises
        `PagingError`, because the server sends an empty `prev` link.

        In ascending order, the default, give `end_time` to page forward. Without it,
        Horizon 30.0.1 writes `start_time=0` into the `next` link, because it caps the
        next start at an end time of 0, in
        [internal/actions/trade.go](https://github.com/stellar/stellar-horizon/blob/01ba44a988b3ebc2d68d3cb6747fa2c2733773cd/internal/actions/trade.go#L445-L449).
        `next()` then returns the first page again, and `iter_records()` yields it
        twice before it raises `PagingError`. Descending order is not affected. The
        other Stellar SDKs follow the link as Horizon wrote it, and this package does
        the same on purpose, so that paging behaves alike in every language.
        """
        request = _requests.trade_aggregations(
            base_asset,
            counter_asset,
            resolution,
            start_time=start_time,
            end_time=end_time,
            offset=offset,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)


class AsyncOrderBooks(AsyncResource):
    """The order book of an asset pair: `client.order_book`."""

    async def get(
        self, selling: str | Asset, buying: str | Asset, *, limit: int | None = None
    ) -> OrderBook:
        """Fetch the bids and asks of an asset pair: `GET /order_book`.

        Args:
            selling: The base asset, as `native`, `CODE:ISSUER` or an `Asset`.
            buying: The counter asset.
            limit: Price levels on each side, at most 200; 20 by default.
        """
        return await self._session.get(
            _requests.order_book(selling, buying, limit=limit)
        )

    def stream(
        self,
        selling: str | Asset,
        buying: str | Asset,
        *,
        limit: int | None = None,
        give_up_after: float | None = GIVE_UP_AFTER,
    ) -> AsyncStream[OrderBook]:
        """Stream the order book of an asset pair: as it is now, and each change.

        Args:
            selling: The base asset, as `native`, `CODE:ISSUER` or an `Asset`.
            buying: The counter asset.
            limit: Price levels on each side, at most 200; 20 by default.
            give_up_after: Seconds without a working connection after which the
                stream raises `StreamError`; `None` for never.

        The server sends the book whenever it changes, at most once a ledger, so
        states between two ledgers are not seen. A book equal to the one before is
        not yielded twice, also across reconnects.
        """
        request = _requests.order_book(selling, buying, limit=limit)
        return self._session.stream(
            request, kind="object", cursor=None, give_up_after=give_up_after
        )


class AsyncPaths(AsyncResource):
    """Path finding, for path payments: `client.paths`."""

    async def strict_receive(
        self,
        *,
        destination_asset: str | Asset,
        destination_amount: str | Decimal,
        source_account: str | None = None,
        source_assets: "str | Asset | Sequence[str | Asset] | None" = None,
    ) -> list[Path]:
        """Find paths that deliver an exact amount: `GET /paths/strict-receive`.

        Args:
            destination_asset: The asset to deliver, as `native`, `CODE:ISSUER` or
                an `Asset`.
            destination_amount: The amount to deliver.
            source_account: Find paths from the assets this account holds.
            source_assets: Find paths from these assets, at most 15.

        Give exactly one of `source_account` and `source_assets`.

        Returns:
            The paths, each with the amount it costs; empty if there is none.
        """
        request = _requests.strict_receive_paths(
            destination_asset=destination_asset,
            destination_amount=destination_amount,
            source_account=source_account,
            source_assets=source_assets,
        )
        return await self._session.records(request)

    async def strict_send(
        self,
        *,
        source_asset: str | Asset,
        source_amount: str | Decimal,
        destination_account: str | None = None,
        destination_assets: "str | Asset | Sequence[str | Asset] | None" = None,
    ) -> list[Path]:
        """Find paths that send an exact amount: `GET /paths/strict-send`.

        Args:
            source_asset: The asset to send, as `native`, `CODE:ISSUER` or an
                `Asset`.
            source_amount: The amount to send.
            destination_account: Find paths to the assets this account can hold.
            destination_assets: Find paths to these assets, at most 15.

        Give exactly one of `destination_account` and `destination_assets`.

        Returns:
            The paths, each with the amount it delivers; empty if there is none.
        """
        request = _requests.strict_send_paths(
            source_asset=source_asset,
            source_amount=source_amount,
            destination_account=destination_account,
            destination_assets=destination_assets,
        )
        return await self._session.records(request)


class AsyncAssets(AsyncResource):
    """Issued assets and how much of each is held: `client.assets`."""

    async def list(
        self,
        *,
        code: str | None = None,
        issuer: str | None = None,
        cursor: str | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[AssetStat]:
        """Fetch a page of issued assets: `GET /assets`.

        Args:
            code: Assets with this code.
            issuer: Assets of this issuer.
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.
        """
        request = _requests.assets(
            code=code, issuer=issuer, cursor=cursor, order=order, limit=limit
        )
        return await self._session.page(request)


class AsyncClaimableBalances(AsyncResource):
    """Claimable balances: `client.claimable_balances`."""

    async def get(self, balance_id: str) -> ClaimableBalance:
        """Fetch a claimable balance by its ID in hex: `GET /claimable_balances/{id}`.

        Raises:
            NotFoundError: The balance was claimed, clawed back, or never existed.
        """
        return await self._session.get(_requests.claimable_balance(balance_id))

    async def list(
        self,
        *,
        sponsor: str | None = None,
        claimant: str | None = None,
        asset: str | Asset | None = None,
        cursor: str | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[ClaimableBalance]:
        """Fetch a page of claimable balances. The filters can be combined.

        Args:
            sponsor: Balances whose reserve this account pays.
            claimant: Balances that this account can claim.
            asset: Balances of this asset, as `native`, `CODE:ISSUER` or an `Asset`.
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.
        """
        request = _requests.claimable_balances(
            sponsor=sponsor,
            claimant=claimant,
            asset=asset,
            cursor=cursor,
            order=order,
            limit=limit,
        )
        return await self._session.page(request)


class AsyncLiquidityPools(AsyncResource):
    """Liquidity pools: `client.liquidity_pools`."""

    async def get(self, pool_id: str) -> LiquidityPool:
        """Fetch a liquidity pool by its ID in hex: `GET /liquidity_pools/{id}`.

        Raises:
            NotFoundError: The pool does not exist, or no longer does.
        """
        return await self._session.get(_requests.liquidity_pool(pool_id))

    async def list(
        self,
        *,
        reserves: "str | Asset | Sequence[str | Asset] | None" = None,
        account: str | None = None,
        cursor: str | None = None,
        order: Order | None = None,
        limit: int | None = None,
    ) -> AsyncPage[LiquidityPool]:
        """Fetch a page of liquidity pools: `GET /liquidity_pools`.

        Args:
            reserves: Pools that hold this asset, or both of these two.
            account: Pools in which this account holds shares.
            cursor: A paging token to start after.
            order: `asc` or `desc`.
            limit: Records per page, at most 200.

        Give at most one of `reserves` and `account`.
        """
        request = _requests.liquidity_pools(
            reserves=reserves, account=account, cursor=cursor, order=order, limit=limit
        )
        return await self._session.page(request)
