"""The fees of recent ledgers: `GET /fee_stats`."""

from decimal import Decimal

from .base import Model

__all__ = ["FeeDistribution", "FeeStats"]


class FeeDistribution(Model):
    """Fees over the last few ledgers, in stroops: their range, mode and percentiles."""

    max: int
    min: int
    mode: int
    p10: int
    p20: int
    p30: int
    p40: int
    p50: int
    p60: int
    p70: int
    p80: int
    p90: int
    p95: int
    p99: int


class FeeStats(Model):
    """The fees of recent ledgers: `GET /fee_stats`."""

    last_ledger: int
    last_ledger_base_fee: int
    """The base fee of the last ledger, in stroops."""
    ledger_capacity_usage: Decimal
    """How full the recent ledgers were, from 0 to 1."""
    fee_charged: FeeDistribution
    """What transactions paid."""
    max_fee: FeeDistribution
    """What transactions offered to pay at most."""
