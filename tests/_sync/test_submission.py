# Generated from _async/test_submission.py by scripts/unasync.py. Do not edit.
"""Submitting and enqueueing a transaction: the three outcomes."""

import httpx2
import pytest

from stellar_horizon import (
    BadRequestError,
    OutcomeUnknownError,
    ResponseError,
    ServerError,
    TransactionFailedError,
    TransportError,
)
from tests._sync.clients import client_for
from tests.support import FakeHorizon, captured, json_response, load, problem, redirect


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
