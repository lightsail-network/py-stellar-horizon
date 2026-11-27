"""One sync client, shared by threads that use it at the same time, over real sockets.

The threads share the client's connection pool, which only real connections exercise.
Each thread asks for things that carry its own name, and the server puts that name in
its answers, so an answer that reaches the wrong thread fails the test.
"""

import json
import sys
import sysconfig
import threading
import time
from collections import Counter
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from stellar_horizon import HorizonClient
from tests.local_server import Connection, Document, LocalHorizon
from tests.support import (
    CLOSE,
    FIXTURES,
    NOW,
    OPEN,
    SMALL_ACCOUNT,
    load,
    records,
)

THREADS = 12
CALLS = 10
WAIT = 10.0
"""Seconds a thread may take, so that a deadlock fails the test instead of hanging."""

HAL = "application/hal+json; charset=utf-8"
ACCOUNT = (FIXTURES / "account.json").read_text(encoding="utf-8")
ACCOUNT_ID = load("account.json")["account_id"]
SEQUENCE = int(load("account.json")["sequence"])
ROOT = (FIXTURES / "root.json").read_text(encoding="utf-8")
SUBMITTED = load("submissions/success.json")
PAGE_RECORDS = records("pages/payments_1.json")
SECOND_CURSOR = PAGE_RECORDS[-1]["paging_token"]
PAGES = {
    None: (FIXTURES / "pages/payments_1.json").read_text(encoding="utf-8"),
    SECOND_CURSOR: (FIXTURES / "pages/payments_2.json").read_text(encoding="utf-8"),
}
"""The pages of the payments of the small account, by the cursor that asks for each."""
PAYMENTS = PAGE_RECORDS + records("pages/payments_2.json")
PAYMENT_IDS = [payment["id"] for payment in PAYMENTS]
FUNDER = PAYMENTS[0]["source_account"]


def name(thread: int, call: int | str) -> str:
    """The name of an account that belongs to one call of one thread."""
    return f"GTHREAD{thread:02d}CALL{call}"


def route(method: str, path: str, body: bytes) -> Document | None:
    """Answer with a fixture in which the account the request names stands in."""
    parts = urlsplit(path)
    query = dict(parse_qsl(parts.query))
    if parts.path.startswith("/echo/"):
        echo = {"method": method, "path": path, "body": body.decode()}
        return 200, "application/json", json.dumps(echo).encode()
    if parts.path == "/":
        return 200, HAL, ROOT.encode()
    if parts.path == "/transactions":
        envelope = dict(parse_qsl(body.decode()))["tx"]
        return 200, HAL, json.dumps({**SUBMITTED, "envelope_xdr": envelope}).encode()
    account = parts.path.split("/")[2]
    if parts.path.endswith("/payments"):
        if query.get("cursor") == NOW:
            # A stream, which `stream` answers.
            return None
        page = PAGES[query.get("cursor")]
        return 200, HAL, page.replace(SMALL_ACCOUNT, account).encode()
    return 200, HAL, ACCOUNT.replace(ACCOUNT_ID, account).encode()


def stream(connection: Connection) -> None:
    """Stream the payments of the small account, as those of the account asked for."""
    account = urlsplit(connection.path).path.split("/")[2]
    events = [
        f"id: {payment['paging_token']}\ndata: "
        + json.dumps(payment).replace(SMALL_ACCOUNT, account)
        for payment in PAYMENTS
    ]
    connection.send(OPEN, *events, CLOSE)


def work(client: HorizonClient, thread: int) -> None:
    for call in range(CALLS):
        account = name(thread, call)
        params = {"thread": str(thread), "call": str(call)}
        query = f"thread={thread}&call={call}"

        echoed: Any = client.request("GET", f"/echo/{account}", params=params).json()
        assert echoed == {
            "method": "GET",
            "path": f"/echo/{account}?{query}",
            "body": "",
        }
        echoed = client.request("POST", f"/echo/{account}", data=params).json()
        assert echoed == {"method": "POST", "path": f"/echo/{account}", "body": query}

        found = client.accounts.get(account)
        assert (found.account_id, found.sequence) == (account, SEQUENCE)

        first = client.payments.list(account=account, order="asc", limit=2)
        second = first.next()
        payments = [*first, *second]
        assert [payment.id for payment in payments] == PAYMENT_IDS
        assert [payment.source_account for payment in payments] == [
            FUNDER,
            account,
            account,
        ]

        envelope = f"envelope of {account}"
        assert client.transactions.submit(envelope).envelope_xdr == envelope

    account = name(thread, "STREAM")
    with client.payments.stream(account=account) as payments_stream:
        streamed = [next(payments_stream) for _ in PAYMENTS]
    assert [payment.id for payment in streamed] == PAYMENT_IDS
    assert [payment.source_account for payment in streamed] == [
        FUNDER,
        account,
        account,
    ]


def gil_is_off() -> bool:
    """Tell whether the GIL is off, which it can be only on a free-threaded build."""
    is_enabled = getattr(sys, "_is_gil_enabled", None)
    return is_enabled is not None and not is_enabled()


def test_threads_share_one_client() -> None:
    failures: list[Exception] = []
    barrier = threading.Barrier(THREADS, timeout=WAIT)

    def run(client: HorizonClient, thread: int) -> None:
        try:
            # All threads start at once, so that their calls overlap.
            barrier.wait()
            work(client, thread)
        except Exception as error:  # noqa: BLE001
            failures.append(error)

    with (
        LocalHorizon(stream, router=route) as local,
        HorizonClient(local.url, max_retries=0) as client,
    ):
        threads = [
            threading.Thread(target=run, args=(client, thread), daemon=True)
            for thread in range(THREADS)
        ]
        for each in threads:
            each.start()
        deadline = time.monotonic() + WAIT
        for each in threads:
            each.join(max(deadline - time.monotonic(), 0))
        assert not [each for each in threads if each.is_alive()], "a thread hangs"
    if failures:
        msg = "a thread failed"
        raise ExceptionGroup(msg, failures)

    # Every request was sent once: none was repeated, none was lost.
    expected: Counter[str] = Counter()
    for thread in range(THREADS):
        for call in range(CALLS):
            account = name(thread, call)
            expected[f"/echo/{account}"] += 2
            expected[f"/accounts/{account}"] += 1
            expected[f"/accounts/{account}/payments"] += 2
            expected["/transactions"] += 1
        expected["/"] += 1
        expected[f"/accounts/{name(thread, 'STREAM')}/payments"] += 1
    assert Counter(urlsplit(path).path for path in local.requests) == expected
    assert local.failures == []

    # On a free-threaded build, nothing that was imported turned the GIL back on, so
    # the threads ran at the same time.
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        assert gil_is_off(), "a module turned the GIL back on"
