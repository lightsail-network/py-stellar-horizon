"""Operations, `GET /operations` and the routes scoped to one resource.

Horizon tells operation types apart by number, `type_i`, and by name, `type`. The class
of an operation is chosen by `type_i`, which never changes. `type` is kept as Horizon
sent it: one name has changed already, and the class still reads the operation. A number
that this package does not know gives `UnknownOperation`.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, Tag

from ._fields import Base64Bytes, Links, NullAsEmpty, numbers_of, tag_by_number
from .base import Model
from .common import Asset, AssetAmount, Claimant, Price
from .transaction import Transaction

__all__ = [
    "AccountMergeOperation",
    "AllowTrustOperation",
    "AssetContractBalanceChange",
    "BaseOperation",
    "BeginSponsoringFutureReservesOperation",
    "BumpSequenceOperation",
    "ChangeTrustOperation",
    "ClaimClaimableBalanceOperation",
    "ClawbackClaimableBalanceOperation",
    "ClawbackOperation",
    "CreateAccountOperation",
    "CreateClaimableBalanceOperation",
    "CreatePassiveSellOfferOperation",
    "EndSponsoringFutureReservesOperation",
    "ExtendFootprintTTLOperation",
    "HostFunctionParameter",
    "InflationOperation",
    "InvokeHostFunctionOperation",
    "LiquidityPoolDepositOperation",
    "LiquidityPoolWithdrawOperation",
    "ManageBuyOfferOperation",
    "ManageDataOperation",
    "ManageSellOfferOperation",
    "Operation",
    "PathPaymentStrictReceiveOperation",
    "PathPaymentStrictSendOperation",
    "PaymentOperation",
    "RestoreFootprintOperation",
    "RevokeSponsorshipOperation",
    "SetOptionsOperation",
    "SetTrustLineFlagsOperation",
    "UnknownOperation",
]


class BaseOperation(Model):
    """The fields that every operation has.

    Every operation class also has `type_i`, the number of its type: the value of the
    operation type in the protocol's XDR. Tell the types apart with `isinstance` or
    `match`; comparing `type_i` does not narrow the type, because `UnknownOperation`
    can have any number.
    """

    links: Links
    id: str
    paging_token: str
    transaction_successful: bool
    source_account: str
    source_account_muxed: str | None = None
    source_account_muxed_id: int | None = None
    type: str
    """The name of the type, as Horizon sent it."""
    created_at: datetime
    transaction_hash: str
    transaction: Transaction | None = None
    """The transaction, when it was requested with `join_transactions=True`."""
    sponsor: str | None = None


class HostFunctionParameter(Model):
    """An argument of a host function, as base64 XDR of an `SCVal`."""

    value: str
    type: str


class AssetContractBalanceChange(Model):
    """A change of a Stellar Asset Contract balance that a contract call caused."""

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    type: str
    """`transfer`, `mint`, `clawback` or `burn`."""
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    amount: Decimal
    destination_muxed_id: int | None = None


class CreateAccountOperation(BaseOperation):
    """Creates and funds an account."""

    type_i: Literal[0]

    starting_balance: Decimal
    funder: str
    funder_muxed: str | None = None
    funder_muxed_id: int | None = None
    account: str


class PaymentOperation(BaseOperation):
    """Sends an amount of an asset to an account."""

    type_i: Literal[1]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    from_: str = Field(alias="from")
    from_muxed: str | None = None
    from_muxed_id: int | None = None
    to: str
    to_muxed: str | None = None
    to_muxed_id: int | None = None
    amount: Decimal


class PathPaymentStrictReceiveOperation(BaseOperation):
    """Sends an asset so that the destination receives an exact amount of another."""

    type_i: Literal[2]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    from_: str = Field(alias="from")
    from_muxed: str | None = None
    from_muxed_id: int | None = None
    to: str
    to_muxed: str | None = None
    to_muxed_id: int | None = None
    amount: Decimal
    path: list[Asset]
    source_amount: Decimal
    source_max: Decimal
    source_asset_type: str
    source_asset_code: str | None = None
    source_asset_issuer: str | None = None


class ManageSellOfferOperation(BaseOperation):
    """Creates, changes or removes an offer to sell an asset."""

    type_i: Literal[3]

    amount: Decimal
    price: Decimal
    price_r: Price
    buying_asset_type: str
    buying_asset_code: str | None = None
    buying_asset_issuer: str | None = None
    selling_asset_type: str
    selling_asset_code: str | None = None
    selling_asset_issuer: str | None = None
    offer_id: str


class CreatePassiveSellOfferOperation(BaseOperation):
    """Creates an offer that does not take offers at the same price."""

    type_i: Literal[4]

    amount: Decimal
    price: Decimal
    price_r: Price
    buying_asset_type: str
    buying_asset_code: str | None = None
    buying_asset_issuer: str | None = None
    selling_asset_type: str
    selling_asset_code: str | None = None
    selling_asset_issuer: str | None = None


class SetOptionsOperation(BaseOperation):
    """Changes the settings of an account."""

    type_i: Literal[5]

    home_domain: str | None = None
    inflation_dest: str | None = None
    master_key_weight: int | None = None
    signer_key: str | None = None
    signer_weight: int | None = None
    set_flags: list[int] | None = None
    set_flags_s: list[str] | None = None
    clear_flags: list[int] | None = None
    clear_flags_s: list[str] | None = None
    low_threshold: int | None = None
    med_threshold: int | None = None
    high_threshold: int | None = None


class ChangeTrustOperation(BaseOperation):
    """Creates, changes or removes a trustline."""

    type_i: Literal[6]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    liquidity_pool_id: str | None = None
    limit: Decimal
    trustee: str | None = None
    trustor: str
    trustor_muxed: str | None = None
    trustor_muxed_id: int | None = None


class AllowTrustOperation(BaseOperation):
    """Authorizes a trustline. Replaced by `set_trust_line_flags`."""

    type_i: Literal[7]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    trustee: str
    trustee_muxed: str | None = None
    trustee_muxed_id: int | None = None
    trustor: str
    authorize: bool
    authorize_to_maintain_liabilities: bool


class AccountMergeOperation(BaseOperation):
    """Removes an account and sends its lumens to another."""

    type_i: Literal[8]

    account: str
    account_muxed: str | None = None
    account_muxed_id: int | None = None
    into: str
    into_muxed: str | None = None
    into_muxed_id: int | None = None


class InflationOperation(BaseOperation):
    """Ran inflation, before protocol 12 retired it."""

    type_i: Literal[9]


class ManageDataOperation(BaseOperation):
    """Sets or removes a data entry of an account."""

    type_i: Literal[10]

    name: str
    value: Base64Bytes
    """Empty when the entry was removed."""


class BumpSequenceOperation(BaseOperation):
    """Raises the sequence number of an account."""

    type_i: Literal[11]

    bump_to: int


class ManageBuyOfferOperation(BaseOperation):
    """Creates, changes or removes an offer to buy an asset."""

    type_i: Literal[12]

    amount: Decimal
    price: Decimal
    price_r: Price
    buying_asset_type: str
    buying_asset_code: str | None = None
    buying_asset_issuer: str | None = None
    selling_asset_type: str
    selling_asset_code: str | None = None
    selling_asset_issuer: str | None = None
    offer_id: str


class PathPaymentStrictSendOperation(BaseOperation):
    """Sends an exact amount of an asset, which the destination receives as another."""

    type_i: Literal[13]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    from_: str = Field(alias="from")
    from_muxed: str | None = None
    from_muxed_id: int | None = None
    to: str
    to_muxed: str | None = None
    to_muxed_id: int | None = None
    amount: Decimal
    path: list[Asset]
    source_amount: Decimal
    destination_min: Decimal
    source_asset_type: str
    source_asset_code: str | None = None
    source_asset_issuer: str | None = None


class CreateClaimableBalanceOperation(BaseOperation):
    """Creates a claimable balance."""

    type_i: Literal[14]

    asset: str
    """`native` or `CODE:ISSUER`."""
    amount: Decimal
    claimants: list[Claimant]


class ClaimClaimableBalanceOperation(BaseOperation):
    """Claims a claimable balance."""

    type_i: Literal[15]

    balance_id: str
    claimant: str
    claimant_muxed: str | None = None
    claimant_muxed_id: int | None = None


class BeginSponsoringFutureReservesOperation(BaseOperation):
    """Starts paying the reserves of another account."""

    type_i: Literal[16]

    sponsored_id: str


class EndSponsoringFutureReservesOperation(BaseOperation):
    """Ends the sponsorship that `begin_sponsoring_future_reserves` started."""

    type_i: Literal[17]

    begin_sponsor: str | None = None
    begin_sponsor_muxed: str | None = None
    begin_sponsor_muxed_id: int | None = None


class RevokeSponsorshipOperation(BaseOperation):
    """Removes or moves the sponsorship of a ledger entry or a signer."""

    type_i: Literal[18]

    account_id: str | None = None
    claimable_balance_id: str | None = None
    data_account_id: str | None = None
    data_name: str | None = None
    offer_id: str | None = None
    trustline_account_id: str | None = None
    trustline_liquidity_pool_id: str | None = None
    trustline_asset: str | None = None
    signer_account_id: str | None = None
    signer_key: str | None = None


class ClawbackOperation(BaseOperation):
    """Takes back an amount of an asset from an account."""

    type_i: Literal[19]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    from_: str = Field(alias="from")
    from_muxed: str | None = None
    from_muxed_id: int | None = None
    amount: Decimal


class ClawbackClaimableBalanceOperation(BaseOperation):
    """Takes back a claimable balance."""

    type_i: Literal[20]

    balance_id: str


class SetTrustLineFlagsOperation(BaseOperation):
    """Sets or clears the flags of a trustline."""

    type_i: Literal[21]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    trustor: str
    set_flags: list[int] | None = None
    set_flags_s: list[str] | None = None
    clear_flags: list[int] | None = None
    clear_flags_s: list[str] | None = None


class LiquidityPoolDepositOperation(BaseOperation):
    """Deposits assets into a liquidity pool."""

    type_i: Literal[22]

    liquidity_pool_id: str
    reserves_max: list[AssetAmount]
    min_price: Decimal
    min_price_r: Price
    max_price: Decimal
    max_price_r: Price
    reserves_deposited: list[AssetAmount]
    shares_received: Decimal


class LiquidityPoolWithdrawOperation(BaseOperation):
    """Withdraws assets from a liquidity pool."""

    type_i: Literal[23]

    liquidity_pool_id: str
    reserves_min: list[AssetAmount]
    shares: Decimal
    reserves_received: list[AssetAmount]


class InvokeHostFunctionOperation(BaseOperation):
    """Calls a smart contract, deploys one, or uploads its code."""

    type_i: Literal[24]

    function: str
    parameters: Annotated[list[HostFunctionParameter], NullAsEmpty]
    address: str
    salt: str
    asset_balance_changes: Annotated[list[AssetContractBalanceChange], NullAsEmpty]
    """Movements of Stellar Asset Contract balances that the call caused."""


class ExtendFootprintTTLOperation(BaseOperation):
    """Extends how long contract data and code live.

    Older Horizon releases named it `bump_footprint_expiration`.
    """

    type_i: Literal[25]

    extend_to: int


class RestoreFootprintOperation(BaseOperation):
    """Restores archived contract data and code."""

    type_i: Literal[26]


class UnknownOperation(BaseOperation):
    """An operation whose `type_i` this package does not know.

    A newer Horizon may add types. The fields of such an operation are in
    `model_extra`.
    """

    type_i: int


def _operation_tag(value: Any) -> str:  # noqa: ANN401
    return tag_by_number(value, _OPERATION_NUMBERS)


Operation = Annotated[
    Annotated[CreateAccountOperation, Tag("0")]
    | Annotated[PaymentOperation, Tag("1")]
    | Annotated[PathPaymentStrictReceiveOperation, Tag("2")]
    | Annotated[ManageSellOfferOperation, Tag("3")]
    | Annotated[CreatePassiveSellOfferOperation, Tag("4")]
    | Annotated[SetOptionsOperation, Tag("5")]
    | Annotated[ChangeTrustOperation, Tag("6")]
    | Annotated[AllowTrustOperation, Tag("7")]
    | Annotated[AccountMergeOperation, Tag("8")]
    | Annotated[InflationOperation, Tag("9")]
    | Annotated[ManageDataOperation, Tag("10")]
    | Annotated[BumpSequenceOperation, Tag("11")]
    | Annotated[ManageBuyOfferOperation, Tag("12")]
    | Annotated[PathPaymentStrictSendOperation, Tag("13")]
    | Annotated[CreateClaimableBalanceOperation, Tag("14")]
    | Annotated[ClaimClaimableBalanceOperation, Tag("15")]
    | Annotated[BeginSponsoringFutureReservesOperation, Tag("16")]
    | Annotated[EndSponsoringFutureReservesOperation, Tag("17")]
    | Annotated[RevokeSponsorshipOperation, Tag("18")]
    | Annotated[ClawbackOperation, Tag("19")]
    | Annotated[ClawbackClaimableBalanceOperation, Tag("20")]
    | Annotated[SetTrustLineFlagsOperation, Tag("21")]
    | Annotated[LiquidityPoolDepositOperation, Tag("22")]
    | Annotated[LiquidityPoolWithdrawOperation, Tag("23")]
    | Annotated[InvokeHostFunctionOperation, Tag("24")]
    | Annotated[ExtendFootprintTTLOperation, Tag("25")]
    | Annotated[RestoreFootprintOperation, Tag("26")]
    | Annotated[UnknownOperation, Tag("unknown")],
    Discriminator(_operation_tag),
]
"""Any operation. Use `isinstance` or `match` to tell the types apart."""

_OPERATION_NUMBERS = numbers_of(Operation)
"""The type numbers that have a class of their own: those tagged in `Operation`."""
