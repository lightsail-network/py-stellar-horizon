"""The body of an error response."""

from typing import Any

from .base import Model

__all__ = ["Problem", "TransactionResultCodes"]

_PREFIX = "https://stellar.org/horizon-errors/"


class Problem(Model):
    """An `application/problem+json` body, which Horizon sends with every error."""

    type: str
    """The problem type, a URL such as `https://stellar.org/horizon-errors/not_found`."""
    title: str
    status: int
    detail: str | None = None
    extras: dict[str, Any] | None = None

    @property
    def short_type(self) -> str:
        """The problem type without its URL prefix, such as `not_found`."""
        return self.type.removeprefix(_PREFIX)


class TransactionResultCodes(Model):
    """The result codes of a failed transaction, such as `tx_bad_seq`."""

    transaction: str
    inner_transaction: str | None = None
    """The code of the inner transaction of a fee bump."""
    operations: list[str] | None = None
    """One code per operation, such as `op_underfunded`."""
