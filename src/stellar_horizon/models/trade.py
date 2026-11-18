"""Trades, against offers or liquidity pools: `GET /trades`."""

from datetime import datetime
from decimal import Decimal

from ._fields import Links
from .base import Model
from .common import Price

__all__ = ["Trade"]


class Trade(Model):
    """A trade, against an offer or a liquidity pool: `GET /trades`.

    When the query named an asset pair, the base side holds its base asset. Otherwise
    the sides are in the order Horizon stores them, by an internal number of each
    asset, which says nothing about the direction of the trade. Either way,
    `base_is_seller` says which side sold.
    """

    links: Links
    id: str
    paging_token: str
    ledger_close_time: datetime
    offer_id: str | None = None
    trade_type: str
    """`orderbook` or `liquidity_pool`."""
    liquidity_pool_fee_bp: int | None = None
    base_liquidity_pool_id: str | None = None
    base_offer_id: str | None = None
    base_account: str | None = None
    base_amount: Decimal
    base_asset_type: str
    base_asset_code: str | None = None
    base_asset_issuer: str | None = None
    counter_liquidity_pool_id: str | None = None
    counter_offer_id: str | None = None
    counter_account: str | None = None
    counter_amount: Decimal
    counter_asset_type: str
    counter_asset_code: str | None = None
    counter_asset_issuer: str | None = None
    base_is_seller: bool
    """Whether the base side sold its asset to the counter side."""
    price: Price | None = None
    """The price of one unit of the base asset, in units of the counter asset."""
