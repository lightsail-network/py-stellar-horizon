# Generated from _async/test_client.py by scripts/unasync.py. Do not edit.
# pyright: reportPrivateUsage=false
"""Making a client: its base URL, headers and timeout, and `request()`."""

from importlib.metadata import PackageNotFoundError

import httpx2
import pytest

from stellar_horizon import BadRequestError, HorizonClient, NotFoundError
from stellar_horizon._sync import _client, _stream
from tests._sync.clients import client_for
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


@pytest.mark.parametrize("url", ["ftp://horizon.test", "horizon.test", "https://"])
def test_base_url_must_be_http(url: str) -> None:
    with pytest.raises(ValueError, match="http or https"):
        HorizonClient(url)


@pytest.mark.parametrize("url", ["http://[::1", "https://horizon\x00.test"])
def test_base_url_must_be_a_url(url: str) -> None:
    with pytest.raises(ValueError, match="not a URL") as caught:
        HorizonClient(url)
    assert isinstance(caught.value.__cause__, httpx2.InvalidURL)


def test_base_url_has_no_fragment() -> None:
    with pytest.raises(ValueError, match="fragment"):
        HorizonClient(BASE + "/#a")


def test_http_client_must_be_of_the_flavour() -> None:
    with pytest.raises(TypeError, match=r"httpx2\.Client"):
        HorizonClient(BASE, http_client=object())  # type: ignore[arg-type]


def test_http_client_must_not_send_last_event_id() -> None:
    http = httpx2.Client(headers={"Last-Event-ID": "5"})
    with pytest.raises(ValueError, match="Last-Event-ID"):
        HorizonClient(BASE, http_client=http)
    http.close()


def test_headers_must_not_hold_last_event_id() -> None:
    with pytest.raises(ValueError, match="Last-Event-ID"):
        HorizonClient(BASE, headers={"last-event-id": "5"})


def test_headers_are_sent_with_every_request(horizon: FakeHorizon) -> None:
    horizon.on(f"/accounts/{ACCOUNT_ID}", captured("account.json"))
    horizon.on("/payments", captured(FIRST_STREAM))
    horizon.on("/transactions", captured("submissions/success.json"))
    http = httpx2.Client(
        transport=httpx2.MockTransport(horizon),
        headers={"Authorization": "from the http client", "X-Proxy": "kept"},
    )
    client = HorizonClient(
        BASE,
        http_client=http,
        headers={"authorization": "Bearer key", "x-client-name": "my-wallet"},
    )
    with client:
        client.accounts.get(ACCOUNT_ID)
        with client.payments.stream() as stream:
            next(stream)
        client.transactions.submit("AAAA")
        client.request(
            "GET", f"/accounts/{ACCOUNT_ID}", headers={"Authorization": "just once"}
        )
    http.close()
    *every, last = horizon.requests
    assert len(every) == 4  # the account, `/` for `now`, the stream, the submission
    for request in every:
        assert request.headers.get_list("authorization") == ["Bearer key"]
        assert request.headers.get_list("x-client-name") == ["my-wallet"]
        assert request.headers["x-proxy"] == "kept"
        assert request.headers["x-client-version"]
    assert last.headers.get_list("authorization") == ["just once"]


def test_timeout_rule(horizon: FakeHorizon) -> None:
    explicit = client_for(horizon, timeout=3)
    assert explicit._session.timeout == httpx2.Timeout(3)
    plain = client_for(horizon)
    assert plain._session.timeout == httpx2.Timeout(60)
    http = httpx2.Client(timeout=20)
    injected = HorizonClient(BASE, http_client=http)
    assert injected._session.timeout == httpx2.Timeout(20)
    assert plain._session.stream_timeout.read == _stream.READ_TIMEOUT
    with HorizonClient(BASE) as own:
        assert own._session.timeout == httpx2.Timeout(60)
    http.close()


def test_closing_leaves_an_injected_client_open(horizon: FakeHorizon) -> None:
    client = client_for(horizon)
    with client:
        pass
    assert not client._session.http.is_closed
    assert repr(client) == f"<HorizonClient {BASE}>"


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("https://provider.test/v1/secret-key", "https://provider.test"),
        ("https://provider.test/?apikey=secret", "https://provider.test"),
        ("http://localhost:8000/horizon", "http://localhost:8000"),
    ],
)
def test_repr_leaves_out_what_can_hold_a_key(url: str, shown: str) -> None:
    with HorizonClient(url) as client:
        assert repr(client) == f"<HorizonClient {shown}>"
        assert str(client.base_url) == url


def test_identification_headers(horizon: FakeHorizon) -> None:
    with client_for(horizon, app_name="wallet", app_version="2.0") as client:
        client.root()
    headers = horizon.requests[0].headers
    assert headers["X-Client-Name"] == "py-stellar-horizon"
    assert headers["X-Client-Version"]
    assert (headers["X-App-Name"], headers["X-App-Version"]) == ("wallet", "2.0")


def test_identification_without_the_metadata_of_the_package(
    horizon: FakeHorizon, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A program packed into one file, by PyInstaller for example, can lack it.
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(_client, "version", missing)
    with client_for(horizon) as client:
        client.root()
    assert horizon.requests[0].headers["X-Client-Version"] == "unknown"


def test_base_url_prefix_is_kept(horizon: FakeHorizon) -> None:
    horizon.on(f"/prefix/accounts/{ACCOUNT_ID}", captured("account.json"))
    with client_for(horizon, BASE + "/prefix/") as client:
        account = client.accounts.get(ACCOUNT_ID)
    assert account.account_id == ACCOUNT_ID


def test_base_url_query_is_sent_with_every_request(horizon: FakeHorizon) -> None:
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
    with client_for(horizon, BASE + "/v1?apikey=key&network=public") as client:
        client.accounts.get(ACCOUNT_ID)
        listed = client.payments.list(account=SMALL_ACCOUNT, limit=2)
        listed.next()
        with client.payments.stream() as stream:
            next(stream)
        client.transactions.submit("AAAA")
        client.request("GET", f"/accounts/{ACCOUNT_ID}", params={"apikey": "other"})
    assert len(horizon.requests) == 7
    for request in horizon.requests:
        assert request.url.params.get_list("apikey") == ["key"], request.url
        assert request.url.params["network"] == "public"
    assert horizon.requests[2].url.params["cursor"] == listed.records[-1].paging_token


def test_path_segments_are_encoded(horizon: FakeHorizon) -> None:
    with client_for(horizon) as client:
        with pytest.raises(NotFoundError):
            client.accounts.get("G/X?")
    assert horizon.requests[0].url.raw_path == b"/accounts/G%2FX%3F"


def test_request(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", captured("errors/transaction_malformed.json"))
    with client_for(horizon) as client:
        response = client.request("get", "", params={"a": "1"})
        assert response.json()["horizon_version"] == ROOT["horizon_version"]
        with pytest.raises(BadRequestError) as caught:
            client.request(
                "POST", "/transactions", data={"tx": "AAAA"}, headers={"X-Test": "1"}
            )
        with pytest.raises(NotFoundError):
            client.request("GET", "/nothing")
    assert caught.value.type == "transaction_malformed"
    posted = horizon.requests[1]
    assert (posted.method, posted.content, posted.headers["X-Test"]) == (
        "POST",
        b"tx=AAAA",
        "1",
    )
    assert posted.headers["X-Client-Name"] == "py-stellar-horizon"
