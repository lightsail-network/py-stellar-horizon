"""Ledgers: `GET /ledgers`."""

from datetime import datetime
from decimal import Decimal

from ._fields import Links
from .base import Model

__all__ = ["Ledger"]


class Ledger(Model):
    """A closed ledger."""

    links: Links
    id: str
    paging_token: str
    hash: str
    prev_hash: str | None = None
    """Absent for the first ledger."""
    sequence: int
    successful_transaction_count: int
    failed_transaction_count: int | None = None
    """`None` in ledgers that old versions of Horizon ingested."""
    operation_count: int
    """The operations of the successful transactions."""
    tx_set_operation_count: int | None = None
    """The operations of all transactions, failed ones included. `None` in ledgers that
    old versions of Horizon ingested."""
    closed_at: datetime
    total_coins: Decimal
    """The lumens in existence."""
    fee_pool: Decimal
    """The lumens collected as fees and not yet handed out."""
    base_fee_in_stroops: int
    base_reserve_in_stroops: int
    max_tx_set_size: int
    protocol_version: int
    header_xdr: str
    """The `LedgerHeader`, as base64 XDR."""
