"""Effects, `GET /effects` and the routes scoped to one resource.

An effect is one change that an operation made, such as an account credited or a
trustline created. Like operations, effects are told apart by number, `type_i`, which
chooses the class, and by name, `type`, which is kept as Horizon sent it. A number that
this package does not know gives `UnknownEffect`.

The fields of each class follow the Go types of Horizon's responses, in
`protocols/horizon/effects` of go-stellar-sdk v0.9.0, the version Horizon 30.0.1 uses:
[effects/main.go](https://github.com/stellar/go-stellar-sdk/blob/5410d3410e212331399d1518cc13150279969dac/protocols/horizon/effects/main.go).
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import Discriminator, Tag

from ._fields import Base64Bytes, Links, numbers_of, tag_by_number
from .base import Model
from .common import AssetAmount, ClaimPredicate

__all__ = [
    "AccountCreatedEffect",
    "AccountCreditedEffect",
    "AccountDebitedEffect",
    "AccountFlagsUpdatedEffect",
    "AccountHomeDomainUpdatedEffect",
    "AccountInflationDestinationUpdatedEffect",
    "AccountRemovedEffect",
    "AccountSponsorshipCreatedEffect",
    "AccountSponsorshipRemovedEffect",
    "AccountSponsorshipUpdatedEffect",
    "AccountThresholdsUpdatedEffect",
    "BaseEffect",
    "ClaimableBalanceClaimantCreatedEffect",
    "ClaimableBalanceClaimedEffect",
    "ClaimableBalanceClawedBackEffect",
    "ClaimableBalanceCreatedEffect",
    "ClaimableBalanceSponsorshipCreatedEffect",
    "ClaimableBalanceSponsorshipRemovedEffect",
    "ClaimableBalanceSponsorshipUpdatedEffect",
    "ContractCreditedEffect",
    "ContractDebitedEffect",
    "DataCreatedEffect",
    "DataRemovedEffect",
    "DataSponsorshipCreatedEffect",
    "DataSponsorshipRemovedEffect",
    "DataSponsorshipUpdatedEffect",
    "DataUpdatedEffect",
    "Effect",
    "EffectLiquidityPool",
    "LiquidityPoolClaimableAssetAmount",
    "LiquidityPoolCreatedEffect",
    "LiquidityPoolDepositedEffect",
    "LiquidityPoolRemovedEffect",
    "LiquidityPoolRevokedEffect",
    "LiquidityPoolTradeEffect",
    "LiquidityPoolWithdrewEffect",
    "SequenceBumpedEffect",
    "SignerCreatedEffect",
    "SignerRemovedEffect",
    "SignerSponsorshipCreatedEffect",
    "SignerSponsorshipRemovedEffect",
    "SignerSponsorshipUpdatedEffect",
    "SignerUpdatedEffect",
    "TradeEffect",
    "TrustlineAuthorizedEffect",
    "TrustlineAuthorizedToMaintainLiabilitiesEffect",
    "TrustlineCreatedEffect",
    "TrustlineDeauthorizedEffect",
    "TrustlineFlagsUpdatedEffect",
    "TrustlineRemovedEffect",
    "TrustlineSponsorshipCreatedEffect",
    "TrustlineSponsorshipRemovedEffect",
    "TrustlineSponsorshipUpdatedEffect",
    "TrustlineUpdatedEffect",
    "UnknownEffect",
]


class BaseEffect(Model):
    """The fields that every effect has.

    Every effect class also has `type_i`, the number of its type. Tell the types apart
    with `isinstance` or `match`; comparing `type_i` does not narrow the type, because
    `UnknownEffect` can have any number.
    """

    links: Links
    id: str
    paging_token: str
    account: str
    """The account that the effect changed, or that made the change."""
    account_muxed: str | None = None
    account_muxed_id: int | None = None
    type: str
    """The name of the type, as Horizon sent it."""
    created_at: datetime
    """When the ledger of the effect closed."""


class EffectLiquidityPool(Model):
    """A liquidity pool as an effect describes it, after the change.

    It has the fields of `LiquidityPool` without its links, paging token and time of
    the last change. The other SDKs have the same separate type: `effects.LiquidityPool`
    in Go and Java, `LiquidityPoolEffectRecord` in JavaScript. Go and Java tell the two
    apart by package; this package exports every model from one namespace, so the name
    says it, as in JavaScript.
    """

    id: str
    fee_bp: int
    """The fee, in basis points."""
    type: str
    total_trustlines: int
    total_shares: Decimal
    reserves: list[AssetAmount]


class LiquidityPoolClaimableAssetAmount(Model):
    """A reserve of revoked pool shares, and the claimable balance that holds it."""

    asset: str
    amount: Decimal
    claimable_balance_id: str


class AccountCreatedEffect(BaseEffect):
    """An account was created."""

    type_i: Literal[0]

    starting_balance: Decimal


class AccountRemovedEffect(BaseEffect):
    """An account was merged into another."""

    type_i: Literal[1]


class AccountCreditedEffect(BaseEffect):
    """An account received an amount of an asset."""

    type_i: Literal[2]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    amount: Decimal


class AccountDebitedEffect(BaseEffect):
    """An account sent an amount of an asset."""

    type_i: Literal[3]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    amount: Decimal


class AccountThresholdsUpdatedEffect(BaseEffect):
    """The thresholds of an account changed."""

    type_i: Literal[4]

    low_threshold: int
    med_threshold: int
    high_threshold: int


class AccountHomeDomainUpdatedEffect(BaseEffect):
    """The home domain of an account changed."""

    type_i: Literal[5]

    home_domain: str


class AccountFlagsUpdatedEffect(BaseEffect):
    """The flags of an account changed."""

    type_i: Literal[6]

    auth_required_flag: bool | None = None
    auth_revokable_flag: bool | None = None
    """Never sent: Horizon stores this flag under another name, `auth_revocable_flag`,
    and drops it when it writes the effect. The field follows Horizon's own type."""


class AccountInflationDestinationUpdatedEffect(BaseEffect):
    """The inflation destination of an account changed."""

    type_i: Literal[7]


class SignerCreatedEffect(BaseEffect):
    """A signer was added to an account."""

    type_i: Literal[10]

    weight: int
    public_key: str
    key: str


class SignerRemovedEffect(BaseEffect):
    """A signer was removed from an account."""

    type_i: Literal[11]

    weight: int
    public_key: str
    key: str


class SignerUpdatedEffect(BaseEffect):
    """The weight of a signer of an account changed."""

    type_i: Literal[12]

    weight: int
    public_key: str
    key: str


class TrustlineCreatedEffect(BaseEffect):
    """A trustline to an asset or a liquidity pool was created."""

    type_i: Literal[20]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    liquidity_pool_id: str | None = None
    limit: Decimal


class TrustlineRemovedEffect(BaseEffect):
    """A trustline was removed."""

    type_i: Literal[21]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    liquidity_pool_id: str | None = None
    limit: Decimal


class TrustlineUpdatedEffect(BaseEffect):
    """The limit of a trustline changed."""

    type_i: Literal[22]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    liquidity_pool_id: str | None = None
    limit: Decimal


class TrustlineAuthorizedEffect(BaseEffect):
    """An issuer authorized a trustline with `allow_trust`.

    The issuer is the account of the effect.
    """

    type_i: Literal[23]

    trustor: str
    asset_type: str
    asset_code: str | None = None


class TrustlineDeauthorizedEffect(BaseEffect):
    """An issuer removed the authorization of a trustline with `allow_trust`.

    The issuer is the account of the effect.
    """

    type_i: Literal[24]

    trustor: str
    asset_type: str
    asset_code: str | None = None


class TrustlineAuthorizedToMaintainLiabilitiesEffect(BaseEffect):
    """An issuer let a trustline keep its offers, and nothing more, with `allow_trust`.

    The issuer is the account of the effect.
    """

    type_i: Literal[25]

    trustor: str
    asset_type: str
    asset_code: str | None = None


class TrustlineFlagsUpdatedEffect(BaseEffect):
    """An issuer changed the flags of a trustline."""

    type_i: Literal[26]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    trustor: str
    authorized_flag: bool | None = None
    authorized_to_maintain_liabilites_flag: bool | None = None
    """Never sent: Horizon stores this flag as
    `authorized_to_maintain_liabilities_flag` and drops it when it writes the effect.
    The field follows Horizon's own type, misspelling included."""
    clawback_enabled_flag: bool | None = None


class TradeEffect(BaseEffect):
    """An offer was matched: by an offer operation or a path payment."""

    type_i: Literal[33]

    seller: str
    seller_muxed: str | None = None
    seller_muxed_id: int | None = None
    offer_id: str
    sold_amount: Decimal
    sold_asset_type: str
    sold_asset_code: str | None = None
    sold_asset_issuer: str | None = None
    bought_amount: Decimal
    bought_asset_type: str
    bought_asset_code: str | None = None
    bought_asset_issuer: str | None = None


class DataCreatedEffect(BaseEffect):
    """A data entry was added to an account."""

    type_i: Literal[40]

    name: str
    value: Base64Bytes


class DataRemovedEffect(BaseEffect):
    """A data entry was removed from an account."""

    type_i: Literal[41]

    name: str


class DataUpdatedEffect(BaseEffect):
    """The value of a data entry changed."""

    type_i: Literal[42]

    name: str
    value: Base64Bytes


class SequenceBumpedEffect(BaseEffect):
    """The sequence number of an account was raised."""

    type_i: Literal[43]

    new_seq: int


class ClaimableBalanceCreatedEffect(BaseEffect):
    """A claimable balance was created."""

    type_i: Literal[50]

    asset: str
    balance_id: str
    amount: Decimal


class ClaimableBalanceClaimantCreatedEffect(BaseEffect):
    """A claimant of a new claimable balance; the account of the effect."""

    type_i: Literal[51]

    asset: str
    balance_id: str
    amount: Decimal
    predicate: ClaimPredicate


class ClaimableBalanceClaimedEffect(BaseEffect):
    """A claimable balance was claimed."""

    type_i: Literal[52]

    asset: str
    balance_id: str
    amount: Decimal


class AccountSponsorshipCreatedEffect(BaseEffect):
    """An account was created with its reserve paid by a sponsor."""

    type_i: Literal[60]

    sponsor: str


class AccountSponsorshipUpdatedEffect(BaseEffect):
    """The sponsorship of an account moved to another sponsor."""

    type_i: Literal[61]

    former_sponsor: str
    new_sponsor: str


class AccountSponsorshipRemovedEffect(BaseEffect):
    """An account no longer has a sponsor."""

    type_i: Literal[62]

    former_sponsor: str


class TrustlineSponsorshipCreatedEffect(BaseEffect):
    """A trustline was created with its reserve paid by a sponsor."""

    type_i: Literal[63]

    asset_type: str
    asset: str | None = None
    liquidity_pool_id: str | None = None
    sponsor: str


class TrustlineSponsorshipUpdatedEffect(BaseEffect):
    """The sponsorship of a trustline moved to another sponsor."""

    type_i: Literal[64]

    asset_type: str
    asset: str | None = None
    liquidity_pool_id: str | None = None
    former_sponsor: str
    new_sponsor: str


class TrustlineSponsorshipRemovedEffect(BaseEffect):
    """A trustline no longer has a sponsor."""

    type_i: Literal[65]

    asset_type: str
    asset: str | None = None
    liquidity_pool_id: str | None = None
    former_sponsor: str


class DataSponsorshipCreatedEffect(BaseEffect):
    """A data entry was created with its reserve paid by a sponsor."""

    type_i: Literal[66]

    data_name: str
    sponsor: str


class DataSponsorshipUpdatedEffect(BaseEffect):
    """The sponsorship of a data entry moved to another sponsor."""

    type_i: Literal[67]

    data_name: str
    former_sponsor: str
    new_sponsor: str


class DataSponsorshipRemovedEffect(BaseEffect):
    """A data entry no longer has a sponsor."""

    type_i: Literal[68]

    data_name: str
    former_sponsor: str


class ClaimableBalanceSponsorshipCreatedEffect(BaseEffect):
    """A claimable balance was created with its reserve paid by a sponsor."""

    type_i: Literal[69]

    balance_id: str
    sponsor: str


class ClaimableBalanceSponsorshipUpdatedEffect(BaseEffect):
    """The sponsorship of a claimable balance moved to another sponsor."""

    type_i: Literal[70]

    balance_id: str
    former_sponsor: str
    new_sponsor: str


class ClaimableBalanceSponsorshipRemovedEffect(BaseEffect):
    """A claimable balance no longer has a sponsor."""

    type_i: Literal[71]

    balance_id: str
    former_sponsor: str


class SignerSponsorshipCreatedEffect(BaseEffect):
    """A signer was added with its reserve paid by a sponsor."""

    type_i: Literal[72]

    signer: str
    sponsor: str


class SignerSponsorshipUpdatedEffect(BaseEffect):
    """The sponsorship of a signer moved to another sponsor."""

    type_i: Literal[73]

    signer: str
    former_sponsor: str
    new_sponsor: str


class SignerSponsorshipRemovedEffect(BaseEffect):
    """A signer no longer has a sponsor."""

    type_i: Literal[74]

    signer: str
    former_sponsor: str


class ClaimableBalanceClawedBackEffect(BaseEffect):
    """The issuer of an asset clawed a claimable balance back."""

    type_i: Literal[80]

    balance_id: str


class LiquidityPoolDepositedEffect(BaseEffect):
    """An account deposited reserves into a liquidity pool."""

    type_i: Literal[90]

    liquidity_pool: EffectLiquidityPool
    reserves_deposited: list[AssetAmount]
    shares_received: Decimal


class LiquidityPoolWithdrewEffect(BaseEffect):
    """An account withdrew reserves from a liquidity pool."""

    type_i: Literal[91]

    liquidity_pool: EffectLiquidityPool
    reserves_received: list[AssetAmount]
    shares_redeemed: Decimal


class LiquidityPoolTradeEffect(BaseEffect):
    """A liquidity pool took part in a trade."""

    type_i: Literal[92]

    liquidity_pool: EffectLiquidityPool
    sold: AssetAmount
    bought: AssetAmount


class LiquidityPoolCreatedEffect(BaseEffect):
    """A liquidity pool was created, by its first trustline."""

    type_i: Literal[93]

    liquidity_pool: EffectLiquidityPool


class LiquidityPoolRemovedEffect(BaseEffect):
    """A liquidity pool was removed, with its last trustline."""

    type_i: Literal[94]

    liquidity_pool_id: str


class LiquidityPoolRevokedEffect(BaseEffect):
    """An issuer revoked the authorization of an account that held pool shares.

    The shares were redeemed, and each reserve went to a claimable balance.
    """

    type_i: Literal[95]

    liquidity_pool: EffectLiquidityPool
    reserves_revoked: list[LiquidityPoolClaimableAssetAmount]
    shares_revoked: Decimal


class ContractCreditedEffect(BaseEffect):
    """A contract received an amount of an asset."""

    type_i: Literal[96]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    contract: str
    contract_muxed: str | None = None
    contract_muxed_id: int | None = None
    amount: Decimal


class ContractDebitedEffect(BaseEffect):
    """A contract sent an amount of an asset."""

    type_i: Literal[97]

    asset_type: str
    asset_code: str | None = None
    asset_issuer: str | None = None
    contract: str
    amount: Decimal


class UnknownEffect(BaseEffect):
    """An effect whose `type_i` this package does not know.

    A newer Horizon may add types. The fields of such an effect are in `model_extra`.
    """

    type_i: int


def _effect_tag(value: Any) -> str:  # noqa: ANN401
    return tag_by_number(value, _EFFECT_NUMBERS)


Effect = Annotated[
    Annotated[AccountCreatedEffect, Tag("0")]
    | Annotated[AccountRemovedEffect, Tag("1")]
    | Annotated[AccountCreditedEffect, Tag("2")]
    | Annotated[AccountDebitedEffect, Tag("3")]
    | Annotated[AccountThresholdsUpdatedEffect, Tag("4")]
    | Annotated[AccountHomeDomainUpdatedEffect, Tag("5")]
    | Annotated[AccountFlagsUpdatedEffect, Tag("6")]
    | Annotated[AccountInflationDestinationUpdatedEffect, Tag("7")]
    | Annotated[SignerCreatedEffect, Tag("10")]
    | Annotated[SignerRemovedEffect, Tag("11")]
    | Annotated[SignerUpdatedEffect, Tag("12")]
    | Annotated[TrustlineCreatedEffect, Tag("20")]
    | Annotated[TrustlineRemovedEffect, Tag("21")]
    | Annotated[TrustlineUpdatedEffect, Tag("22")]
    | Annotated[TrustlineAuthorizedEffect, Tag("23")]
    | Annotated[TrustlineDeauthorizedEffect, Tag("24")]
    | Annotated[TrustlineAuthorizedToMaintainLiabilitiesEffect, Tag("25")]
    | Annotated[TrustlineFlagsUpdatedEffect, Tag("26")]
    | Annotated[TradeEffect, Tag("33")]
    | Annotated[DataCreatedEffect, Tag("40")]
    | Annotated[DataRemovedEffect, Tag("41")]
    | Annotated[DataUpdatedEffect, Tag("42")]
    | Annotated[SequenceBumpedEffect, Tag("43")]
    | Annotated[ClaimableBalanceCreatedEffect, Tag("50")]
    | Annotated[ClaimableBalanceClaimantCreatedEffect, Tag("51")]
    | Annotated[ClaimableBalanceClaimedEffect, Tag("52")]
    | Annotated[AccountSponsorshipCreatedEffect, Tag("60")]
    | Annotated[AccountSponsorshipUpdatedEffect, Tag("61")]
    | Annotated[AccountSponsorshipRemovedEffect, Tag("62")]
    | Annotated[TrustlineSponsorshipCreatedEffect, Tag("63")]
    | Annotated[TrustlineSponsorshipUpdatedEffect, Tag("64")]
    | Annotated[TrustlineSponsorshipRemovedEffect, Tag("65")]
    | Annotated[DataSponsorshipCreatedEffect, Tag("66")]
    | Annotated[DataSponsorshipUpdatedEffect, Tag("67")]
    | Annotated[DataSponsorshipRemovedEffect, Tag("68")]
    | Annotated[ClaimableBalanceSponsorshipCreatedEffect, Tag("69")]
    | Annotated[ClaimableBalanceSponsorshipUpdatedEffect, Tag("70")]
    | Annotated[ClaimableBalanceSponsorshipRemovedEffect, Tag("71")]
    | Annotated[SignerSponsorshipCreatedEffect, Tag("72")]
    | Annotated[SignerSponsorshipUpdatedEffect, Tag("73")]
    | Annotated[SignerSponsorshipRemovedEffect, Tag("74")]
    | Annotated[ClaimableBalanceClawedBackEffect, Tag("80")]
    | Annotated[LiquidityPoolDepositedEffect, Tag("90")]
    | Annotated[LiquidityPoolWithdrewEffect, Tag("91")]
    | Annotated[LiquidityPoolTradeEffect, Tag("92")]
    | Annotated[LiquidityPoolCreatedEffect, Tag("93")]
    | Annotated[LiquidityPoolRemovedEffect, Tag("94")]
    | Annotated[LiquidityPoolRevokedEffect, Tag("95")]
    | Annotated[ContractCreditedEffect, Tag("96")]
    | Annotated[ContractDebitedEffect, Tag("97")]
    | Annotated[UnknownEffect, Tag("unknown")],
    Discriminator(_effect_tag),
]
"""Any effect: the class that its `type_i` names, or `UnknownEffect`."""

_EFFECT_NUMBERS = numbers_of(Effect)
"""The type numbers that have a class of their own: those tagged in `Effect`."""
