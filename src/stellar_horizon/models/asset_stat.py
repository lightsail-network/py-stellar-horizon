"""Issued assets and how much of each is held: `GET /assets`."""

from decimal import Decimal

from ._fields import Links
from .account import AccountFlags
from .base import Model

__all__ = ["AssetStat", "AssetStatAccounts", "AssetStatBalances"]


class AssetStatAccounts(Model):
    """The number of trustlines to an asset, by authorization."""

    authorized: int
    authorized_to_maintain_liabilities: int
    unauthorized: int


class AssetStatBalances(Model):
    """The amount of an asset that trustlines hold, by authorization."""

    authorized: Decimal
    authorized_to_maintain_liabilities: Decimal
    unauthorized: Decimal


class AssetStat(Model):
    """An issued asset and how much of it is held where: `GET /assets`."""

    links: Links
    asset_type: str
    asset_code: str
    asset_issuer: str
    paging_token: str
    contract_id: str | None = None
    """The Stellar Asset Contract of the asset, once it has been deployed."""
    num_claimable_balances: int
    num_liquidity_pools: int
    num_contracts: int
    accounts: AssetStatAccounts
    claimable_balances_amount: Decimal
    liquidity_pools_amount: Decimal
    contracts_amount: Decimal
    balances: AssetStatBalances
    flags: AccountFlags
    """The flags of the issuing account."""
