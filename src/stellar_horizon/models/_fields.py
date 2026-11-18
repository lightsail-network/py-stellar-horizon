"""Field types that several models share. Not part of the API."""

import base64
import binascii
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, PlainSerializer

from .base import Link

__all__ = ["Base64Bytes", "Links", "NullAsEmpty"]


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
