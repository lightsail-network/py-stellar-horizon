"""Field types and helpers that several models share. Not part of the API."""

import base64
import binascii
from typing import Annotated, Any, cast, get_args

from pydantic import BeforeValidator, Field, PlainSerializer, Tag

from .base import Link

__all__ = ["Base64Bytes", "Links", "NullAsEmpty", "numbers_of", "tag_by_number"]


Links = Annotated[dict[str, Link], Field(alias="_links", default_factory=dict)]
"""The `_links` of a resource, by name. Absent links are absent keys."""


def _decode_base64(value: Any) -> Any:  # noqa: ANN401
    if isinstance(value, str):
        try:
            return base64.b64decode(value, validate=True)
        except binascii.Error as error:
            msg = f"invalid base64: {error}"
            raise ValueError(msg) from error
    return value


def _encode_base64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


Base64Bytes = Annotated[
    bytes,
    BeforeValidator(_decode_base64),
    PlainSerializer(_encode_base64, return_type=str),
]
"""Bytes that Horizon sends in base64, and that a dump writes back in base64."""


def _null_as_empty(value: Any) -> Any:  # noqa: ANN401
    return [] if value is None else value


NullAsEmpty = BeforeValidator(_null_as_empty)
"""Reads `null` as an empty list: Go writes an empty slice as `null`."""


def numbers_of(union: Any) -> frozenset[int]:  # noqa: ANN401
    """Return the type numbers that the classes of `Operation` or `Effect` stand for.

    Each class of such a union is annotated with a `Tag` of its number, and the class
    for every other number with the tag `unknown`.
    """
    members = get_args(get_args(union)[0])
    tags = {cast("Tag", get_args(member)[1]).tag for member in members}
    return frozenset(int(tag) for tag in tags if tag != "unknown")


def tag_by_number(value: Any, numbers: frozenset[int]) -> str:  # noqa: ANN401
    """Name the class of an operation or an effect by its `type_i`, or `unknown`.

    `value` is the body as Horizon sent it, or a model that is validated again.
    """
    type_i: object = (
        cast("dict[str, object]", value).get("type_i")
        if isinstance(value, dict)
        else getattr(value, "type_i", None)
    )
    if isinstance(type_i, int) and not isinstance(type_i, bool) and type_i in numbers:
        return str(type_i)
    return "unknown"
