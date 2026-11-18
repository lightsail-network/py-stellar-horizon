"""Path finding: `GET /paths/strict-receive` and `GET /paths/strict-send`."""

from decimal import Decimal

from .base import Model
from .common import Asset

__all__ = ["Path"]


class Path(Model):
    """A way to pay one asset with another: `GET /paths/strict-receive` and `-send`."""

    source_asset_type: str
    source_asset_code: str | None = None
    source_asset_issuer: str | None = None
    source_amount: Decimal
    destination_asset_type: str
    destination_asset_code: str | None = None
    destination_asset_issuer: str | None = None
    destination_amount: Decimal
    path: list[Asset]
    """The assets in between, in order; empty for a direct exchange."""
