"""Offers that are open on the order book: `GET /offers`."""

from datetime import datetime
from decimal import Decimal

from ._fields import Links
from .base import Model
from .common import Asset, Price

__all__ = ["Offer"]


class Offer(Model):
    """An offer that is open on the order book: `GET /offers`."""

    links: Links
    id: str
    paging_token: str
    seller: str
    selling: Asset
    buying: Asset
    amount: Decimal
    """The amount of `selling` that is offered."""
    price_r: Price
    price: Decimal
    """The price of one unit of `selling`, in units of `buying`."""
    last_modified_ledger: int
    last_modified_time: datetime | None = None
    sponsor: str | None = None
