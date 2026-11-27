# Generated from _async/_client.py by scripts/unasync.py. Do not edit.
"""The client: one Horizon server, and the resources it serves."""

from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from types import TracebackType
from typing import Self

import httpx2

from stellar_horizon import _requests
from stellar_horizon._retry_policy import check_max_retries
from stellar_horizon.models import FeeStats, Root

from ._resources import (
    Accounts,
    Assets,
    ClaimableBalances,
    Effects,
    Ledgers,
    LiquidityPools,
    Offers,
    Operations,
    OrderBooks,
    Paths,
    Payments,
    TradeAggregations,
    Trades,
    Transactions,
)
from ._session import Session

__all__ = ["HorizonClient"]

DEFAULT_TIMEOUT = 60.0
"""Seconds. Horizon gives up after 55 seconds for a GET, with its default settings."""
_LIBRARY_DEFAULT_TIMEOUT = httpx2.Timeout(5.0)
DEFAULT_MAX_RETRIES = 2
"""How often a failed `GET` is tried again, unless the client is told otherwise."""


class HorizonClient:
    """A client for one Horizon server.

    Args:
        base_url: The URL of the server, such as `https://horizon.stellar.org`. A path
            prefix, such as `https://example.com/horizon/<key>`, is kept, and query
            parameters, such as `https://example.com/?apikey=<key>`, are sent with
            every request. For a key in a header, use `headers`.
        http_client: An `httpx2.Client` to send requests with, for proxies, TLS
            settings or connection limits. The caller closes it.
        timeout: Seconds, or an `httpx2.Timeout`. Without it, the timeout of
            `http_client` is used if it was set, and otherwise 60 seconds.
        max_retries: How often to try a single `GET` again after a transport error
            or a 429, 502, 503 or 504: twice by default, never with 0. The waits
            start at half a second and double, are no shorter than the server's
            `Retry-After`, and add up to at most 60 seconds per call. A submission
            is never sent twice, and streams reconnect by their own rule.
        app_name: Sent as `X-App-Name`, so that the server's logs can tell
            applications apart.
        app_version: Sent as `X-App-Version`.
        headers: Headers to send with every request, streams and submissions
            included, such as `{"Authorization": "Bearer <key>"}`. They take the place
            of headers of the same name, those of `http_client` and the client's own
            `X-Client-Name` and `X-Client-Version` included. A stream sends its own
            `Accept` all the same.
    """

    def __init__(  # noqa: PLR0915
        self,
        base_url: str,
        *,
        http_client: httpx2.Client | None = None,
        timeout: float | httpx2.Timeout | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        app_name: str | None = None,
        app_version: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        url = _checked_base_url(base_url)
        self.base_url: httpx2.URL = url
        """The URL of the server."""
        if http_client is None:
            self._http = httpx2.Client()
            self._owns_http = True
        else:
            if not isinstance(http_client, httpx2.Client):  # pyright: ignore[reportUnnecessaryIsInstance]
                msg = (
                    "http_client must be an httpx2.Client, "
                    f"not {type(http_client).__module__}.{type(http_client).__name__}"
                )
                raise TypeError(msg)
            _refuse_last_event_id(http_client.headers, "the headers of http_client")
            self._http = http_client
            self._owns_http = False
        if timeout is not None:
            resolved = httpx2.Timeout(timeout)
        elif not self._owns_http and self._http.timeout != _LIBRARY_DEFAULT_TIMEOUT:
            resolved = self._http.timeout
        else:
            resolved = httpx2.Timeout(DEFAULT_TIMEOUT)
        sent = httpx2.Headers(
            {
                "X-Client-Name": "py-stellar-horizon",
                "X-Client-Version": _package_version(),
            }
        )
        if app_name is not None:
            sent["X-App-Name"] = app_name
        if app_version is not None:
            sent["X-App-Version"] = app_version
        if headers is not None:
            _refuse_last_event_id(httpx2.Headers(headers), "headers")
            sent.update(headers)
        self._session = Session(
            self._http,
            base_url=url,
            timeout=resolved,
            headers=sent,
            max_retries=check_max_retries(max_retries),
        )
        self.accounts: Accounts = Accounts(self._session)
        """Accounts."""
        self.transactions: Transactions = Transactions(self._session)
        """Transactions, and submitting them."""
        self.payments: Payments = Payments(self._session)
        """Payments: the operations that move assets."""
        self.operations: Operations = Operations(self._session)
        """Operations."""
        self.effects: Effects = Effects(self._session)
        """Effects: the changes that operations made."""
        self.ledgers: Ledgers = Ledgers(self._session)
        """Ledgers."""
        self.offers: Offers = Offers(self._session)
        """Offers that are open on the order book."""
        self.trades: Trades = Trades(self._session)
        """Trades, against offers or liquidity pools."""
        self.trade_aggregations: TradeAggregations = TradeAggregations(self._session)
        """Trades of an asset pair, summed up by time."""
        self.order_book: OrderBooks = OrderBooks(self._session)
        """The order book of an asset pair."""
        self.paths: Paths = Paths(self._session)
        """Path finding, for path payments."""
        self.assets: Assets = Assets(self._session)
        """Issued assets."""
        self.claimable_balances: ClaimableBalances = ClaimableBalances(self._session)
        """Claimable balances."""
        self.liquidity_pools: LiquidityPools = LiquidityPools(self._session)
        """Liquidity pools."""

    def __repr__(self) -> str:
        # Only the scheme and the host: the path or the query can hold a key.
        port = f":{self.base_url.port}" if self.base_url.port else ""
        return f"<{type(self).__name__} {self.base_url.scheme}://{self.base_url.host}{port}>"

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Release the connections, unless the HTTP client was passed in."""
        if self._owns_http:
            self._http.close()

    def root(self) -> Root:
        """What the server reports about itself and the network: `GET /`."""
        return self._session.get(_requests.root())

    def fee_stats(self) -> FeeStats:
        """The fees that recent ledgers charged: `GET /fee_stats`.

        `last_ledger_base_fee` is the base fee to put in a transaction when the
        network is not busy; the percentiles of `fee_charged` show what it takes
        when it is.
        """
        return self._session.get(_requests.fee_stats())

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        """Send any request to the server, and return the response once it is read.

        It reaches what this package does not know yet: a new endpoint, a new
        parameter, or a response header such as `Latest-Ledger`. Errors are raised as
        for every other call, a redirect among them; the exception has the whole
        response. The request is sent once, whatever `max_retries` is.

        A submission sent this way gets no special handling. A broken connection, a
        timeout or a 5xx then means that its outcome is unknown, not that it failed.

        Args:
            method: The HTTP method, such as `GET`.
            path: The path below the base URL, percent-encoded and without a query
                (that goes in `params`), such as
                `/accounts/G.../data/config.memo_required`.
            params: Query parameters.
            data: Form fields, sent as `application/x-www-form-urlencoded`.
            headers: Headers to send in addition to the client's own, in the place
                of those of the same name.
        """
        if not path.startswith("/"):
            path = "/" + path
        _check_path(path)
        try:
            url = self._session.url(path)
        except httpx2.InvalidURL as error:
            msg = f"path is not a URL path: {error}"
            raise ValueError(msg) from error
        return self._session.send(
            method.upper(),
            url,
            params=params,
            data=data,
            headers=headers,
        )


def _checked_base_url(base_url: str) -> httpx2.URL:
    """Return `base_url` as a URL, or raise `ValueError` if a client cannot use it."""
    try:
        url = httpx2.URL(base_url)
    except httpx2.InvalidURL as error:
        msg = f"base_url is not a URL: {error}"
        raise ValueError(msg) from error
    if url.scheme not in {"http", "https"} or not url.host:
        msg = f"base_url must be an http or https URL, not {base_url!r}"
        raise ValueError(msg)
    if url.fragment:
        msg = "base_url must not have a fragment"
        raise ValueError(msg)
    return url


def _check_path(path: str) -> None:
    """Raise `ValueError` if `path` has a query or is not percent-encoded."""
    if "?" in path:
        msg = "path must not have a query; put query parameters in params"
        raise ValueError(msg)
    if "#" in path or not path.isascii():
        msg = f"path must be percent-encoded: {path!r}"
        raise ValueError(msg)


def _package_version() -> str:
    """The version of this package, or `unknown` where its metadata is not installed.

    A program packed into one file, by PyInstaller for example, can come without it.
    """
    try:
        return version("stellar-horizon")
    except PackageNotFoundError:
        return "unknown"


def _refuse_last_event_id(headers: httpx2.Headers, where: str) -> None:
    if "last-event-id" in headers:
        msg = (
            f"{where} contain Last-Event-ID, which Horizon would use in place of "
            "every cursor"
        )
        raise ValueError(msg)
