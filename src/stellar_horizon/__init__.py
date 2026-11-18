"""A typed Python client for the Stellar Horizon API.

See https://stellar-horizon.readthedocs.io/ for the guide.
"""

from typing import Final

__all__ = ["HORIZON_VERSION"]

HORIZON_VERSION: Final = "30.0.1"
"""The Horizon release that the models and fixtures were checked against.

Newer releases of Horizon are expected to work: fields the models don't know are kept,
and operation and effect types they don't know are read as `UnknownOperation` and
`UnknownEffect`.
"""
