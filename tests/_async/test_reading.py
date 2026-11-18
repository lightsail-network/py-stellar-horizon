"""Reading a resource, and what is raised when that fails."""

from types import SimpleNamespace

import httpx2
import pytest

from stellar_horizon import (
    BadRequestError,
    BeforeHistoryError,
    InvalidResponseError,
    NotFoundError,
    OutcomeUnknownError,
    ResponseError,
    ServerError,
    TransportError,
    _reading,
    errors,
)
from stellar_horizon.models import Account, Transaction
from tests._async.clients import client_for
from tests.support import (
    ACCOUNT,
    ACCOUNT_ID,
    FIRST_STREAM,
    MISSING_ACCOUNT,
    ROOT,
    SMALL_ACCOUNT,
    SMALL_PAYMENTS,
    TRANSACTION,
    TRANSACTIONS,
    FakeHorizon,
    captured,
    json_response,
    records,
    redirect,
)

pytestmark = pytest.mark.anyio


async def test_root(horizon: FakeHorizon) -> None:
    async with client_for(horizon) as client:
        root = await client.root()
    assert root.history_latest_ledger == ROOT["history_latest_ledger"]


async def test_account(horizon: FakeHorizon) -> None:
    horizon.on(f"/accounts/{ACCOUNT_ID}", captured("account.json"))
    async with client_for(horizon) as client:
        account = await client.accounts.get(ACCOUNT_ID)
    assert isinstance(account, Account)
    assert account.sequence == int(ACCOUNT["sequence"])


async def test_not_found(horizon: FakeHorizon) -> None:
    horizon.on(
        f"/accounts/{MISSING_ACCOUNT}",
        captured("errors/not_found_account.json"),
    )
    async with client_for(horizon) as client:
        with pytest.raises(NotFoundError) as caught:
            await client.accounts.get(MISSING_ACCOUNT)
    assert (caught.value.status_code, caught.value.type) == (404, "not_found")


async def test_bad_request(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", captured("errors/bad_request_limit.json"))
    async with client_for(horizon) as client:
        with pytest.raises(BadRequestError) as caught:
            await client.transactions.list(limit=500)
    assert caught.value.invalid_field == "limit"


async def test_before_history(horizon: FakeHorizon) -> None:
    horizon.on("/transactions", captured("errors/before_history.json"))
    async with client_for(horizon) as client:
        with pytest.raises(BeforeHistoryError):
            await client.transactions.list(order="desc", cursor=1 << 32)


async def test_server_error(horizon: FakeHorizon) -> None:
    horizon.on("/accounts", captured("errors/server_error.json"))
    async with client_for(horizon) as client:
        with pytest.raises(ServerError) as caught:
            await client.accounts.list(signer=ACCOUNT_ID)
    assert caught.value.type == "server_error"


async def test_transport_error(horizon: FakeHorizon) -> None:
    # Synthetic: the connection fails.
    horizon.on(f"/accounts/{ACCOUNT_ID}", httpx2.ConnectError("refused"))
    async with client_for(horizon) as client:
        with pytest.raises(TransportError, match="refused") as caught:
            await client.accounts.get(ACCOUNT_ID)
    assert isinstance(caught.value.__cause__, httpx2.ConnectError)


async def test_body_that_cannot_be_decoded(horizon: FakeHorizon) -> None:
    # Synthetic: broken gzip, which httpx2 reports with an error that is not one
    # of its transport errors.
    broken = httpx2.DecodingError("incorrect header check")
    horizon.on(f"/accounts/{ACCOUNT_ID}", broken)
    async with client_for(horizon) as client:
        with pytest.raises(TransportError, match="incorrect header") as caught:
            await client.accounts.get(ACCOUNT_ID)
    assert caught.value.__cause__ is broken


async def test_redirect_is_an_error(horizon: FakeHorizon) -> None:
    # The address is shown by scheme and host only: its path and query can hold a
    # key, as those of the base URL can.
    moved = redirect("https://horizon.test:8443/v1/key/accounts?apikey=key")
    horizon.on(f"/accounts/{ACCOUNT_ID}", moved)
    async with client_for(horizon, max_retries=2) as client:
        with pytest.raises(ResponseError) as caught:
            await client.accounts.get(ACCOUNT_ID)
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


@pytest.mark.usefixtures("too_deep")
async def test_body_nested_too_deep(horizon: FakeHorizon) -> None:
    # A server could send one to make the client raise what is not a HorizonError.
    horizon.on(f"/accounts/{ACCOUNT_ID}", captured("account.json"))
    horizon.on("/ledgers", captured("errors/server_error.json"))
    horizon.on("/transactions", captured("submissions/success.json"))
    horizon.on("/transactions_async", captured("errors/server_error.json"))
    horizon.on("/payments", captured(FIRST_STREAM))
    async with client_for(horizon) as client:
        with pytest.raises(InvalidResponseError, match="not JSON"):
            await client.accounts.get(ACCOUNT_ID)
        with pytest.raises(ServerError) as caught:
            await client.ledgers.list()
        with pytest.raises(OutcomeUnknownError, match="not JSON"):
            await client.transactions.submit("AAAA")
        with pytest.raises(OutcomeUnknownError):
            await client.transactions.enqueue("AAAA")
        with pytest.raises(InvalidResponseError, match="not JSON"):
            async with client.payments.stream(cursor="1") as stream:
                await anext(stream)
    assert caught.value.problem is None


@pytest.mark.parametrize(
    ("content", "match"), [(b"<html>", "not JSON"), (b'{"id": 1}', "cannot be read")]
)
async def test_unreadable_response(
    horizon: FakeHorizon, content: bytes, match: str
) -> None:
    # Synthetic: bodies that Horizon does not send.
    horizon.on(f"/accounts/{ACCOUNT_ID}", httpx2.Response(200, content=content))
    async with client_for(horizon) as client:
        with pytest.raises(InvalidResponseError, match=match) as caught:
            await client.accounts.get(ACCOUNT_ID)
    assert caught.value.response.status_code == 200


async def test_transactions(horizon: FakeHorizon) -> None:
    hash_ = TRANSACTION["hash"]
    horizon.on(f"/transactions/{hash_}", json_response(200, TRANSACTION))
    horizon.on("/transactions", captured("transactions.json"))
    async with client_for(horizon) as client:
        transaction = await client.transactions.get(hash_.upper())
        listed = await client.transactions.list(include_failed=True, limit=50)
    assert isinstance(transaction, Transaction)
    assert transaction.hash == hash_
    assert len(listed) == len(TRANSACTIONS["_embedded"]["records"])
    assert horizon.requests[-1].url.params["include_failed"] == "true"


async def test_payments(horizon: FakeHorizon) -> None:
    horizon.on(SMALL_PAYMENTS, captured("pages/payments_1.json"))
    async with client_for(horizon) as client:
        listed = await client.payments.list(account=SMALL_ACCOUNT, limit=2)
    assert [payment.id for payment in listed] == [
        record["id"] for record in records("pages/payments_1.json")
    ]
