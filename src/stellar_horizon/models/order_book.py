"""The order book of an asset pair: `GET /order_book`."""

from decimal import Decimal

from .base import Model
from .common import Asset, Price

__all__ = ["OrderBook", "PriceLevel"]


class PriceLevel(Model):
    """The offers of an order book at one price."""

    price_r: Price
    price: Decimal
    amount: Decimal
    """What the offers at this price sell: `base` for an ask, `counter` for a bid."""


class OrderBook(Model):
    """The bids and asks of an asset pair: `GET /order_book`."""

    bids: list[PriceLevel]
    """Offers to buy `base` with `counter`, the best price first."""
    asks: list[PriceLevel]
    """Offers to sell `base` for `counter`, the best price first."""
    base: Asset
    """The asset given as `selling`."""
    counter: Asset
    """The asset given as `buying`."""
