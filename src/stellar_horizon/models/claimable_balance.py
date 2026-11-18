"""Claimable balances: `GET /claimable_balances`."""

from datetime import datetime
from decimal import Decimal

from ._fields import Links
from .base import Model
from .common import Claimant

__all__ = ["ClaimableBalance", "ClaimableBalanceFlags"]


class ClaimableBalanceFlags(Model):
    """The flags of a claimable balance."""

    clawback_enabled: bool


class ClaimableBalance(Model):
    """An amount waiting to be claimed: `GET /claimable_balances`."""

    links: Links
    id: str
    """The balance ID, in hex."""
    paging_token: str
    asset: str
    """`native` or `CODE:ISSUER`."""
    amount: Decimal
    sponsor: str | None = None
    last_modified_ledger: int
    last_modified_time: datetime | None = None
    claimants: list[Claimant]
    flags: ClaimableBalanceFlags
