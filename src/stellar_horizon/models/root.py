"""The root resource, `GET /`."""

from datetime import datetime

from ._fields import Links
from .base import Model

__all__ = ["Root"]


class Root(Model):
    """What a Horizon server reports about itself and the network."""

    links: Links
    horizon_version: str
    core_version: str
    ingest_latest_ledger: int
    history_latest_ledger: int
    """The latest ledger in the history this server serves."""
    history_latest_ledger_closed_at: datetime
    history_elder_ledger: int
    """The oldest ledger in the history this server keeps."""
    core_latest_ledger: int
    network_passphrase: str
    current_protocol_version: int
    supported_protocol_version: int | None = None
    core_supported_protocol_version: int
