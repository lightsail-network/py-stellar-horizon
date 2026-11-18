"""Helpers shared by the tests."""

import json
from pathlib import Path
from typing import Any, cast

import httpx2
from pydantic import BaseModel

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> Any:
    """Return the decoded JSON of the fixture at `name`, relative to `fixtures/`."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixtures(pattern: str) -> list[str]:
    """Return the names of the fixtures that match `pattern`, sorted."""
    return sorted(
        path.relative_to(FIXTURES).as_posix() for path in FIXTURES.glob(pattern)
    )


def manifest() -> dict[str, dict[str, Any]]:
    """Return where each fixture came from, by name."""
    return cast("dict[str, dict[str, Any]]", load("manifest.json"))


def captured(name: str) -> httpx2.Response:
    """A response as Horizon sent it: the body of a fixture, its status and type."""
    entry = manifest()[name]
    return httpx2.Response(
        int(entry.get("status", 200)),
        content=(FIXTURES / name).read_bytes(),
        headers={"content-type": entry.get("content_type", "application/hal+json")},
    )


def event_ids(name: str) -> list[str]:
    """Return the IDs of the events of a captured stream, in order."""
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return [
        line.removeprefix("id: ")
        for line in text.splitlines()
        if line.startswith("id: ")
    ]


def unknown_fields(value: object, path: str = "") -> list[str]:
    """Return the paths of every field, at any depth, that a model did not know."""
    found: list[str] = []
    if isinstance(value, BaseModel):
        found.extend(f"{path}.{name}" for name in value.model_extra or {})
        for name in type(value).model_fields:
            found.extend(unknown_fields(getattr(value, name), f"{path}.{name}"))
    elif isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            found.extend(unknown_fields(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in cast("dict[object, object]", value).items():
            found.extend(unknown_fields(item, f"{path}[{key!r}]"))
    return found


class FakeHorizon:
    """A Horizon server for `httpx2.MockTransport`, scripted route by route.

    Each route has a queue of answers: a response, or an exception to raise. The last
    answer of a queue is repeated.
    """

    def __init__(self) -> None:
        self.routes: dict[str, list[httpx2.Response | Exception]] = {}
        self.requests: list[httpx2.Request] = []

    def on(self, path: str, *answers: httpx2.Response | Exception) -> None:
        """Answer requests for `path` with `answers`, in turn."""
        self.routes[path] = list(answers)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        answers = self.routes.get(path_of(request))
        if not answers:
            return json_response(404, problem("not_found", 404))
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def paths(self) -> list[str]:
        """Return the path of each request, in order."""
        return [path_of(request) for request in self.requests]


def path_of(request: httpx2.Request) -> str:
    """The path of a request as it was sent, still percent-encoded."""
    return request.url.raw_path.split(b"?", 1)[0].decode("ascii")


def json_response(status: int, body: object, **headers: str) -> httpx2.Response:
    """A response with a JSON body."""
    return httpx2.Response(status, content=json.dumps(body).encode(), headers=headers)


def problem(type_: str, status: int, **extras: object) -> dict[str, Any]:
    """A problem document."""
    body: dict[str, Any] = {
        "type": "https://stellar.org/horizon-errors/" + type_,
        "title": type_.replace("_", " ").title(),
        "status": status,
    }
    if extras:
        body["extras"] = extras
    return body


def sse(*events: str) -> httpx2.Response:
    """An event-stream response made of these events, each written out in full."""
    content = "".join(event + "\n\n" for event in events)
    return httpx2.Response(
        200,
        content=content.encode(),
        headers={"content-type": "text/event-stream; charset=utf-8"},
    )


OPEN = 'retry: 1000\nevent: open\ndata: "hello"'


def stream_records(name: str) -> list[str]:
    """Return the events of a captured stream that carry a record, each in full."""
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return [block for block in text.split("\n\n") if block.startswith("id: ")]


CLOSE = 'retry: 10\nevent: close\ndata: "byebye"'
