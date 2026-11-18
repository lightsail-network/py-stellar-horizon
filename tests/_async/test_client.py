# pyright: reportPrivateUsage=false
"""Making a client: its base URL, headers and timeout, and `request()`."""

from importlib.metadata import PackageNotFoundError

import httpx2
import pytest

from stellar_horizon import AsyncHorizonClient, BadRequestError, NotFoundError
from stellar_horizon._async import _client, _stream
from tests._async.clients import client_for
from tests.support import (
    ACCOUNT_ID,
    BASE,
    FIRST_STREAM,
    ROOT,
    SMALL_ACCOUNT,
    SMALL_PAYMENTS,
    FakeHorizon,
    captured,
    json_response,
    load,
)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("url", ["ftp://horizon.test", "horizon.test", "https://"])
async def test_base_url_must_be_http(url: str) -> None:
    with pytest.raises(ValueError, match="http or https"):
        AsyncHorizonClient(url)


@pytest.mark.parametrize("url", ["http://[::1", "https://horizon\x00.test"])
async def test_base_url_must_be_a_url(url: str) -> None:
    with pytest.raises(ValueError, match="not a URL") as caught:
        AsyncHorizonClient(url)
    assert isinstance(caught.value.__cause__, httpx2.InvalidURL)


async def test_base_url_has_no_fragment() -> None:
    with pytest.raises(ValueError, match="fragment"):
        AsyncHorizonClient(BASE + "/#a")


async def test_http_client_must_be_of_the_flavour() -> None:
    with pytest.raises(TypeError, match=r"httpx2\.AsyncClient"):
        AsyncHorizonClient(BASE, http_client=object())  # type: ignore[arg-type]


async def test_http_client_must_not_send_last_event_id() -> None:
    http = httpx2.AsyncClient(headers={"Last-Event-ID": "5"})
    with pytest.raises(ValueError, match="Last-Event-ID"):
        AsyncHorizonClient(BASE, http_client=http)
    await http.aclose()


async def test_headers_must_not_hold_last_event_id() -> None:
    with pytest.raises(ValueError, match="Last-Event-ID"):
        AsyncHorizonClient(BASE, headers={"last-event-id": "5"})


async def test_headers_are_sent_with_every_request(horizon: FakeHorizon) -> None:
    horizon.on(f"/accounts/{ACCOUNT_ID}", captured("account.json"))
    horizon.on("/payments", captured(FIRST_STREAM))
    horizon.on("/transactions", captured("submissions/success.json"))
    http = httpx2.AsyncClient(
        transport=httpx2.MockTransport(horizon),
        headers={"Authorization": "from the http client", "X-Proxy": "kept"},
    )
    client = AsyncHorizonClient(
        BASE,
        http_client=http,
        headers={"authorization": "Bearer key", "x-client-name": "my-wallet"},
    )
    async with client:
        await client.accounts.get(ACCOUNT_ID)
        async with client.payments.stream() as stream:
            await anext(stream)
        await client.transactions.submit("AAAA")
        await client.request(
            "GET", f"/accounts/{ACCOUNT_ID}", headers={"Authorization": "just once"}
        )
    await http.aclose()
    *every, last = horizon.requests
    assert len(every) == 4  # the account, `/` for `now`, the stream, the submission
    for request in every:
        assert request.headers.get_list("authorization") == ["Bearer key"]
        assert request.headers.get_list("x-client-name") == ["my-wallet"]
        assert request.headers["x-proxy"] == "kept"
        assert request.headers["x-client-version"]
    assert last.headers.get_list("authorization") == ["just once"]


async def test_timeout_rule(horizon: FakeHorizon) -> None:
    explicit = client_for(horizon, timeout=3)
    assert explicit._session.timeout == httpx2.Timeout(3)
    plain = client_for(horizon)
    assert plain._session.timeout == httpx2.Timeout(60)
    http = httpx2.AsyncClient(timeout=20)
    injected = AsyncHorizonClient(BASE, http_client=http)
    assert injected._session.timeout == httpx2.Timeout(20)
    assert plain._session.stream_timeout.read == _stream.READ_TIMEOUT
    async with AsyncHorizonClient(BASE) as own:
        assert own._session.timeout == httpx2.Timeout(60)
    await http.aclose()


async def test_closing_leaves_an_injected_client_open(horizon: FakeHorizon) -> None:
    client = client_for(horizon)
    async with client:
        pass
    assert not client._session.http.is_closed
    assert repr(client) == f"<AsyncHorizonClient {BASE}>"


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://provider.test/v1/secret-key", "https://provider.test"),
        ("https://provider.test/?apikey=secret", "https://provider.test"),
        ("http://localhost:8000/horizon", "http://localhost:8000"),
    ],
)
async def test_repr_leaves_out_what_can_hold_a_key(url: str, shown: str) -> None:
    async with AsyncHorizonClient(url) as client:
        assert repr(client) == f"<AsyncHorizonClient {shown}>"
        assert str(client.base_url) == url


async def test_identification_headers(horizon: FakeHorizon) -> None:
    async with client_for(horizon, app_name="wallet", app_version="2.0") as client:
        await client.root()
    headers = horizon.requests[0].headers
    assert headers["X-Client-Name"] == "py-stellar-horizon"
    assert headers["X-Client-Version"]
    assert (headers["X-App-Name"], headers["X-App-Version"]) == ("wallet", "2.0")


async def test_identification_without_the_metadata_of_the_package(
    horizon: FakeHorizon, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A program packed into one file, by PyInstaller for example, can lack it.
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(_client, "version", missing)
    async with client_for(horizon) as client:
        await client.root()
    assert horizon.requests[0].headers["X-Client-Version"] == "unknown"


async def test_base_url_prefix_is_kept(horizon: FakeHorizon) -> None:
    horizon.on(f"/prefix/accounts/{ACCOUNT_ID}", captured("account.json"))
    async with client_for(horizon, BASE + "/prefix/") as client:
        account = await client.accounts.get(ACCOUNT_ID)
    assert account.account_id == ACCOUNT_ID


async def test_base_url_query_is_sent_with_every_request(horizon: FakeHorizon) -> None:
    # The links are mocked to echo the key, with another value, as a proxy could.
    first = load("pages/payments_1.json")
    first["_links"]["next"]["href"] += "&apikey=echoed"
    horizon.on(f"/v1/accounts/{ACCOUNT_ID}", captured("account.json"))
    horizon.on(
        f"/v1{SMALL_PAYMENTS}",
        json_response(200, first),
        captured("pages/payments_2.json"),
    )
    horizon.on("/v1/payments", captured(FIRST_STREAM))
    horizon.on("/v1/transactions", captured("submissions/success.json"))
    horizon.on("/v1", captured("root.json"))
    async with client_for(horizon, BASE + "/v1?apikey=key&network=public") as client:
        await client.accounts.get(ACCOUNT_ID)
        listed = await client.payments.list(account=SMALL_ACCOUNT, limit=2)
        await listed.next()
        async with client.payments.stream() as stream:
            await anext(stream)
        await client.transactions.submit("AAAA")
        await client.request(
            "GET", f"/accounts/{ACCOUNT_ID}", params={"apikey": "other"}
        )
    assert len(horizon.requests) == 7
    for request in horizon.requests:
        assert request.url.params.get_list("apikey") == ["key"], request.url
        assert request.url.params["network"] == "public"
    assert horizon.requests[2].url.params["cursor"] == listed.records[-1].paging_token


async def test_path_segments_are_encoded(horizon: FakeHorizon) -> None:
    async with client_for(horizon) as client:
        with pytest.raises(NotFoundError):
            await client.accounts.get("G/X?")
    assert horizon.requests[0].url.raw_path == b"/accounts/G%2FX%3F"


async def test_request(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", captured("errors/transaction_malformed.json"))
    async with client_for(horizon) as client:
        response = await client.request("get", "", params={"a": "1"})
        assert response.json()["horizon_version"] == ROOT["horizon_version"]
        with pytest.raises(BadRequestError) as caught:
            await client.request(
                "POST", "/transactions", data={"tx": "AAAA"}, headers={"X-Test": "1"}
            )
        with pytest.raises(NotFoundError):
            await client.request("GET", "/nothing")
    assert caught.value.type == "transaction_malformed"
    posted = horizon.requests[1]
    assert (posted.method, posted.content, posted.headers["X-Test"]) == (
        "POST",
        b"tx=AAAA",
        "1",
    )
    assert posted.headers["X-Client-Name"] == "py-stellar-horizon"
