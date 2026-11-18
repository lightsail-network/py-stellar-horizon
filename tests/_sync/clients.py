# Generated from _async/clients.py by scripts/unasync.py. Do not edit.
"""A client of this flavour for the fake server.

The fake server answers with captured responses: bodies come unchanged from
`tests/fixtures`, captured from the public networks. Where no public server gives an
answer on request, a test builds one and says so:

- answers that need a failing server: 503 `still_ingesting` and `stale_history`, 504
  `transaction_submission_timeout`, a 502 page from a proxy, a 429;
- broken connections and timeouts;
- `error` events in the middle of a stream;
- bodies that are not what Horizon sends, to test that they are refused;
- a redirect, as a load balancer in front of Horizon answers `http://` with, and a body
  that cannot be decoded;
- an object stream that sends the same object twice.
"""

from typing import Any

import httpx2

from stellar_horizon import HorizonClient
from tests.support import BASE, FakeHorizon


def client_for(horizon: FakeHorizon, base: str = BASE, **options: Any) -> HorizonClient:
    # Most tests look at one answer, so they turn the default retries off; the tests
    # of retries say what they want.
    options.setdefault("max_retries", 0)
    http = httpx2.Client(transport=httpx2.MockTransport(horizon))
    return HorizonClient(base, http_client=http, **options)
