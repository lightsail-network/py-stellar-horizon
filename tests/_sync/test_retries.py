# Generated from _async/test_retries.py by scripts/unasync.py. Do not edit.
"""A failed `GET` is tried again; nothing else is."""

import logging

import httpx2
import pytest

from stellar_horizon import (
    HorizonClient,
    NotFoundError,
    OutcomeUnknownError,
    ServerError,
    TransportError,
)
from stellar_horizon._sync import _session
from tests._sync.clients import client_for
from tests.support import (
    ACCOUNT_ID,
    BASE,
    MISSING_ACCOUNT,
    SMALL_ACCOUNT,
    SMALL_PAYMENTS,
    FakeHorizon,
    captured,
    json_response,
    problem,
    records,
)


@pytest.fixture
def slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waited: list[float] = []

    def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(_session, "_sleep", sleep)
    return waited


def test_two_retries_by_default(horizon: FakeHorizon, slept: list[float]) -> None:
    horizon.on(f"/accounts/{ACCOUNT_ID}", json_response(503, problem("timeout", 503)))
    http = httpx2.Client(transport=httpx2.MockTransport(horizon))
    with HorizonClient(BASE, http_client=http) as client:
        with pytest.raises(ServerError):
            client.accounts.get(ACCOUNT_ID)
    assert (len(horizon.requests), len(slept)) == (3, 2)


def test_no_retries_with_zero(horizon: FakeHorizon, slept: list[float]) -> None:
    horizon.on(f"/accounts/{ACCOUNT_ID}", json_response(503, problem("timeout", 503)))
    with client_for(horizon, max_retries=0) as client:
        with pytest.raises(ServerError):
            client.accounts.get(ACCOUNT_ID)
    assert (len(horizon.requests), slept) == (1, [])


def test_a_get_is_tried_again(
    horizon: FakeHorizon, slept: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    # Synthetic: a proxy that fails, a rate limit, then the captured account.
    horizon.on(
        f"/accounts/{ACCOUNT_ID}",
        httpx2.Response(502, content=b"<html>"),
        json_response(429, problem("rate_limit_exceeded", 429), **{"Retry-After": "3"}),
        httpx2.ConnectError("refused"),
        captured("account.json"),
    )
    with client_for(horizon, max_retries=3) as client:
        with caplog.at_level(logging.WARNING, logger="stellar_horizon"):
            account = client.accounts.get(ACCOUNT_ID)
    assert account.account_id == ACCOUNT_ID
    assert len(horizon.requests) == 4
    assert len(slept) == 3
    assert slept[1] == 3
    assert len(caplog.records) == 3


def test_retries_run_out(horizon: FakeHorizon, slept: list[float]) -> None:
    horizon.on("/ledgers", json_response(504, problem("timeout", 504)))
    with client_for(horizon, max_retries=2) as client:
        with pytest.raises(ServerError):
            client.ledgers.list()
    assert (len(horizon.requests), len(slept)) == (3, 2)


@pytest.mark.usefixtures("slept")
def test_a_not_found_is_not_tried_again(horizon: FakeHorizon) -> None:
    with client_for(horizon, max_retries=3) as client:
        with pytest.raises(NotFoundError):
            client.accounts.get(MISSING_ACCOUNT)
    assert len(horizon.requests) == 1


@pytest.mark.usefixtures("slept")
def test_next_is_tried_again(horizon: FakeHorizon) -> None:
    first, second = "pages/payments_1.json", "pages/payments_2.json"
    horizon.on(
        SMALL_PAYMENTS,
        captured(first),
        json_response(503, problem("still_ingesting", 503)),
        captured(second),
    )
    with client_for(horizon, max_retries=1) as client:
        page = client.payments.list(account=SMALL_ACCOUNT, order="asc", limit=2)
        following = page.next()
    assert len(following) == len(records(second))


@pytest.mark.usefixtures("slept")
def test_a_post_is_never_tried_again(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", httpx2.ConnectError("refused"))
    horizon.on("/transactions_async", json_response(503, problem("timeout", 503)))
    with client_for(horizon, max_retries=3) as client:
        with pytest.raises(TransportError):
            client.transactions.submit("AAAA")
        with pytest.raises(OutcomeUnknownError):
            client.transactions.enqueue("AAAA")
        with pytest.raises(TransportError):
            client.request("POST", "/transactions", data={"tx": "AAAA"})
    assert len(horizon.requests) == 3


@pytest.mark.usefixtures("slept")
def test_request_is_sent_once(horizon: FakeHorizon) -> None:
    horizon.on("/ledgers", json_response(503, problem("timeout", 503)))
    with client_for(horizon, max_retries=3) as client:
        with pytest.raises(ServerError):
            client.request("GET", "/ledgers")
    assert len(horizon.requests) == 1


def test_max_retries_is_checked() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        HorizonClient(BASE, max_retries=-1)
