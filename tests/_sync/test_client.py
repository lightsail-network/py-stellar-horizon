# Generated from _async/test_client.py by scripts/unasync.py. Do not edit.
# pyright: reportPrivateUsage=false
"""The client against a fake server that answers with captured responses.

Bodies come unchanged from `tests/fixtures`, captured from the public networks. Where no
public server gives an answer on request, a test builds one and says so:

- answers that need a failing server: 503 `still_ingesting` and `stale_history`, 504
  `transaction_submission_timeout`, a 502 page from a proxy, a 429;
- broken connections and timeouts;
- `error` events in the middle of a stream;
- bodies that are not what Horizon sends, to test that they are refused;
- a redirect, as a load balancer in front of Horizon answers `http://` with, and a body
  that cannot be decoded;
- an object stream that sends the same object twice.
"""

import json
import logging
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

from stellar_horizon import (
    BadRequestError,
    BeforeHistoryError,
    HorizonClient,
    InvalidResponseError,
    NotFoundError,
    OutcomeUnknownError,
    Page,
    PagingError,
    ResponseError,
    ServerError,
    Stream,
    StreamError,
    TransactionFailedError,
    TransportError,
    _reading,
    errors,
)
from stellar_horizon import _requests as rq
from stellar_horizon._sync import _client, _session, _stream
from stellar_horizon.models import Account, Operation, Transaction
from tests.support import (
    OPEN,
    FakeHorizon,
    captured,
    event_ids,
    json_response,
    load,
    manifest,
    problem,
    sse,
)

BASE = "https://horizon.test"
ROOT = load("root.json")
NOW = str(ROOT["history_latest_ledger"] << 32 | 0xFFFFFFFF)
ACCOUNT = load("account.json")
ACCOUNT_ID = ACCOUNT["account_id"]
MISSING_ACCOUNT = manifest()["errors/not_found_account.json"]["url"].rsplit("/", 1)[1]
SMALL_ACCOUNT = "GBVF5SBMKRAVL5L2L3F2KUKYFKXTX7ZL57JB4NQUP7LEDDK2XPEZQUNA"
SMALL_PAYMENTS = f"/accounts/{SMALL_ACCOUNT}/payments"
TRANSACTIONS = load("transactions.json")
TRANSACTION = TRANSACTIONS["_embedded"]["records"][0]
FIRST_STREAM = "streams/payments_1.sse"
SECOND_STREAM = "streams/payments_2.sse"


def records_of(name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = load(name)["_embedded"]["records"]
    return records


@pytest.fixture
def horizon() -> FakeHorizon:
    fake = FakeHorizon()
    fake.on("/", captured("root.json"))
    return fake


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waited: list[float] = []

    def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(_stream, "_sleep", sleep)
    return waited


def redirect(location: str, status: int = 301) -> httpx2.Response:
    """Synthetic: a redirect, as a load balancer answers `http://` with."""
    return httpx2.Response(
        status, headers={"location": location}, content=b"<html>Moved</html>"
    )


def client_for(horizon: FakeHorizon, base: str = BASE, **options: Any) -> HorizonClient:
    # Most tests look at one answer, so they turn the default retries off; the tests
    # of retries say what they want.
    options.setdefault("max_retries", 0)
    http = httpx2.Client(transport=httpx2.MockTransport(horizon))
    return HorizonClient(base, http_client=http, **options)


# The client.


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


@pytest.mark.usefixtures("waits")
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


@pytest.mark.usefixtures("waits")
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


# Reading.


def test_root(horizon: FakeHorizon) -> None:
    with client_for(horizon) as client:
        root = client.root()
    assert root.history_latest_ledger == ROOT["history_latest_ledger"]


def test_account(horizon: FakeHorizon) -> None:
    horizon.on(f"/accounts/{ACCOUNT_ID}", captured("account.json"))
    with client_for(horizon) as client:
        account = client.accounts.get(ACCOUNT_ID)
    assert isinstance(account, Account)
    assert account.sequence == int(ACCOUNT["sequence"])


def test_not_found(horizon: FakeHorizon) -> None:
    horizon.on(
        f"/accounts/{MISSING_ACCOUNT}",
        captured("errors/not_found_account.json"),
    )
    with client_for(horizon) as client:
        with pytest.raises(NotFoundError) as caught:
            client.accounts.get(MISSING_ACCOUNT)
    assert (caught.value.status_code, caught.value.type) == (404, "not_found")


def test_bad_request(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", captured("errors/bad_request_limit.json"))
    with client_for(horizon) as client:
        with pytest.raises(BadRequestError) as caught:
            client.transactions.list(limit=500)
    assert caught.value.invalid_field == "limit"


def test_before_history(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", captured("errors/before_history.json"))
    with client_for(horizon) as client:
        with pytest.raises(BeforeHistoryError):
            client.transactions.list(order="desc", cursor=1 << 32)


def test_server_error(horizon: FakeHorizon) -> None:
    horizon.on("/accounts", captured("errors/server_error.json"))
    with client_for(horizon) as client:
        with pytest.raises(ServerError) as caught:
            client.accounts.list(signer=ACCOUNT_ID)
    assert caught.value.type == "server_error"


def test_transport_error(horizon: FakeHorizon) -> None:
    # Synthetic: the connection fails.
    horizon.on(f"/accounts/{ACCOUNT_ID}", httpx2.ConnectError("refused"))
    with client_for(horizon) as client:
        with pytest.raises(TransportError, match="refused") as caught:
            client.accounts.get(ACCOUNT_ID)
    assert isinstance(caught.value.__cause__, httpx2.ConnectError)


def test_body_that_cannot_be_decoded(horizon: FakeHorizon) -> None:
    # Synthetic: broken gzip, which httpx2 reports with an error that is not one
    # of its transport errors.
    broken = httpx2.DecodingError("incorrect header check")
    horizon.on(f"/accounts/{ACCOUNT_ID}", broken)
    with client_for(horizon) as client:
        with pytest.raises(TransportError, match="incorrect header") as caught:
            client.accounts.get(ACCOUNT_ID)
    assert caught.value.__cause__ is broken


def test_redirect_is_an_error(horizon: FakeHorizon) -> None:
    # The address is shown by scheme and host only: its path and query can hold a
    # key, as those of the base URL can.
    moved = redirect("https://horizon.test:8443/v1/key/accounts?apikey=key")
    horizon.on(f"/accounts/{ACCOUNT_ID}", moved)
    with client_for(horizon, max_retries=2) as client:
        with pytest.raises(ResponseError) as caught:
            client.accounts.get(ACCOUNT_ID)
    assert str(caught.value) == (
        "HTTP 301: a redirect to https://horizon.test:8443, "
        "which the client does not follow"
    )
    assert caught.value.response is moved
    assert len(horizon.requests) == 1


@pytest.fixture
def too_deep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the JSON decoder give up on every body, as it does on one nested too deep.

    The decoder then raises `RecursionError`, which is not a `ValueError`. At which
    depth depends on the interpreter and on the stack of the platform, so the tests do
    not rely on a real body to get there.
    """

    def loads(_: object) -> object:
        msg = "maximum recursion depth exceeded"
        raise RecursionError(msg)

    stand_in = SimpleNamespace(loads=loads)
    monkeypatch.setattr(_reading, "json", stand_in)
    monkeypatch.setattr(errors, "json", stand_in)


@pytest.mark.usefixtures("too_deep", "waits")
def test_body_nested_too_deep(horizon: FakeHorizon) -> None:
    # A server could send one to make the client raise what is not a HorizonError.
    horizon.on(f"/accounts/{ACCOUNT_ID}", captured("account.json"))
    horizon.on("/ledgers", captured("errors/server_error.json"))
    horizon.on("/transactions", captured("submissions/success.json"))
    horizon.on("/transactions_async", captured("errors/server_error.json"))
    horizon.on("/payments", captured(FIRST_STREAM))
    with client_for(horizon) as client:
        with pytest.raises(InvalidResponseError, match="not JSON"):
            client.accounts.get(ACCOUNT_ID)
        with pytest.raises(ServerError) as caught:
            client.ledgers.list()
        with pytest.raises(OutcomeUnknownError, match="not JSON"):
            client.transactions.submit("AAAA")
        with pytest.raises(OutcomeUnknownError):
            client.transactions.enqueue("AAAA")
        with pytest.raises(InvalidResponseError, match="not JSON"):
            with client.payments.stream(cursor="1") as stream:
                next(stream)
    assert caught.value.problem is None


@pytest.mark.parametrize(
    ("content", "match"), [(b"<html>", "not JSON"), (b'{"id": 1}', "cannot be read")]
)
def test_unreadable_response(horizon: FakeHorizon, content: bytes, match: str) -> None:
    # Synthetic: bodies that Horizon does not send.
    horizon.on(f"/accounts/{ACCOUNT_ID}", httpx2.Response(200, content=content))
    with client_for(horizon) as client:
        with pytest.raises(InvalidResponseError, match=match) as caught:
            client.accounts.get(ACCOUNT_ID)
    assert caught.value.response.status_code == 200


def test_transactions(horizon: FakeHorizon) -> None:
    hash_ = TRANSACTION["hash"]
    horizon.on(f"/transactions/{hash_}", json_response(200, TRANSACTION))
    horizon.on("/transactions", captured("transactions.json"))
    with client_for(horizon) as client:
        transaction = client.transactions.get(hash_.upper())
        listed = client.transactions.list(include_failed=True, limit=50)
    assert isinstance(transaction, Transaction)
    assert transaction.hash == hash_
    assert len(listed) == len(TRANSACTIONS["_embedded"]["records"])
    assert horizon.requests[-1].url.params["include_failed"] == "true"


def test_payments(horizon: FakeHorizon) -> None:
    horizon.on(SMALL_PAYMENTS, captured("pages/payments_1.json"))
    with client_for(horizon) as client:
        listed = client.payments.list(account=SMALL_ACCOUNT, limit=2)
    assert [payment.id for payment in listed] == [
        record["id"] for record in records_of("pages/payments_1.json")
    ]


# Pages.


def test_next_and_prev_follow_the_query_of_a_link(horizon: FakeHorizon) -> None:
    horizon.on(
        SMALL_PAYMENTS,
        captured("pages/payments_1.json"),
        captured("pages/payments_2.json"),
        captured("pages/payments_2_prev.json"),
    )
    with client_for(horizon) as client:
        first = client.payments.list(account=SMALL_ACCOUNT, order="asc", limit=2)
        assert isinstance(first, Page)
        assert repr(first) == "<Page of 2 records>"
        second = first.next()
        back = second.prev()
    # The links name horizon.stellar.org; only their query is used.
    assert all(request.url.host == "horizon.test" for request in horizon.requests)
    assert horizon.requests[1].url.params["cursor"] == first.records[-1].paging_token
    # Horizon's prev link inverts the order.
    assert horizon.requests[2].url.params["order"] == "desc"
    assert [p.id for p in back] == [p.id for p in reversed(first.records)]


def test_iter_records_goes_on_past_a_short_page(horizon: FakeHorizon) -> None:
    names = [f"pages/payments_{n}.json" for n in (1, 2, 3)]
    horizon.on(SMALL_PAYMENTS, *[captured(name) for name in names])
    with client_for(horizon) as client:
        first = client.payments.list(account=SMALL_ACCOUNT, order="asc", limit=2)
        ids = [payment.id for payment in first.iter_records()]
    assert ids == [record["id"] for name in names for record in records_of(name)]
    assert len(ids) == 3
    assert len(horizon.requests) == 3  # the last page is empty


def test_iter_records_stops_after_max_records(horizon: FakeHorizon) -> None:
    horizon.on(SMALL_PAYMENTS, captured("pages/payments_1.json"))
    with client_for(horizon) as client:
        first = client.payments.list(account=SMALL_ACCOUNT, limit=2)
        assert len([p for p in first.iter_records(max_records=1)]) == 1
        assert len([p for p in first.iter_records(max_records=2)]) == 2
        with pytest.raises(ValueError, match="negative"):
            [p for p in first.iter_records(max_records=-1)]
    assert len(horizon.requests) == 1


def test_an_empty_page_has_links_but_no_records(horizon: FakeHorizon) -> None:
    horizon.on(SMALL_PAYMENTS, captured("pages/payments_3.json"))
    with client_for(horizon) as client:
        empty = client.payments.list(account=SMALL_ACCOUNT)
    assert len(empty) == 0
    assert set(empty.links) == {"self", "next", "prev"}


def test_page_without_a_link(horizon: FakeHorizon) -> None:
    # Synthetic: Horizon always sends prev, except an empty one for trade aggregations.
    body = load("pages/payments_1.json")
    body["_links"]["prev"]["href"] = ""
    horizon.on(SMALL_PAYMENTS, json_response(200, body))
    with client_for(horizon) as client:
        listed = client.payments.list(account=SMALL_ACCOUNT)
        with pytest.raises(PagingError, match="no prev page"):
            listed.prev()


def test_page_link_to_another_endpoint(horizon: FakeHorizon) -> None:
    # Synthetic: a link that a proxy or a broken server could send.
    body = load("pages/payments_1.json")
    # It can echo a key of the base URL, so the error does not show the link.
    body["_links"]["next"]["href"] = BASE + "/offers?cursor=1&apikey=secret"
    horizon.on(SMALL_PAYMENTS, json_response(200, body))
    with client_for(horizon) as client:
        listed = client.payments.list(account=SMALL_ACCOUNT)
        with pytest.raises(PagingError, match="another endpoint") as caught:
            listed.next()
    assert "secret" not in str(caught.value)
    assert "secret" in listed.links["next"]


def test_iter_records_refuses_a_page_that_links_to_itself(
    horizon: FakeHorizon,
) -> None:
    # Synthetic: Horizon's next link always moves past the last record.
    body = load("pages/payments_1.json")
    body["_links"]["next"]["href"] = BASE + SMALL_PAYMENTS + "?limit=2"
    horizon.on(SMALL_PAYMENTS, json_response(200, body))
    with client_for(horizon) as client:
        first = client.payments.list(account=SMALL_ACCOUNT, limit=2)
        with pytest.raises(PagingError, match="repeats"):
            [p for p in first.iter_records()]


@pytest.mark.parametrize(
    "body",
    [{"_embedded": {}}, {"_embedded": {"records": {}}}, [], {"_links": {}, "x": 1}],
)
def test_a_body_that_is_not_a_page(horizon: FakeHorizon, body: object) -> None:
    # Synthetic: bodies that Horizon does not send.
    horizon.on("/transactions", json_response(200, body))
    with client_for(horizon) as client:
        with pytest.raises(InvalidResponseError, match="not a page"):
            client.transactions.list()


def test_odd_links_are_ignored(horizon: FakeHorizon) -> None:
    # Synthetic: links of shapes that Horizon does not send.
    body = load("pages/payments_3.json")
    body["_links"] = {"next": "x", "prev": {"href": 5}, "self": {"href": "/s"}}
    horizon.on("/transactions", json_response(200, body))
    with client_for(horizon) as client:
        listed = client.transactions.list()
    assert listed.links == {"self": "/s"}


def test_links_may_be_absent(horizon: FakeHorizon) -> None:
    # Synthetic: Horizon sends links with every page.
    horizon.on("/transactions", json_response(200, {"_embedded": {"records": []}}))
    with client_for(horizon) as client:
        listed = client.transactions.list()
    assert listed.links == {}


# The escape hatch.


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


# Retries.


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
    assert len(following) == len(records_of(second))


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


# Data entries and SEP-29.

MEMO_ACCOUNT = manifest()["account_data/memo_required.json"]["url"].split("/")[-3]
MEMO_REQUIRED = f"/accounts/{MEMO_ACCOUNT}/data/config.memo_required"


def test_data(horizon: FakeHorizon) -> None:
    horizon.on(MEMO_REQUIRED, captured("account_data/memo_required.json"))
    with client_for(horizon) as client:
        entry = client.accounts.data(MEMO_ACCOUNT, "config.memo_required")
    assert (entry.value, entry.sponsor) == (b"1", None)


def test_data_not_found(horizon: FakeHorizon) -> None:
    horizon.on(
        f"/accounts/{MEMO_ACCOUNT}/data/no.such.key",
        captured("errors/not_found_data.json"),
    )
    with client_for(horizon) as client:
        with pytest.raises(NotFoundError):
            client.accounts.data(MEMO_ACCOUNT, "no.such.key")


def test_data_key_is_encoded(horizon: FakeHorizon) -> None:
    with client_for(horizon) as client:
        with pytest.raises(NotFoundError):
            client.accounts.data(MEMO_ACCOUNT, "a/b c")
        # A name that a URL would take for the parent directory is sent as a name.
        with pytest.raises(NotFoundError):
            client.accounts.data(MEMO_ACCOUNT, "..")
    assert horizon.paths() == [
        f"/accounts/{MEMO_ACCOUNT}/data/a%2Fb%20c",
        f"/accounts/{MEMO_ACCOUNT}/data/%2E%2E",
    ]


@pytest.mark.usefixtures("waits")
def test_stream_data(horizon: FakeHorizon) -> None:
    horizon.on(MEMO_REQUIRED, captured("streams/account_data.sse"))
    with (
        client_for(horizon) as client,
        client.accounts.stream_data(MEMO_ACCOUNT, "config.memo_required") as stream,
    ):
        entry = next(stream)
    assert entry.value == b"1"
    assert horizon.requests[0].headers["accept"] == "text/event-stream"
    assert "cursor" not in horizon.requests[0].url.params


def test_requires_memo(horizon: FakeHorizon) -> None:
    horizon.on(MEMO_REQUIRED, captured("account_data/memo_required.json"))
    with client_for(horizon) as client:
        assert client.accounts.requires_memo(MEMO_ACCOUNT)


def test_requires_memo_not_for_another_value(horizon: FakeHorizon) -> None:
    # Synthetic: a value other than 1.
    horizon.on(MEMO_REQUIRED, json_response(200, {"value": "MA=="}))
    with client_for(horizon) as client:
        assert not client.accounts.requires_memo(MEMO_ACCOUNT)


def test_requires_memo_not_without_the_entry(horizon: FakeHorizon) -> None:
    # The fake answers every unknown path with 404, like a missing entry or account.
    with client_for(horizon) as client:
        assert not client.accounts.requires_memo(ACCOUNT_ID)
    assert horizon.paths() == [f"/accounts/{ACCOUNT_ID}/data/config.memo_required"]


def test_requires_memo_not_for_a_muxed_address(horizon: FakeHorizon) -> None:
    muxed = "MAAAAAAAAAAAAAB7BQ2L7E5NBWMXDUCMZSIPOBKRDSBYVLMXGSSKF6YNPIB7Y77ITLVL6"
    with client_for(horizon) as client:
        assert not client.accounts.requires_memo(muxed)
    assert horizon.requests == []


def test_requires_memo_raises_other_errors(horizon: FakeHorizon) -> None:
    horizon.on(MEMO_REQUIRED, captured("errors/server_error.json"))
    with client_for(horizon) as client:
        with pytest.raises(ServerError):
            client.accounts.requires_memo(MEMO_ACCOUNT)


# Submission.


def test_submit(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", captured("submissions/success.json"))
    with client_for(horizon) as client:
        transaction = client.transactions.submit("AAAA")
    assert transaction.successful
    assert transaction.hash == load("submissions/success.json")["hash"]
    assert horizon.requests[0].content == b"tx=AAAA"


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        (captured("errors/transaction_failed.json"), TransactionFailedError),
        (captured("errors/transaction_malformed.json"), BadRequestError),
        # Synthetic from here: no public server gives these on request.
        (json_response(503, problem("stale_history", 503)), ServerError),
        (redirect("https://horizon.test/transactions", 308), ResponseError),
        (httpx2.ConnectError("refused"), TransportError),
        (httpx2.ConnectTimeout("slow"), TransportError),
    ],
)
def test_submit_refused(
    horizon: FakeHorizon, answer: httpx2.Response | Exception, error: type[Exception]
) -> None:
    horizon.on("/transactions", answer)
    with client_for(horizon) as client:
        with pytest.raises(error):
            client.transactions.submit("AAAA")
    assert len(horizon.requests) == 1


def test_submit_failed_has_the_result_codes(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", captured("errors/transaction_failed.json"))
    with client_for(horizon) as client:
        with pytest.raises(TransactionFailedError) as caught:
            client.transactions.submit("AAAA")
    assert caught.value.result_codes is not None
    assert caught.value.result_codes.transaction == "tx_no_source_account"


@pytest.mark.parametrize(
    ("answer", "hash_"),
    [
        (captured("errors/server_error.json"), None),
        # Synthetic from here: a submission timeout, a proxy and broken connections.
        (
            json_response(
                504, problem("transaction_submission_timeout", 504, hash="ab")
            ),
            "ab",
        ),
        (httpx2.Response(502, content=b"<html>"), None),
        (httpx2.ReadTimeout("slow"), None),
        (httpx2.RemoteProtocolError("reset"), None),
        (httpx2.DecodingError("broken gzip"), None),
        (json_response(200, {"hash": 5}), None),
    ],
)
def test_submit_outcome_unknown(
    horizon: FakeHorizon, answer: httpx2.Response | Exception, hash_: str | None
) -> None:
    horizon.on("/transactions", answer)
    with client_for(horizon) as client:
        with pytest.raises(OutcomeUnknownError) as caught:
            client.transactions.submit("AAAA")
    assert (caught.value.envelope_xdr, caught.value.hash) == ("AAAA", hash_)
    assert len(horizon.requests) == 1


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("submissions/async_pending.json", "PENDING"),
        ("submissions/async_resubmitted.json", "DUPLICATE"),
        ("submissions/async_error.json", "ERROR"),
    ],
)
def test_enqueue_returns_every_status(
    horizon: FakeHorizon, name: str, status: str
) -> None:
    horizon.on("/transactions_async", captured(name))
    with client_for(horizon) as client:
        result = client.transactions.enqueue("AAAA")
    assert result.tx_status == status
    assert result.hash == load(name)["hash"]
    assert result.error_result_xdr == load(name).get("error_result_xdr")
    assert horizon.requests[0].content == b"tx=AAAA"


def test_enqueue_returns_try_again_later(horizon: FakeHorizon) -> None:
    # Synthetic: stellar-core gives it only when its queue is full.
    body = {"tx_status": "TRY_AGAIN_LATER", "hash": "ab"}
    horizon.on("/transactions_async", json_response(503, body))
    with client_for(horizon) as client:
        result = client.transactions.enqueue("AAAA")
    assert result.tx_status == "TRY_AGAIN_LATER"
    assert len(horizon.requests) == 1


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        (captured("errors/transaction_malformed.json"), BadRequestError),
        # Synthetic from here: no public server gives these on request.
        (json_response(503, problem("stale_history", 503)), ServerError),
        (redirect("https://horizon.test/transactions_async"), ResponseError),
        (httpx2.ConnectError("refused"), TransportError),
        # A status this package does not know is not a result.
        (json_response(400, {"tx_status": "LOST", "hash": "ab"}), BadRequestError),
    ],
)
def test_enqueue_refused(
    horizon: FakeHorizon, answer: httpx2.Response | Exception, error: type[Exception]
) -> None:
    horizon.on("/transactions_async", answer)
    with client_for(horizon) as client:
        with pytest.raises(error):
            client.transactions.enqueue("AAAA")
    assert len(horizon.requests) == 1


@pytest.mark.parametrize(
    "answer",
    [
        # Synthetic: stellar-core failing, a proxy and broken connections.
        json_response(500, problem("transaction_submission_exception", 500)),
        httpx2.Response(502, content=b"<html>"),
        httpx2.ReadTimeout("slow"),
        httpx2.DecodingError("broken gzip"),
        # A body with a field missing is not a result.
        json_response(201, {"tx_status": "PENDING"}),
    ],
)
def test_enqueue_outcome_unknown(
    horizon: FakeHorizon, answer: httpx2.Response | Exception
) -> None:
    horizon.on("/transactions_async", answer)
    with client_for(horizon) as client:
        with pytest.raises(OutcomeUnknownError) as caught:
            client.transactions.enqueue("AAAA")
    assert caught.value.envelope_xdr == "AAAA"


def test_enqueue_takes_only_a_string(horizon: FakeHorizon) -> None:
    with client_for(horizon) as client:
        with pytest.raises(TypeError, match="base64 XDR"):
            client.transactions.enqueue(b"AAAA")  # type: ignore[arg-type]
    assert horizon.requests == []


# Streams.


def test_stream_starts_now_and_continues_from_the_last_record(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    horizon.on(
        "/payments",
        captured(FIRST_STREAM),
        captured("streams/quiet.sse"),
        captured(SECOND_STREAM),
    )
    first_ids, second_ids = event_ids(FIRST_STREAM), event_ids(SECOND_STREAM)
    with (
        client_for(horizon) as client,
        client.payments.stream() as stream,
    ):
        assert stream.cursor == NOW
        ids = [(next(stream)).id for _ in range(len(first_ids) + 1)]
        assert stream.cursor == second_ids[0]
    assert ids == [*first_ids, second_ids[0]]
    streams = [r for r in horizon.requests if r.url.path != "/"]
    # The quiet connection delivered nothing, so the cursor stayed.
    assert [r.url.params["cursor"] for r in streams] == [
        NOW,
        first_ids[-1],
        first_ids[-1],
    ]
    assert all(r.url.params["limit"] == "200" for r in streams)
    assert all(r.headers["accept"] == "text/event-stream" for r in streams)
    # The server's retry time after each `close`.
    assert waits == [0.01, 0.01]


@pytest.mark.usefixtures("waits")
def test_stream_from_the_oldest_history(horizon: FakeHorizon) -> None:
    horizon.on("/payments", captured(FIRST_STREAM))
    with client_for(horizon) as client:
        stream = client.payments.stream(cursor=None)
        assert stream.cursor is None
        record = next(stream)
        stream.close()
    assert record.id == event_ids(FIRST_STREAM)[0]
    assert horizon.paths() == ["/payments"]
    assert "cursor" not in horizon.requests[0].url.params


def test_stream_from_an_empty_cursor(horizon: FakeHorizon) -> None:
    # Horizon reads an empty cursor as none, and starts at the oldest history it
    # keeps. The client sends it as it is, and does not ask the root for `now`.
    horizon.on("/payments", captured(FIRST_STREAM))
    with (
        client_for(horizon) as client,
        client.payments.stream(cursor="") as stream,
    ):
        record = next(stream)
    assert record.id == event_ids(FIRST_STREAM)[0]
    assert horizon.paths() == ["/payments"]
    assert horizon.requests[0].url.params["cursor"] == ""


@pytest.mark.usefixtures("waits")
def test_stream_from_a_cursor(horizon: FakeHorizon) -> None:
    cursor = event_ids(FIRST_STREAM)[-1]
    horizon.on(SMALL_PAYMENTS, captured(SECOND_STREAM))
    with (
        client_for(horizon) as client,
        client.payments.stream(account=SMALL_ACCOUNT, cursor=cursor) as stream,
    ):
        assert stream.cursor == cursor
        next(stream)
    # A cursor is sent as it is: the client does not ask the server anything first.
    assert horizon.paths() == [SMALL_PAYMENTS]
    assert horizon.requests[0].url.params["cursor"] == cursor


def test_stream_raises_what_does_not_pass(horizon: FakeHorizon) -> None:
    horizon.on("/payments", captured("errors/bad_request_cursor.json"))
    with client_for(horizon) as client:
        with pytest.raises(BadRequestError):
            with client.payments.stream(cursor="-1") as stream:
                next(stream)
    assert horizon.paths() == ["/payments"]


def test_stream_retries_what_passes(
    horizon: FakeHorizon, waits: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    # Synthetic: a failing server, a silent connection and an error event.
    horizon.on(
        "/payments",
        json_response(503, problem("still_ingesting", 503)),
        json_response(429, problem("rate_limit_exceeded", 429), **{"Retry-After": "7"}),
        httpx2.ReadTimeout("silent"),
        httpx2.DecodingError("broken gzip"),
        sse(OPEN, "event: error\ndata: problem: timeout. full details: late"),
        captured(FIRST_STREAM),
    )
    caplog.set_level(logging.WARNING, logger="stellar_horizon")
    with client_for(horizon) as client, client.payments.stream() as stream:
        record = next(stream)
    assert record.id == event_ids(FIRST_STREAM)[0]
    assert len(waits) == 5
    assert waits[1] >= 7
    assert len(caplog.records) == 5
    # `now` is resolved once, when the stream is entered.
    assert horizon.paths().count("/") == 1


def test_stream_ends_at_a_redirect(horizon: FakeHorizon, waits: list[float]) -> None:
    # A redirect stays, so waiting for it to pass would only hide it. The same
    # holds for the root, which a stream that starts now reads first.
    horizon.on("/payments", redirect("https://horizon.test/payments"))
    with client_for(horizon) as client:
        with pytest.raises(ResponseError, match="redirect"):
            with client.payments.stream(cursor="1") as stream:
                next(stream)
        horizon.on("/", redirect("https://horizon.test/"))
        with pytest.raises(ResponseError, match="redirect"):
            with client.payments.stream() as stream:
                next(stream)
    assert waits == []
    assert horizon.paths() == ["/payments", "/"]


@pytest.mark.usefixtures("waits")
def test_stream_gives_up(horizon: FakeHorizon) -> None:
    # Synthetic: the server cannot be reached.
    horizon.on("/payments", httpx2.ConnectError("refused"))
    with client_for(horizon) as client:
        with pytest.raises(StreamError, match="no working connection") as caught:
            with client.payments.stream(give_up_after=0) as stream:
                next(stream)
    assert caught.value.cursor == NOW
    assert isinstance(caught.value.__cause__, httpx2.ConnectError)


@pytest.mark.usefixtures("waits")
def test_stream_ends_at_an_error_that_stays(horizon: FakeHorizon) -> None:
    # Synthetic: an error event in the middle of a stream.
    horizon.on(
        "/payments",
        sse(OPEN, "event: error\ndata: problem: not_found. full details: x"),
    )
    with client_for(horizon) as client:
        with pytest.raises(StreamError, match="not_found"):
            with client.payments.stream() as stream:
                next(stream)


@pytest.mark.usefixtures("waits")
def test_stream_record_that_cannot_be_read(horizon: FakeHorizon) -> None:
    # Synthetic: records that Horizon does not send.
    horizon.on(
        "/payments", sse(OPEN, 'id: 5\ndata: {"id": "5"}'), sse(OPEN, "data: nope")
    )
    with client_for(horizon) as client:
        with pytest.raises(InvalidResponseError, match="cannot be read"):
            with client.payments.stream() as stream:
                next(stream)
        stream = client.payments.stream()
        with pytest.raises(InvalidResponseError, match="not JSON"):
            with stream:
                next(stream)
        # The record that cannot be read does not move the cursor.
        assert stream.cursor == NOW


def test_stream_waits_for_the_root_at_the_start(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    # Synthetic: the root fails twice, in ways that pass, before it answers.
    horizon.on(
        "/",
        json_response(503, problem("still_ingesting", 503), **{"Retry-After": "4"}),
        httpx2.ConnectError("refused"),
        captured("root.json"),
    )
    horizon.on("/payments", captured(FIRST_STREAM))
    with client_for(horizon, max_retries=5) as client:
        stream = client.payments.stream()
        with stream:
            assert stream.cursor == NOW
            next(stream)
    assert horizon.paths()[:4] == ["/", "/", "/", "/payments"]
    assert horizon.requests[3].url.params["cursor"] == NOW
    # The stream's rule, not max_retries: the first wait is no shorter than 4 seconds.
    assert waits[0] >= 4
    assert len(waits) >= 2


def test_stream_start_that_fails_tries_again_when_read_again(
    horizon: FakeHorizon,
) -> None:
    # Synthetic: a root that cannot be read the first time.
    horizon.on(
        "/", json_response(404, problem("not_found", 404)), captured("root.json")
    )
    horizon.on("/payments", captured(FIRST_STREAM))
    with client_for(horizon) as client:
        stream = client.payments.stream()
        with pytest.raises(NotFoundError):
            next(stream)
        # Read again, the stream resolves `now` instead of starting without a cursor.
        next(stream)
        stream.close()
    assert horizon.paths()[:3] == ["/", "/", "/payments"]
    assert horizon.requests[2].url.params["cursor"] == NOW


@pytest.mark.usefixtures("waits")
def test_stream_gives_up_on_the_root(horizon: FakeHorizon) -> None:
    horizon.on("/", json_response(503, problem("still_ingesting", 503)))
    with client_for(horizon) as client:
        stream = client.payments.stream(give_up_after=0)
        with pytest.raises(StreamError, match="still_ingesting") as caught:
            stream.__enter__()
    assert caught.value.cursor is None
    assert "/payments" not in horizon.paths()


def test_stream_close_before_use(horizon: FakeHorizon) -> None:
    with client_for(horizon) as client:
        stream = client.payments.stream()
        stream.close()
    assert horizon.requests == []


@pytest.mark.usefixtures("waits")
def test_stream_survives_a_reset_after_delivering(horizon: FakeHorizon) -> None:
    # Synthetic: the connection breaks after the first record of a real stream.
    events = captured(FIRST_STREAM).content.split(b"\n\n")

    def body() -> Iterator[bytes]:
        yield b"\n\n".join(events[:2]) + b"\n\n"
        raise httpx2.ReadError("reset")

    reset = httpx2.Response(
        200, content=body(), headers={"content-type": "text/event-stream"}
    )
    unknown_event = sse(OPEN, "event: other\ndata: x")
    horizon.on("/payments", reset, unknown_event, captured(SECOND_STREAM))
    with client_for(horizon) as client, client.payments.stream() as stream:
        first, second = (next(stream)).id, (next(stream)).id
    assert [first, second] == [event_ids(FIRST_STREAM)[0], event_ids(SECOND_STREAM)[0]]
    streams = [r for r in horizon.requests if r.url.path != "/"]
    assert streams[1].url.params["cursor"] == first


def test_stream_that_is_silent_until_the_timeout_is_replaced_at_once(
    horizon: FakeHorizon, waits: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    # Synthetic: a quiet connection, which the client ends by its read timeout. It is
    # not a failure: nothing is logged, and the next connection follows without a wait.
    def body() -> Iterator[bytes]:
        yield (OPEN + "\n\n").encode()
        raise httpx2.ReadTimeout("silent")

    quiet = httpx2.Response(
        200, content=body(), headers={"content-type": "text/event-stream"}
    )
    horizon.on("/payments", quiet, captured(FIRST_STREAM))
    caplog.set_level(logging.WARNING, logger="stellar_horizon")
    with (
        client_for(horizon) as client,
        client.payments.stream(cursor="1") as stream,
    ):
        record = next(stream)
    assert record.id == event_ids(FIRST_STREAM)[0]
    assert waits == [0]
    assert caplog.records == []
    assert [request.url.params["cursor"] for request in horizon.requests] == ["1", "1"]


def test_stream_that_ends_early_is_a_failure(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    # Synthetic: a connection that opens and ends without `close`.
    horizon.on("/payments", sse(OPEN), captured(FIRST_STREAM))
    with client_for(horizon) as client:
        stream = client.payments.stream(cursor=None)
        records = [record.id for record in _first(stream)]
    assert records == [event_ids(FIRST_STREAM)[0]]
    assert len(waits) == 1
    assert 0.5 <= waits[0] <= 1.0  # the first wait after a failure, with jitter


def _first(stream: Stream[Operation]) -> Iterator[Operation]:
    with stream:
        for record in stream:
            yield record
            return


@pytest.mark.usefixtures("waits")
def test_object_stream_drops_repeats(horizon: FakeHorizon) -> None:
    # Synthetic events around a real account: Horizon sends an account once.
    same = f"data: {json.dumps(ACCOUNT)}"
    changed = f"data: {json.dumps(ACCOUNT | {'sequence': '1'})}"
    horizon.on(f"/accounts/{ACCOUNT_ID}", sse(OPEN, same, same, changed))
    with client_for(horizon) as client:
        stream = client._session.stream(
            rq.account(ACCOUNT_ID), kind="object", cursor=None, give_up_after=None
        )
        with stream:
            assert (next(stream)).sequence == int(ACCOUNT["sequence"])
            assert (next(stream)).sequence == 1
            assert stream.cursor is None
    assert "cursor" not in horizon.requests[0].url.params
