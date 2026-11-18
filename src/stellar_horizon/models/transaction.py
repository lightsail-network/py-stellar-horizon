"""Transactions, `GET /transactions` and the routes scoped to one resource."""

from datetime import datetime
from typing import Literal

from ._fields import Base64Bytes, Links
from .base import Model

__all__ = [
    "EnqueueResult",
    "FeeBumpTransaction",
    "InnerTransaction",
    "LedgerBounds",
    "TimeBounds",
    "Transaction",
    "TransactionPreconditions",
]


class TimeBounds(Model):
    """The time range in which a transaction is valid, in Unix seconds."""

    min_time: int | None = None
    max_time: int | None = None
    """Can be as large as `9223372036854775807`, which no `datetime` can hold."""


class LedgerBounds(Model):
    """The ledgers in which a transaction is valid."""

    min_ledger: int
    max_ledger: int | None = None
    """Absent when there is no upper bound."""


class TransactionPreconditions(Model):
    """The conditions a transaction sets on when it is valid."""

    timebounds: TimeBounds | None = None
    ledgerbounds: LedgerBounds | None = None
    min_account_sequence: int | None = None
    min_account_sequence_age: int | None = None
    """In seconds."""
    min_account_sequence_ledger_gap: int | None = None
    extra_signers: list[str] | None = None


class FeeBumpTransaction(Model):
    """The outer transaction of a fee bump."""

    hash: str
    signatures: list[str]


class InnerTransaction(Model):
    """The transaction inside a fee bump."""

    hash: str
    signatures: list[str]
    max_fee: int


class Transaction(Model):
    """A transaction that is in a ledger, successful or not."""

    links: Links
    id: str
    paging_token: str
    successful: bool
    hash: str
    ledger: int
    created_at: datetime
    source_account: str
    account_muxed: str | None = None
    account_muxed_id: int | None = None
    source_account_sequence: int
    fee_account: str
    fee_account_muxed: str | None = None
    fee_account_muxed_id: int | None = None
    fee_charged: int
    max_fee: int
    operation_count: int
    envelope_xdr: str
    result_xdr: str
    result_meta_xdr: str | None = None
    """Absent when the server runs with `--skip-txmeta`."""
    fee_meta_xdr: str
    memo_type: str
    memo: str | None = None
    memo_bytes: Base64Bytes | None = None
    """The bytes of a text memo, which need not be valid UTF-8."""
    signatures: list[str]
    preconditions: TransactionPreconditions | None = None
    fee_bump_transaction: FeeBumpTransaction | None = None
    inner_transaction: InnerTransaction | None = None


class EnqueueResult(Model):
    """What `POST /transactions_async` answers: whether stellar-core took the envelope.

    Only `PENDING` means that the transaction is on its way into a ledger. Horizon sends
    this body with the status `201` for `PENDING`, `409` for `DUPLICATE`, `503` for
    `TRY_AGAIN_LATER` and `400` for `ERROR`; it is read as a result whatever the status.
    """

    tx_status: Literal["PENDING", "DUPLICATE", "TRY_AGAIN_LATER", "ERROR"]
    """
    - `PENDING`: stellar-core took the transaction and will try to put it in a ledger.
    - `DUPLICATE`: stellar-core already has this transaction, from an earlier
      submission.
    - `TRY_AGAIN_LATER`: stellar-core is full, or already has a transaction from the
      same source account; send the envelope again later.
    - `ERROR`: stellar-core refused the transaction; see `error_result_xdr`.
    """
    hash: str
    """The hash of the transaction, in hex."""
    error_result_xdr: str | None = None
    """For `ERROR`, the `TransactionResult` as base64 XDR, which says why."""
