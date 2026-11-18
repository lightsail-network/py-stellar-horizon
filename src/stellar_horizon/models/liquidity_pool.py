"""Liquidity pools: `GET /liquidity_pools`."""

from datetime import datetime
from decimal import Decimal

from ._fields import Links
from .base import Model
from .common import AssetAmount

__all__ = ["LiquidityPool"]


class LiquidityPool(Model):
    """A liquidity pool: `GET /liquidity_pools`."""

    links: Links
    id: str
    paging_token: str
    fee_bp: int
    """The fee, in basis points."""
    type: str
    total_trustlines: int
    total_shares: Decimal
    reserves: list[AssetAmount]
    last_modified_ledger: int
    last_modified_time: datetime | None = None
