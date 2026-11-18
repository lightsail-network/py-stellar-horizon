"""Every Horizon route is called by a method, or left out for a reason.

`tests/routes.json` lists the routes of the Horizon release the package was checked
against. Each listed method is called here against a fake server, and the request it
sends must be for its route. A new route, or a method that is not listed, fails a test.
"""

import inspect
import json
import re
from typing import Any

import pytest

from stellar_horizon import HorizonClient, ResponseError
from stellar_horizon._sync import _resources as resources
from tests._sync.clients import client_for
from tests.support import FIXTURES, FakeHorizon, path_of

ROUTES: list[dict[str, Any]] = json.loads(
    (FIXTURES.parent / "routes.json").read_text(encoding="utf-8")
)["routes"]


def route_id(route: dict[str, Any]) -> str:
    return f"{route['method']} {route['path']}"


# Methods that call a route another method also calls: `requires_memo` reads one
# data entry.
ALSO_CALLING = {"accounts.requires_memo"}


def pattern(path: str) -> re.Pattern[str]:
    """Match the paths of a route template, one segment per placeholder."""
    parts = re.split(r"\{[^}]+\}", path)
    return re.compile("[^/]+".join(re.escape(part) for part in parts))


def method_of(client: HorizonClient, call: dict[str, Any]) -> Any:
    target = getattr(client, call["resource"]) if call["resource"] else client
    return getattr(target, call["method"])


def invoke(client: HorizonClient, call: dict[str, Any]) -> Any:
    return method_of(client, call)(*call.get("args", []), **call.get("kwargs", {}))


@pytest.mark.parametrize("route", ROUTES, ids=route_id)
def test_route_is_called_or_left_out(route: dict[str, Any]) -> None:
    assert ("call" in route) != ("not_offered" in route)
    if route["stream"]:
        assert ("stream_call" in route) != ("stream_not_offered" in route)
    else:
        assert "stream_call" not in route
        assert "stream_not_offered" not in route
    assert route.get("raw", False) == ("raw_not_offered" in route)


@pytest.mark.parametrize(
    "route", [route for route in ROUTES if "call" in route], ids=route_id
)
def test_method_requests_its_route(horizon: FakeHorizon, route: dict[str, Any]) -> None:
    # Every route answers 404, which each method raises; streams need the root.
    horizon.routes.clear()
    with client_for(horizon) as client, pytest.raises(ResponseError):
        invoke(client, route["call"])
    sent = horizon.requests[-1]
    assert sent.method == route["method"]
    assert pattern(route["path"]).fullmatch(path_of(sent)), path_of(sent)
    assert sent.headers["accept"] != "text/event-stream"


@pytest.mark.parametrize(
    "route", [route for route in ROUTES if "stream_call" in route], ids=route_id
)
def test_stream_requests_its_route(horizon: FakeHorizon, route: dict[str, Any]) -> None:
    with (
        client_for(horizon) as client,
        invoke(client, route["stream_call"]) as stream,
        pytest.raises(ResponseError),
    ):
        next(stream)
    sent = horizon.requests[-1]
    assert pattern(route["path"]).fullmatch(path_of(sent)), path_of(sent)
    assert sent.headers["accept"] == "text/event-stream"


def test_every_method_is_listed() -> None:
    listed = {
        f"{call['resource']}.{call['method']}".lstrip(".")
        for route in ROUTES
        for call in (route.get("call"), route.get("stream_call"))
        if call is not None
    }
    with HorizonClient("https://horizon.test") as client:
        offered = {"root", "fee_stats"}
        for name, resource in vars(client).items():
            if type(resource).__name__ in resources.__all__:
                offered |= {
                    f"{name}.{method}"
                    for method, _ in inspect.getmembers(resource, inspect.ismethod)
                    if not method.startswith("_")
                }
    assert offered - ALSO_CALLING == listed


def test_the_routes_of_the_baseline() -> None:
    methods = [route["method"] for route in ROUTES if route["path"] != "/friendbot"]
    assert (methods.count("GET"), methods.count("POST")) == (48, 2)
    assert sum(1 for route in ROUTES if route["stream"]) == 30
