"""Write `docs/api-coverage.md` from `tests/routes.json`.

Usage:
    uv run python scripts/api_coverage.py            # write the page
    uv run python scripts/api_coverage.py --check    # fail if the page is out of date
"""

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any

from stellar_horizon import HorizonClient

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "tests" / "routes.json"
PAGE = ROOT / "docs" / "api-coverage.md"

BODIES = {
    "object": "one resource",
    "page": "a page",
    "list": "a list",
    "redirect": "a redirect",
}
CLIENT = HorizonClient("https://horizon.invalid")
"""Only read for the signatures of its methods; it sends nothing."""


def signature(call: dict[str, Any]) -> str:
    """Write a call as `client.resource.method(name, keyword=...)`."""
    target = getattr(CLIENT, call["resource"]) if call["resource"] else CLIENT
    names = list(inspect.signature(getattr(target, call["method"])).parameters)
    args = [*names[: len(call.get("args", []))]]
    args += [f"{name}=…" for name in call.get("kwargs", {})]
    owner = f"client.{call['resource']}" if call["resource"] else "client"
    return f"`{owner}.{call['method']}({', '.join(args)})`"


def render(routes: dict[str, Any]) -> str:
    """Return the page for the routes of `routes.json`."""
    intro = f"""\
# API coverage

<!-- Written by scripts/api_coverage.py from tests/routes.json. Do not edit. -->

Every route of Horizon {routes["horizon_version"]}, as its
[router]({routes["source"]}) defines them, and the method that calls it. A test checks
that each listed method requests its route, and that every route is either called or
left out for the reason given below.

Anything that is not listed can still be reached with `client.request()`.
"""
    lines = [
        *intro.splitlines(),
        "",
        "| Route | Returns | Method | Stream |",
        "|---|---|---|---|",
    ]
    left_out: list[str] = []
    for route in routes["routes"]:
        name = f"`{route['method']} {route['path']}`"
        call = signature(route["call"]) if "call" in route else "not offered"
        if "not_offered" in route:
            left_out.append(f"- {name}: {route['not_offered']}")
        stream = "—"
        if route["stream"]:
            if "stream_call" in route:
                stream = signature(route["stream_call"])
            else:
                stream = "not offered"
                left_out.append(
                    f"- The stream of {name}: {route['stream_not_offered']}"
                )
        if route.get("raw"):
            left_out.append(
                f"- {name} as raw bytes, `application/octet-stream`: "
                f"{route['raw_not_offered']}"
            )
        lines.append(f"| {name} | {BODIES[route['body']]} | {call} | {stream} |")
    lines += ["", "## Left out", "", *left_out, ""]
    return "\n".join(lines)


def main() -> int:
    """Write the page, or with `--check` tell whether it is up to date."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if out of date")
    args = parser.parse_args()
    page = render(json.loads(ROUTES.read_text(encoding="utf-8")))
    if args.check:
        if PAGE.read_text(encoding="utf-8") != page:
            print(f"{PAGE.relative_to(ROOT)} is out of date; run make generate")
            return 1
        return 0
    PAGE.write_text(page, encoding="utf-8")
    print(f"wrote {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
