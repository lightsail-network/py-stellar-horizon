"""Accounts, `GET /accounts/{id}` and `GET /accounts`."""

from datetime import datetime
from decimal import Decimal

from ._fields import Base64Bytes, Links
from .base import Model

__all__ = [
    "Account",
    "AccountData",
    "AccountFlags",
    "AccountThresholds",
    "Balance",
    "Signer",
]


class AccountThresholds(Model):
    """The weights that signatures must reach, by operation threshold."""

    low_threshold: int
    med_threshold: int
    high_threshold: int


class AccountFlags(Model):
    """The flags an issuer sets on its account."""

    auth_required: bool
    auth_revocable: bool
    auth_immutable: bool
    auth_clawback_enabled: bool


class Balance(Model):
    """What an account holds of one asset or one liquidity pool."""

    balance: Decimal
    asset_type: str
    """`native`, `credit_alphanum4`, `credit_alphanum12` or `liquidity_pool_shares`."""
    asset_code: str | None = None
    asset_issuer: str | None = None
    liquidity_pool_id: str | None = None
    limit: Decimal | None = None
    buying_liabilities: Decimal | None = None
    selling_liabilities: Decimal | None = None
    sponsor: str | None = None
    last_modified_ledger: int | None = None
    is_authorized: bool | None = None
    is_authorized_to_maintain_liabilities: bool | None = None
    is_clawback_enabled: bool | None = None


class Signer(Model):
    """A key that can sign for an account, and its weight."""

    key: str
    weight: int
    type: str
    sponsor: str | None = None


class Account(Model):
    """An account on the ledger."""

    links: Links
    id: str
    account_id: str
    sequence: int
    sequence_ledger: int | None = None
    sequence_time: int | None = None
    """When the sequence number last changed, in Unix seconds."""
    subentry_count: int
    inflation_destination: str | None = None
    home_domain: str | None = None
    last_modified_ledger: int
    last_modified_time: datetime | None = None
    thresholds: AccountThresholds
    flags: AccountFlags
    balances: list[Balance]
    signers: list[Signer]
    data: dict[str, Base64Bytes]
    """The data entries of the account, by name."""
    num_sponsoring: int
    num_sponsored: int
    sponsor: str | None = None
    paging_token: str


class AccountData(Model):
    """One data entry of an account: `GET /accounts/{account_id}/data/{key}`."""

    value: Base64Bytes
    """The value, decoded from base64: up to 64 bytes, not necessarily text."""
    sponsor: str | None = None
    """The account that pays the reserve of the entry, if not its owner."""
