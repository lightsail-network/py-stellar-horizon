"""The comparison of the models with Horizon's Go types finds what it should.

The real comparison needs Go and runs in its own CI job; these tests feed it Go
structs written by hand, so they run everywhere.
"""

import importlib.util
import sys
from types import ModuleType
from typing import Any

import pytest

from stellar_horizon import models
from tests.support import FIXTURES

SCRIPT = FIXTURES.parent.parent / "scripts" / "check_go_structs.py"
if not SCRIPT.exists():
    # The source distribution ships the tests, not the scripts.
    pytest.skip("scripts/ is not here", allow_module_level=True)


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_go_structs", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECK = load_script()


def go_field(json: str, kind: str, **options: Any) -> dict[str, Any]:
    return {
        "json": json,
        "kind": kind,
        "omitempty": False,
        "string": False,
        "pointer": False,
        **options,
    }


def compare(fields: list[dict[str, Any]], model: type[Any], **nested: Any) -> Any:
    structs = {"go.Type": {"fields": fields}, **nested}
    report = CHECK.Report()
    CHECK.Comparer(structs, report).compare("go.Type", model)
    return report


PRICE = [go_field("n", "int"), go_field("d", "int")]


def test_matching_fields_pass() -> None:
    report = compare(PRICE, models.Price)
    assert (report.errors, report.warnings) == ([], [])


def test_a_field_the_model_lacks() -> None:
    report = compare([*PRICE, go_field("x", "string")], models.Price)
    assert report.errors == ["Price.x: missing (go.Type)"]


def test_a_field_go_lacks() -> None:
    report = compare(PRICE[:1], models.Price)
    assert report.errors == ["Price.d: not in go.Type"]


def test_a_field_go_can_leave_out() -> None:
    report = compare([go_field("n", "int", omitempty=True), PRICE[1]], models.Price)
    assert report.errors == ["Price.n: Go omits it when empty; required"]


def test_a_pointer_go_can_write_as_null() -> None:
    report = compare([go_field("n", "int", pointer=True), PRICE[1]], models.Price)
    assert report.errors == ["Price.n: Go writes nil as null; not nullable"]


def test_a_kind_that_does_not_match() -> None:
    report = compare([go_field("n", "bool"), PRICE[1]], models.Price)
    assert report.errors == ["Price.n: Go bool read as ['int']"]


def test_a_number_written_as_a_string() -> None:
    fields = [go_field("href", "int", string=True), go_field("templated", "bool")]
    assert compare(fields, models.Link).errors == []


def test_nested_structs_are_compared() -> None:
    fields = [
        go_field("bids", "slice", elem="struct", elem_type="go.Level"),
        go_field("asks", "slice", elem="struct", elem_type="go.Level"),
        go_field("base", "struct", type="go.Asset"),
        go_field("counter", "struct", type="go.Asset"),
    ]
    nested = {
        "go.Level": {"fields": [go_field("price_r", "struct", type="go.Price")]},
        "go.Price": {"fields": PRICE},
        "go.Asset": {"fields": [go_field("asset_type", "bool")]},
    }
    report = compare(fields, models.OrderBook, **nested)
    assert "Asset.asset_type: Go bool read as ['str']" in report.errors
    assert "PriceLevel.price: not in go.Level" in report.errors
    assert not any(error.startswith("Price.") for error in report.errors)


def test_a_nil_slice_is_a_warning_until_reviewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fields = [
        go_field("hash", "string"),
        go_field("signatures", "slice", elem="string"),
    ]
    reviewed = compare(fields, models.FeeBumpTransaction)
    assert reviewed.warnings == []
    assert len(reviewed.reviewed) == 1
    monkeypatch.setattr(CHECK, "REVIEWED", {})
    report = compare(fields, models.FeeBumpTransaction)
    assert report.warnings == [
        "FeeBumpTransaction.signatures: Go writes a nil slice as null; not nullable"
    ]


def test_every_operation_and_effect_class_has_a_number() -> None:
    assert sorted(CHECK.by_type_i(models.operations, models.BaseOperation)) == list(
        range(27)
    )
    assert len(CHECK.by_type_i(models.effects, models.BaseEffect)) == 50


def test_a_type_number_missing_on_one_side(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CHECK, "RESOURCES", {})
    report = CHECK.check({"structs": {}, "operations": {}, "effects": {}})
    assert "operation type 0: missing in Go" in report.errors
    assert "effect type 97: missing in Go" in report.errors
