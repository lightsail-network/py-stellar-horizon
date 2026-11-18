"""A failed `GET` is tried again; nothing else is."""

import logging

import httpx2
import pytest

from stellar_horizon import (
    AsyncHorizonClient,
    NotFoundError,
    OutcomeUnknownError,
    ServerError,
    TransportError,
)
from stellar_horizon._async import _session
from tests._async.clients import client_for
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

pytestmark = pytest.mark.anyio


@pytest.fixture
def slept(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waited: list[float] = []

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(_session, "_sleep", sleep)
    return waited


async def test_two_retries_by_default(horizon: FakeHorizon, slept: list[float]) -> None:
    horizon.on(f"/accounts/{ACCOUNT_ID}", json_response(503, problem("timeout", 503)))
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(horizon))
    async with AsyncHorizonClient(BASE, http_client=http) as client:
        with pytest.raises(ServerError):
            await client.accounts.get(ACCOUNT_ID)
    assert (len(horizon.requests), len(slept)) == (3, 2)


async def test_no_retries_with_zero(horizon: FakeHorizon, slept: list[float]) -> None:
    horizon.on(f"/accounts/{ACCOUNT_ID}", json_response(503, problem("timeout", 503)))
    async with client_for(horizon, max_retries=0) as client:
        with pytest.raises(ServerError):
            await client.accounts.get(ACCOUNT_ID)
    assert (len(horizon.requests), slept) == (1, [])


async def test_a_get_is_tried_again(
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
    async with client_for(horizon, max_retries=3) as client:
        with caplog.at_level(logging.WARNING, logger="stellar_horizon"):
            account = await client.accounts.get(ACCOUNT_ID)
    assert account.account_id == ACCOUNT_ID
    assert len(horizon.requests) == 4
    assert len(slept) == 3
    assert slept[1] == 3
    assert len(caplog.records) == 3


async def test_retries_run_out(horizon: FakeHorizon, slept: list[float]) -> None:
    horizon.on("/ledgers", json_response(504, problem("timeout", 504)))
    async with client_for(horizon, max_retries=2) as client:
        with pytest.raises(ServerError):
            await client.ledgers.list()
    assert (len(horizon.requests), len(slept)) == (3, 2)


@pytest.mark.usefixtures("slept")
async def test_a_not_found_is_not_tried_again(horizon: FakeHorizon) -> None:
    async with client_for(horizon, max_retries=3) as client:
        with pytest.raises(NotFoundError):
            await client.accounts.get(MISSING_ACCOUNT)
    assert len(horizon.requests) == 1


@pytest.mark.usefixtures("slept")
async def test_next_is_tried_again(horizon: FakeHorizon) -> None:
    first, second = "pages/payments_1.json", "pages/payments_2.json"
    horizon.on(
        SMALL_PAYMENTS,
        captured(first),
        json_response(503, problem("still_ingesting", 503)),
        captured(second),
    )
    async with client_for(horizon, max_retries=1) as client:
        page = await client.payments.list(account=SMALL_ACCOUNT, order="asc", limit=2)
        following = await page.next()
    assert len(following) == len(records(second))


@pytest.mark.usefixtures("slept")
async def test_a_post_is_never_tried_again(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", httpx2.ConnectError("refused"))
    horizon.on("/transactions_async", json_response(503, problem("timeout", 503)))
    async with client_for(horizon, max_retries=3) as client:
        with pytest.raises(TransportError):
            await client.transactions.submit("AAAA")
        with pytest.raises(OutcomeUnknownError):
            await client.transactions.enqueue("AAAA")
        with pytest.raises(TransportError):
            await client.request("POST", "/transactions", data={"tx": "AAAA"})
    assert len(horizon.requests) == 3


@pytest.mark.usefixtures("slept")
async def test_request_is_sent_once(horizon: FakeHorizon) -> None:
    horizon.on("/ledgers", json_response(503, problem("timeout", 503)))
    async with client_for(horizon, max_retries=3) as client:
        with pytest.raises(ServerError):
            await client.request("GET", "/ledgers")
    assert len(horizon.requests) == 1


async def test_max_retries_is_checked() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        AsyncHorizonClient(BASE, max_retries=-1)
