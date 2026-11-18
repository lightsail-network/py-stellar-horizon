"""Values that several resources share: assets, prices and claim predicates."""

from decimal import Decimal

from pydantic import Field

from .base import Model

__all__ = ["Asset", "AssetAmount", "ClaimPredicate", "Claimant", "Price"]


class Asset(Model):
    """An asset, as the three fields Horizon uses for it."""

    asset_type: str
    """`native`, `credit_alphanum4` or `credit_alphanum12`."""
    asset_code: str | None = None
    asset_issuer: str | None = None


class Price(Model):
    """A price as a fraction: `n` units of one asset for `d` units of the other."""

    n: int
    d: int


class AssetAmount(Model):
    """An amount of an asset, the asset written as `native` or `CODE:ISSUER`."""

    asset: str | None = None
    """Absent when the operation failed before the asset was known."""
    amount: Decimal


class ClaimPredicate(Model):
    """The condition under which a claimant can claim a claimable balance.

    Exactly one group of fields is set: `unconditional`; `and_`; `or_`; `not_`;
    `abs_before` with `abs_before_epoch`; or `rel_before`.
    """

    unconditional: bool | None = None
    and_: list["ClaimPredicate"] | None = Field(default=None, alias="and")
    or_: list["ClaimPredicate"] | None = Field(default=None, alias="or")
    not_: "ClaimPredicate | None" = Field(default=None, alias="not")
    abs_before: str | None = None
    """The deadline as an RFC 3339 time. It can lie beyond the year 9999."""
    abs_before_epoch: int | None = None
    """The deadline in Unix seconds."""
    rel_before: int | None = None
    """Seconds after the ledger that created the claimable balance."""


class Claimant(Model):
    """An account that can claim a claimable balance, and its condition."""

    destination: str
    predicate: ClaimPredicate
