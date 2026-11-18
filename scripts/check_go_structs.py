"""Compare the models with the Go types that Horizon serializes its responses from.

`scripts/go_structs` is a small Go program that writes, as JSON, the fields of every
response type of go-stellar-sdk's `protocols/horizon`
(https://github.com/stellar/go-stellar-sdk/tree/5410d3410e212331399d1518cc13150279969dac/protocols/horizon
for v0.9.0), at the version its `go.mod` pins:
the one Horizon depends on. This script compares them with the models, field by field,
and finds what the fixtures cannot show: a field that no sample had, or one that a
sample had but the server may leave out or write as `null`.

Errors fail the run. Warnings are printed: they point at a slice that Go writes as
`null` when it is nil, which Horizon may never do; each one is reviewed and then listed
in `REVIEWED`, with the reason.

Usage:
    uv run python scripts/check_go_structs.py                 # needs Go
    uv run python scripts/check_go_structs.py --structs FILE  # go_structs's output
"""

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import types
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, Union, cast, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from stellar_horizon import models
from stellar_horizon.models import effects, operations
from stellar_horizon.models._fields import NullAsEmpty

ROOT = Path(__file__).resolve().parent.parent
GO_PROGRAM = ROOT / "scripts" / "go_structs"

RESOURCES: dict[str, type[BaseModel]] = {
    "horizon.Root": models.Root,
    "horizon.Account": models.Account,
    "horizon.AccountData": models.AccountData,
    "horizon.AssetStat": models.AssetStat,
    "horizon.ClaimableBalance": models.ClaimableBalance,
    "horizon.FeeStats": models.FeeStats,
    "horizon.Ledger": models.Ledger,
    "horizon.LiquidityPool": models.LiquidityPool,
    "horizon.Offer": models.Offer,
    "horizon.OrderBookSummary": models.OrderBook,
    "horizon.Path": models.Path,
    "horizon.Trade": models.Trade,
    "horizon.TradeAggregation": models.TradeAggregation,
    "horizon.Transaction": models.Transaction,
    "horizon.AsyncTransactionSubmissionResponse": models.EnqueueResult,
    "horizon.TransactionResultCodes": models.TransactionResultCodes,
}

# Where Horizon shows each difference to be right. Checked on 2026-11-17 at the latest
# commit of stellar-horizon's main branch, one after v30.0.1.
HORIZON = (
    "https://github.com/stellar/stellar-horizon/blob/"
    "01ba44a988b3ebc2d68d3cb6747fa2c2733773cd/internal/"
)
LIB_PQ = "https://github.com/lib/pq/blob/2a217b94f5ccd3de31aec4152a541b9ff64bed05/"
_ACCOUNT = f"{HORIZON}resourceadapter/account_entry.go"
_OPERATIONS = f"{HORIZON}ingest/processors/operations_processor.go"
_EFFECTS = f"{HORIZON}ingest/processors/effects_processor.go"
_MADE = "Horizon fills it with make or a literal, never nil:"
_SIGNATURES = (
    "ingestion writes make([]string, n), "
    f"{HORIZON}db2/history/transaction_batch_insert_builder.go#L67-L73, "
    "and lib/pq v1.10.9 reads an empty array as an empty slice, "
    f"{LIB_PQ}array.go#L648-L657"
)
REVIEWED: dict[tuple[str, str], str] = {
    ("Account", "balances"): f"{_MADE} {_ACCOUNT}#L52",
    ("Account", "data"): f"{_MADE} {_ACCOUNT}#L80",
    ("Account", "signers"): f"{_MADE} {_ACCOUNT}#L88",
    ("AssetStat", "asset_code"): (
        "asset stats skip native and pool shares, so issued assets only: "
        f"{HORIZON}ingest/processors/asset_stats_set.go#L221"
    ),
    ("AssetStat", "asset_issuer"): "as asset_code",
    ("ClaimableBalance", "claimants"): (
        f"{_MADE} {HORIZON}resourceadapter/claimable_balances.go#L29"
    ),
    ("CreateClaimableBalanceOperation", "claimants"): (
        f"appended one by one, {_OPERATIONS}#L547-L555, but an operation without "
        "claimants is malformed and never reaches a ledger"
    ),
    ("EffectLiquidityPool", "reserves"): f"{_MADE} {_EFFECTS}#L1478",
    ("LiquidityPool", "reserves"): (
        "appended one by one, but a pool always has two reserves: "
        f"{HORIZON}resourceadapter/liquidity_pool.go#L32-L33"
    ),
    (
        "LiquidityPoolDepositOperation",
        "reserves_deposited",
    ): f"{_MADE} {_OPERATIONS}#L644",
    ("LiquidityPoolDepositOperation", "reserves_max"): f"{_MADE} {_OPERATIONS}#L630",
    ("LiquidityPoolWithdrawOperation", "reserves_min"): f"{_MADE} {_OPERATIONS}#L666",
    ("LiquidityPoolWithdrawOperation", "reserves_received"): (
        f"{_MADE} {_OPERATIONS}#L671"
    ),
    ("LiquidityPoolDepositedEffect", "reserves_deposited"): f"{_MADE} {_EFFECTS}#L1499",
    ("LiquidityPoolWithdrewEffect", "reserves_received"): f"{_MADE} {_EFFECTS}#L1523",
    ("LiquidityPoolRevokedEffect", "reserves_revoked"): f"{_MADE} {_EFFECTS}#L1398",
    ("OrderBook", "asks"): f"{_MADE} {HORIZON}actions/orderbook.go#L54-L55",
    ("OrderBook", "bids"): f"{_MADE} {HORIZON}actions/orderbook.go#L54-L55",
    ("Path", "path"): f"{_MADE} {HORIZON}resourceadapter/path.go#L51",
    ("PathPaymentStrictReceiveOperation", "path"): f"{_MADE} {_OPERATIONS}#L377",
    ("PathPaymentStrictSendOperation", "path"): f"{_MADE} {_OPERATIONS}#L406",
    ("Transaction", "signatures"): _SIGNATURES,
    ("FeeBumpTransaction", "signatures"): _SIGNATURES,
    ("InnerTransaction", "signatures"): _SIGNATURES,
}
"""Differences that were looked at and are right, by (model, JSON field): the reason."""


@dataclass
class Shape:
    """What a model field accepts, reduced to what can be compared with Go."""

    kinds: set[str] = field(default_factory=set[str])
    models: list[type[BaseModel]] = field(default_factory=list[type[BaseModel]])
    item: "Shape | None" = None
    nullable: bool = False


def shape_of(annotation: Any) -> Shape:  # noqa: ANN401, C901
    """Reduce a type annotation to the kinds of JSON value it accepts."""
    shape = Shape()
    origin = get_origin(annotation)
    if origin is Annotated:
        return shape_of(get_args(annotation)[0])
    if origin in {Union, types.UnionType}:
        for arg in get_args(annotation):
            if arg is type(None):
                shape.nullable = True
                continue
            inner = shape_of(arg)
            shape.kinds |= inner.kinds
            shape.models += inner.models
            shape.item = shape.item or inner.item
        return shape
    if origin is Literal:
        values = get_args(annotation)
        shape.kinds.add("int" if all(isinstance(v, int) for v in values) else "str")
    elif origin is list:
        shape.kinds.add("list")
        shape.item = shape_of(get_args(annotation)[0])
    elif origin is dict:
        shape.kinds.add("dict")
    elif annotation is Any:
        shape.kinds.add("any")
    elif isinstance(annotation, str):
        shape.kinds.add("model")
        shape.models.append(getattr(models, annotation))
    elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
        shape.kinds.add("model")
        shape.models.append(annotation)
    else:
        names: dict[object, str] = {
            str: "str",
            bytes: "bytes",
            int: "int",
            float: "float",
            bool: "bool",
            Decimal: "decimal",
            dt.datetime: "datetime",
        }
        known = cast("object", annotation)
        shape.kinds.add(names.get(known, repr(known)))
    return shape


# What a model may use for each kind of Go value.
ACCEPTS = {
    "string": {"str", "bytes", "decimal", "int", "datetime", "any"},
    "int": {"int", "any"},
    "float": {"decimal", "float", "any"},
    "bool": {"bool", "any"},
    "time": {"datetime", "str", "any"},
    "struct": {"model", "dict", "any"},
    "slice": {"list", "any"},
    "map": {"dict", "any"},
}


@dataclass
class Report:
    """What the comparison found."""

    errors: list[str] = field(default_factory=list[str])
    warnings: list[str] = field(default_factory=list[str])
    reviewed: list[str] = field(default_factory=list[str])

    def add(
        self, level: str, model: type[BaseModel], json_name: str, text: str
    ) -> None:
        """Note a difference, unless it was reviewed."""
        line = f"{model.__name__}.{json_name}: {text}"
        reason = REVIEWED.get((model.__name__, json_name))
        if reason is not None:
            self.reviewed.append(f"{line} (reviewed: {reason})")
        elif level == "error":
            self.errors.append(line)
        else:
            self.warnings.append(line)


class Comparer:
    """Compares Go structs with models, following nested structs."""

    def __init__(self, structs: dict[str, Any], report: Report) -> None:
        self.structs = structs
        self.report = report
        self.done: set[tuple[str, type[BaseModel]]] = set()

    def compare(self, go_name: str, model: type[BaseModel]) -> None:
        """Compare one Go struct with one model, then what they hold."""
        if (go_name, model) in self.done:
            return
        self.done.add((go_name, model))
        by_json = {
            (info.alias or name): info for name, info in model.model_fields.items()
        }
        go_fields = self.structs[go_name]["fields"]
        for go_field in go_fields:
            name = go_field["json"]
            info = by_json.get(name)
            if info is None:
                self.report.add("error", model, name, f"missing ({go_name})")
                continue
            if name == "_links":
                continue
            self.field(model, go_field, info)
        go_names = {go_field["json"] for go_field in go_fields}
        for name in by_json:
            if name not in go_names:
                self.report.add("error", model, name, f"not in {go_name}")

    def field(
        self, model: type[BaseModel], go_field: dict[str, Any], info: FieldInfo
    ) -> None:
        """Compare one field: whether it can be absent or null, and its kind."""
        name = go_field["json"]
        shape = shape_of(info.annotation)
        null_as_empty = NullAsEmpty in info.metadata
        kind = go_field["kind"]
        omitempty = go_field["omitempty"]
        if omitempty and info.is_required():
            self.report.add("error", model, name, "Go omits it when empty; required")
        if go_field["pointer"] and not omitempty and not shape.nullable:
            self.report.add("error", model, name, "Go writes nil as null; not nullable")
        if (
            kind in {"slice", "map"}
            and not omitempty
            and not (shape.nullable or null_as_empty)
        ):
            self.report.add(
                "warning", model, name, f"Go writes a nil {kind} as null; not nullable"
            )
        if kind in {"opaque", "any"}:
            return
        # With the `,string` option, Go writes a number or a bool as a JSON string.
        accepts = (
            ACCEPTS["string"] | ACCEPTS[kind] if go_field["string"] else ACCEPTS[kind]
        )
        if not shape.kinds & accepts:
            self.report.add(
                "error", model, name, f"Go {kind} read as {sorted(shape.kinds)}"
            )
            return
        if kind == "struct" and go_field["type"] != "anonymous":
            for nested in shape.models:
                self.compare(go_field["type"], nested)
        if kind == "slice" and shape.item is not None:
            self.item(model, go_field, shape.item)

    def item(
        self, model: type[BaseModel], go_field: dict[str, Any], item: Shape
    ) -> None:
        """Compare the items of a list."""
        elem = go_field["elem"]
        if elem in {"opaque", "any"}:
            return
        if not item.kinds & ACCEPTS.get(elem, set()):
            self.report.add(
                "error",
                model,
                go_field["json"],
                f"items: Go {elem} read as {sorted(item.kinds)}",
            )
            return
        if elem == "struct":
            for nested in item.models:
                self.compare(go_field["elem_type"], nested)


def by_type_i(module: types.ModuleType, base: type[Any]) -> dict[int, type[BaseModel]]:
    """Map each type number to the model class of `module` that reads it."""
    found: dict[int, type[BaseModel]] = {}
    for cls in vars(module).values():
        if (
            isinstance(cls, type)
            and issubclass(cls, BaseModel)
            and issubclass(cls, base)
            and cls is not base
        ):
            annotation: object = cls.model_fields["type_i"].annotation
            if get_origin(annotation) is Literal:
                found[get_args(annotation)[0]] = cls
    return found


def pinned_version() -> str:
    """Return the go-stellar-sdk version that `scripts/go_structs/go.mod` pins."""
    text = (GO_PROGRAM / "go.mod").read_text(encoding="utf-8")
    match = re.search(r"github\.com/stellar/go-stellar-sdk (\S+)", text)
    if match is None:
        msg = "go.mod does not require go-stellar-sdk"
        raise SystemExit(msg)
    return match.group(1)


def load_structs(path: Path | None) -> dict[str, Any]:
    """Read the output of go_structs, running it if no file is given."""
    if path is not None:
        return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    output = subprocess.run(  # noqa: S603
        ["go", "run", ".", pinned_version()],  # noqa: S607
        cwd=GO_PROGRAM,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return cast("dict[str, Any]", json.loads(output))


def check(data: dict[str, Any]) -> Report:
    """Compare every resource, operation and effect."""
    report = Report()
    comparer = Comparer(data["structs"], report)
    for go_name, model in RESOURCES.items():
        comparer.compare(go_name, model)
    for kind, module, base, go_types in [
        ("operation", operations, operations.BaseOperation, data["operations"]),
        ("effect", effects, effects.BaseEffect, data["effects"]),
    ]:
        ours = by_type_i(module, base)
        theirs = {int(number): go_name for number, go_name in go_types.items()}
        for number in sorted(set(ours) ^ set(theirs)):
            where = "the models" if number not in ours else "Go"
            report.errors.append(f"{kind} type {number}: missing in {where}")
        for number in sorted(set(ours) & set(theirs)):
            comparer.compare(theirs[number], ours[number])
    return report


def main() -> int:
    """Compare, print what differs, and fail on errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structs", type=Path, help="the output of go_structs")
    args = parser.parse_args()
    data = load_structs(args.structs)
    report = check(data)
    print(f"go-stellar-sdk {data.get('version') or pinned_version()}")
    for title, lines in [
        ("errors", report.errors),
        ("warnings", report.warnings),
        ("reviewed", report.reviewed),
    ]:
        print(f"\n{len(lines)} {title}")
        for line in sorted(lines):
            print(f"  {line}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
