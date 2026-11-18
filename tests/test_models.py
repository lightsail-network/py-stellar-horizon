import base64
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from stellar_horizon.models import (
    Account,
    AccountData,
    AssetStat,
    ClaimableBalance,
    Claimant,
    CreateClaimableBalanceOperation,
    DataCreatedEffect,
    Effect,
    EnqueueResult,
    ExtendFootprintTTLOperation,
    FeeStats,
    InvokeHostFunctionOperation,
    Ledger,
    Link,
    LiquidityPool,
    LiquidityPoolRevokedEffect,
    ManageDataOperation,
    Offer,
    Operation,
    OrderBook,
    Path,
    PaymentOperation,
    Problem,
    Root,
    SequenceBumpedEffect,
    Trade,
    TradeAggregation,
    Transaction,
    UnknownEffect,
    UnknownOperation,
)
from tests.support import fixtures, load, unknown_fields

OPERATION = TypeAdapter(Operation)
EFFECT = TypeAdapter(Effect)

SINGLE: dict[str, type[BaseModel] | Any] = {
    "root.json": Root,
    "account.json": Account,
    "account_data/memo_required.json": AccountData,
    "submissions/success.json": Transaction,
    "ledger.json": Ledger,
    "fee_stats.json": FeeStats,
    "offer.json": Offer,
    "order_book.json": OrderBook,
    "claimable_balance.json": ClaimableBalance,
    "liquidity_pool.json": LiquidityPool,
    **dict.fromkeys(fixtures("submissions/async_*.json"), EnqueueResult),
    **dict.fromkeys(fixtures("operations/*.json"), Operation),
}
PAGES: dict[str, type[BaseModel] | Any] = {
    "transactions.json": Transaction,
    "transactions_failed.json": Transaction,
    "payments.json": Operation,
    "operations_joined.json": Operation,
    **dict.fromkeys(fixtures("pages/payments_*.json"), Operation),
    "operations.json": Operation,
    "ledgers.json": Ledger,
    "offers.json": Offer,
    "trades.json": Trade,
    "trades_liquidity_pool.json": Trade,
    "trade_aggregations.json": TradeAggregation,
    "paths_strict_receive.json": Path,
    "paths_strict_send.json": Path,
    "assets.json": AssetStat,
    "claimable_balances.json": ClaimableBalance,
    "liquidity_pools.json": LiquidityPool,
    **dict.fromkeys(fixtures("effects/*.json"), Effect),
}
# Read by test_errors.py.
ELSEWHERE = set(fixtures("errors/*.json"))


def cases() -> list[tuple[str, Any, Any]]:
    found: list[tuple[str, Any, Any]] = []
    for name, model in SINGLE.items():
        found.append((name, model, load(name)))
    for name, model in PAGES.items():
        for index, record in enumerate(load(name)["_embedded"]["records"]):
            found.append((f"{name}[{index}]", model, record))
    return found


CASES = cases()


def test_every_fixture_is_tested() -> None:
    tested = set(SINGLE) | set(PAGES) | ELSEWHERE
    assert set(fixtures("**/*.json")) - {"manifest.json"} == tested


@pytest.mark.parametrize(("name", "model", "body"), CASES, ids=[c[0] for c in CASES])
def test_fixture_reads_without_unknown_fields(name: str, model: Any, body: Any) -> None:
    value = TypeAdapter(model).validate_python(body)
    assert unknown_fields(value) == [], name
    assert not isinstance(value, UnknownOperation | UnknownEffect)


@pytest.mark.parametrize(("name", "model", "body"), CASES, ids=[c[0] for c in CASES])
def test_dump_reads_back_equal(name: str, model: Any, body: Any) -> None:
    adapter = TypeAdapter(model)
    value = adapter.validate_python(body)
    assert adapter.validate_python(adapter.dump_python(value, by_alias=True)) == value
    assert adapter.validate_json(adapter.dump_json(value, by_alias=True)) == value, name


def test_every_operation_type_has_a_fixture() -> None:
    seen = {load(name)["type_i"] for name in fixtures("operations/*.json")}
    assert seen == set(range(27))


def effect(name: str) -> Any:
    return load(f"effects/{name}.json")["_embedded"]["records"][0]


def test_every_effect_type_has_a_fixture_and_its_class() -> None:
    for name in fixtures("effects/*.json"):
        record = load(name)["_embedded"]["records"][0]
        value = EFFECT.validate_python(record)
        expected = record["type"].title().replace("_", "") + "Effect"
        assert type(value).__name__ == expected, name
    numbers = {effect(n.split("/")[1][:-5])["type_i"] for n in fixtures("effects/*")}
    assert len(numbers) == 50


def test_unknown_effect_keeps_its_fields() -> None:
    # Mocked: no Horizon release has type 98.
    body = effect("account_created") | {"type": "new_thing", "type_i": 98, "x": 1}
    value = EFFECT.validate_python(body)
    assert isinstance(value, UnknownEffect)
    assert value.type_i == 98
    assert value.model_extra == {"starting_balance": body["starting_balance"], "x": 1}


@pytest.mark.parametrize("type_i", [True, 8, 30])
def test_odd_effect_numbers_are_unknown(type_i: object) -> None:
    body = effect("account_created") | {"type_i": type_i}
    assert isinstance(EFFECT.validate_python(body), UnknownEffect)


def test_effect_values() -> None:
    created = EFFECT.validate_python(effect("data_created"))
    assert isinstance(created, DataCreatedEffect)
    assert isinstance(created.value, bytes)
    bumped = EFFECT.validate_python(effect("sequence_bumped"))
    assert isinstance(bumped, SequenceBumpedEffect)
    assert isinstance(bumped.new_seq, int)
    revoked = EFFECT.validate_python(effect("liquidity_pool_revoked"))
    assert isinstance(revoked, LiquidityPoolRevokedEffect)
    assert revoked.reserves_revoked[0].claimable_balance_id


def test_the_class_is_chosen_by_number_not_by_name() -> None:
    # Mocked: type 25 was named bump_footprint_expiration by older Horizon releases.
    body = load("operations/extend_footprint_ttl.json")
    operation = OPERATION.validate_python(body | {"type": "bump_footprint_expiration"})
    assert isinstance(operation, ExtendFootprintTTLOperation)
    assert operation.type == "bump_footprint_expiration"


def test_unknown_number_keeps_its_fields() -> None:
    # Synthetic: a type that a newer Horizon could add.
    body = load("operations/payment.json") | {
        "type": "some_new_operation",
        "type_i": 99,
        "new_field": {"a": 1},
    }
    operation = OPERATION.validate_python(body)
    assert isinstance(operation, UnknownOperation)
    assert operation.type_i == 99
    assert operation.model_extra is not None
    assert operation.model_extra["new_field"] == {"a": 1}
    assert operation.model_extra["amount"] == body["amount"]


@pytest.mark.parametrize("type_i", [True, -1, 27])
def test_odd_numbers_are_unknown(type_i: object) -> None:
    body = load("operations/payment.json") | {"type_i": type_i}
    assert isinstance(OPERATION.validate_python(body), UnknownOperation)


def test_missing_number_is_an_error() -> None:
    body = load("operations/payment.json") | {"type_i": None}
    with pytest.raises(ValidationError, match="type_i"):
        OPERATION.validate_python(body)


def test_known_type_with_missing_field_is_an_error() -> None:
    # Synthetic: a body that Horizon does not send.
    body = load("operations/payment.json")
    del body["amount"]
    with pytest.raises(ValidationError, match="amount"):
        OPERATION.validate_python(body)


def test_validating_a_model_keeps_its_class() -> None:
    operation = OPERATION.validate_python(load("operations/payment.json"))
    assert OPERATION.validate_python(operation) is operation


def test_payment_values() -> None:
    operation = OPERATION.validate_python(load("operations/payment.json"))
    assert isinstance(operation, PaymentOperation)
    assert isinstance(operation.amount, Decimal)
    assert operation.created_at.tzinfo is not None
    assert operation.from_ == load("operations/payment.json")["from"]


def test_models_are_frozen() -> None:
    operation = OPERATION.validate_python(load("operations/payment.json"))
    with pytest.raises(ValidationError, match="frozen"):
        operation.id = "1"  # pyright: ignore[reportAttributeAccessIssue]


def test_null_lists_read_as_empty() -> None:
    body = load("operations/invoke_host_function_upload.json")
    assert body["parameters"] is None
    assert body["asset_balance_changes"] is None
    operation = OPERATION.validate_python(body)
    assert isinstance(operation, InvokeHostFunctionOperation)
    assert operation.parameters == []
    assert operation.asset_balance_changes == []


def test_base64_fields() -> None:
    operation = OPERATION.validate_python(load("operations/manage_data.json"))
    assert isinstance(operation, ManageDataOperation)
    assert operation.value == base64.b64decode(
        load("operations/manage_data.json")["value"]
    )
    body = load("operations/manage_data.json") | {"value": "not base64!"}
    with pytest.raises(ValidationError, match="invalid base64"):
        OPERATION.validate_python(body)
    built = ManageDataOperation.model_validate(
        load("operations/manage_data.json") | {"value": b"\x00\xff"}
    )
    assert built.value == b"\x00\xff"


def text_memo_record() -> dict[str, Any]:
    records = load("transactions_failed.json")["_embedded"]["records"]
    record: dict[str, Any] = next(r for r in records if r["memo_type"] == "text")
    return record


def test_memo_bytes() -> None:
    record = text_memo_record()
    transaction = Transaction.model_validate(record)
    assert transaction.memo_bytes is not None
    assert transaction.memo_bytes == base64.b64decode(record["memo_bytes"])
    assert transaction.memo_bytes.decode() == record["memo"]


def test_memo_bytes_need_not_be_utf8() -> None:
    # Synthetic: no captured memo has bytes that are not UTF-8.
    body = text_memo_record() | {"memo_bytes": "/w=="}
    transaction = Transaction.model_validate(body)
    assert transaction.memo_bytes == b"\xff"
    dumped = json.loads(transaction.model_dump_json(by_alias=True))
    assert dumped["memo_bytes"] == "/w=="


def test_transaction_without_meta() -> None:
    # The public network's Horizon runs with --skip-txmeta.
    record = load("transactions.json")["_embedded"]["records"][0]
    assert "result_meta_xdr" not in record
    assert Transaction.model_validate(record).result_meta_xdr is None


def test_preconditions() -> None:
    records = load("transactions_failed.json")["_embedded"]["records"]
    record = next(r for r in records if "ledgerbounds" in r.get("preconditions", {}))
    transaction = Transaction.model_validate(record)
    assert transaction.preconditions is not None
    assert transaction.preconditions.ledgerbounds is not None
    bounds = record["preconditions"]["ledgerbounds"]
    assert transaction.preconditions.ledgerbounds.max_ledger == bounds["max_ledger"]
    assert transaction.preconditions.timebounds is not None
    max_time = int(record["preconditions"]["timebounds"]["max_time"])
    assert transaction.preconditions.timebounds.max_time == max_time


def test_preconditions_at_their_limits() -> None:
    # Synthetic: no captured transaction has no upper ledger bound, or the largest
    # upper time bound.
    record = load("transactions.json")["_embedded"]["records"][0]
    body = record | {
        "preconditions": {
            "timebounds": {"min_time": "0", "max_time": "9223372036854775807"},
            "ledgerbounds": {"min_ledger": 10},
        }
    }
    transaction = Transaction.model_validate(body)
    assert transaction.preconditions is not None
    assert transaction.preconditions.timebounds is not None
    assert transaction.preconditions.timebounds.max_time == 2**63 - 1
    assert transaction.preconditions.ledgerbounds is not None
    assert transaction.preconditions.ledgerbounds.max_ledger is None


def test_claim_predicates() -> None:
    operation = OPERATION.validate_python(
        load("operations/create_claimable_balance.json")
    )
    assert isinstance(operation, CreateClaimableBalanceOperation)
    assert operation.claimants[0].predicate.unconditional is True
    either = operation.claimants[1].predicate.or_
    assert either is not None
    both = either[0].and_
    assert both is not None
    assert both[0].not_ is not None
    assert both[0].not_.rel_before == 100
    assert both[1].abs_before_epoch == 1634000400
    assert both[1].abs_before == "2021-10-12T01:00:00Z"


def test_claim_predicate_beyond_the_year_9999() -> None:
    # Synthetic: such a deadline is valid, but none was captured. It is kept as text;
    # the epoch is the number to use.
    far = {"abs_before": "+10000-01-01T00:00:00Z", "abs_before_epoch": "253402300800"}
    claimant = Claimant.model_validate({"destination": "G", "predicate": far})
    assert claimant.predicate.abs_before == "+10000-01-01T00:00:00Z"
    assert claimant.predicate.abs_before_epoch == 253402300800


def test_account_values() -> None:
    account = Account.model_validate(load("account.json"))
    assert account.sequence > 0
    assert all(isinstance(value, bytes) for value in account.data.values())
    assert isinstance(account.links["self"], Link)


def test_root_values() -> None:
    root = Root.model_validate(load("root.json"))
    assert root.history_latest_ledger > root.history_elder_ledger
    assert root.history_latest_ledger_closed_at < datetime.now(UTC)


def test_problem_short_type() -> None:
    problem = Problem.model_validate(
        {
            "type": "https://stellar.org/horizon-errors/not_found",
            "title": "Resource Missing",
            "status": 404,
        }
    )
    assert problem.short_type == "not_found"
    assert problem.detail is None
