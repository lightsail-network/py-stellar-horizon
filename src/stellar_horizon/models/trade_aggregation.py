"""Trades of an asset pair summed up by time: `GET /trade_aggregations`."""

from decimal import Decimal

from .base import Model
from .common import Price

__all__ = ["TradeAggregation"]


class TradeAggregation(Model):
    """The trades of one asset pair in one time bucket: `GET /trade_aggregations`."""

    timestamp: int
    """The start of the bucket, in Unix milliseconds."""
    trade_count: int
    base_volume: Decimal
    counter_volume: Decimal
    avg: Decimal
    high: Decimal
    high_r: Price
    low: Decimal
    low_r: Price
    open: Decimal
    open_r: Price
    close: Decimal
    close_r: Price
