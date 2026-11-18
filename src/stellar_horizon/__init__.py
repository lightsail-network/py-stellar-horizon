"""A typed Python client for the Stellar Horizon API.

This module has what a program calls and catches: the clients, their pages and streams,
and the errors. The resources that Horizon returns are in `stellar_horizon.models`.

See https://stellar-horizon.readthedocs.io/ for the guide.
"""

from typing import Final

from ._async._client import AsyncHorizonClient
from ._async._page import AsyncPage
from ._async._stream import AsyncStream
from ._sync._client import HorizonClient
from ._sync._page import Page
from ._sync._stream import Stream
from .errors import (
    BadRequestError,
    BeforeHistoryError,
    HorizonError,
    InvalidResponseError,
    NotFoundError,
    OutcomeUnknownError,
    PagingError,
    RateLimitError,
    ResponseError,
    ServerError,
    StreamError,
    TransactionFailedError,
    TransportError,
)

__all__ = [
    "HORIZON_VERSION",
    "AsyncHorizonClient",
    "AsyncPage",
    "AsyncStream",
    "BadRequestError",
    "BeforeHistoryError",
    "HorizonClient",
    "HorizonError",
    "InvalidResponseError",
    "NotFoundError",
    "OutcomeUnknownError",
    "Page",
    "PagingError",
    "RateLimitError",
    "ResponseError",
    "ServerError",
    "Stream",
    "StreamError",
    "TransactionFailedError",
    "TransportError",
]

HORIZON_VERSION: Final = "30.0.1"
"""The Horizon release that the models and fixtures were checked against.

Newer releases of Horizon are expected to work: fields the models don't know are kept,
and operation and effect types they don't know are read as `UnknownOperation` and
`UnknownEffect`.
"""
