"""Reading responses, and the requests that follow from them. Nothing here does I/O."""

import json
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from urllib.parse import parse_qsl, unquote, urlsplit

import httpx2
from pydantic import TypeAdapter, ValidationError

from ._requests import Request
from .errors import InvalidResponseError, PagingError

__all__ = [
    "follow",
    "read_json",
    "read_object",
    "read_page",
    "read_record",
    "read_result",
]

T = TypeVar("T")


def read_json(response: httpx2.Response) -> object:
    """Return the decoded JSON body of a read response."""
    try:
        return json.loads(response.content)
    except (ValueError, RecursionError) as error:
        # RecursionError: a body nested deeper than the interpreter recurses.
        msg = f"the response is not JSON: {error}"
        raise InvalidResponseError(
            msg, body=response.text, response=response
        ) from error


def _validate(adapter: TypeAdapter[T], body: object, response: httpx2.Response) -> T:
    try:
        return adapter.validate_python(body)
    except ValidationError as error:
        msg = f"the response cannot be read: {error}"
        raise InvalidResponseError(msg, body=body, response=response) from error


def read_object(adapter: TypeAdapter[T], response: httpx2.Response) -> T:
    """Read a response that holds one resource."""
    return _validate(adapter, read_json(response), response)


def read_result(adapter: TypeAdapter[T], response: httpx2.Response) -> T | None:
    """Read a response as a result if its whole body is one, or return `None`."""
    try:
        return adapter.validate_json(response.content)
    except ValidationError:
        return None


def read_page(
    adapter: TypeAdapter[T], response: httpx2.Response
) -> tuple[list[T], dict[str, str]]:
    """Read a page: its records, and the href of each of its links by name."""
    body = read_json(response)
    try:
        records = cast("Any", body)["_embedded"]["records"]
        if not isinstance(records, list):
            raise TypeError  # noqa: TRY301
    except (TypeError, KeyError) as error:
        msg = "the response is not a page: it has no _embedded.records list"
        raise InvalidResponseError(msg, body=body, response=response) from error
    read = [
        _validate(adapter, record, response) for record in cast("list[object]", records)
    ]
    links: dict[str, str] = {}
    raw_links = cast("dict[str, Any]", body).get("_links")
    if isinstance(raw_links, dict):
        for name, link in cast("dict[str, Any]", raw_links).items():
            if isinstance(link, dict):
                href = cast("dict[str, Any]", link).get("href")
                if isinstance(href, str):
                    links[name] = href
    return read, links


def read_record(adapter: TypeAdapter[T], data: str, response: httpx2.Response) -> T:
    """Read the data of one event of a stream."""
    try:
        body = json.loads(data)
    except (ValueError, RecursionError) as error:
        msg = f"a stream event is not JSON: {error}"
        raise InvalidResponseError(msg, body=data, response=response) from error
    return _validate(adapter, body, response)


def follow(request: Request[T], links: Mapping[str, str], name: str) -> Request[T]:
    """Return the request for the page that the link `name` points to.

    Only the query string of the link is used. Its scheme, host and any prefix of its
    path are ignored, because Horizon builds them from what it sees, which behind a
    proxy is not what the client sees. The link must be for the endpoint that was
    requested.
    """
    href = links.get(name)
    if not href:
        msg = f"the page has no {name} page"
        raise PagingError(msg)
    parts = urlsplit(href)
    if not unquote(parts.path).rstrip("/").endswith(unquote(request.endpoint)):
        # The link itself is not shown: a server can echo a key in it. It is in
        # the `links` of the page.
        msg = f"the {name} link points to another endpoint than {request.endpoint}"
        raise PagingError(msg)
    return request.with_params(tuple(parse_qsl(parts.query, keep_blank_values=True)))


def same(first: Request[Any], second: Request[Any]) -> bool:
    """Tell whether two requests ask for the same thing."""
    return (
        first.method == second.method
        and first.path == second.path
        and sorted(first.params) == sorted(second.params)
    )
