import copy
import json
import pickle
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from stellar_horizon.errors import (
    BadRequestError,
    BeforeHistoryError,
    HorizonError,
    InvalidResponseError,
    NotFoundError,
    OutcomeUnknownError,
    RateLimitError,
    ResponseError,
    ServerError,
    StreamError,
    TransactionFailedError,
    error_for,
    problem_of,
    retry_after,
)
from tests.support import captured, load, problem

PREFIX = "https://stellar.org/horizon-errors/"


def response(status: int, body: Any = None, **headers: str) -> httpx2.Response:
    content = b"" if body is None else json.dumps(body).encode()
    if isinstance(body, str):
        content = body.encode()
    return httpx2.Response(status, content=content, headers=headers)


@pytest.mark.parametrize(
    ("name", "cls", "type_"),
    [
        ("errors/not_found_account.json", NotFoundError, "not_found"),
        ("errors/not_found_route.json", NotFoundError, "not_found"),
        (
            "errors/invalid_accounts_params.json",
            BadRequestError,
            "invalid_accounts_params",
        ),
        ("errors/bad_request_limit.json", BadRequestError, "bad_request"),
        ("errors/bad_request_cursor.json", BadRequestError, "bad_request"),
        ("errors/bad_request_order.json", BadRequestError, "bad_request"),
        ("errors/before_history.json", BeforeHistoryError, "before_history"),
        ("errors/not_acceptable.json", ResponseError, "not_acceptable"),
        ("errors/server_error.json", ServerError, "server_error"),
        (
            "errors/transaction_malformed.json",
            BadRequestError,
            "transaction_malformed",
        ),
        (
            "errors/unsupported_media_type.json",
            ResponseError,
            "unsupported_media_type",
        ),
        (
            "errors/transaction_failed.json",
            TransactionFailedError,
            "transaction_failed",
        ),
    ],
)
def test_class_of_a_captured_error(
    name: str, cls: type[ResponseError], type_: str
) -> None:
    error = error_for(captured(name))
    assert type(error) is cls
    assert error.type == type_
    assert error.problem is not None
    assert error.status_code == error.problem.status


@pytest.mark.parametrize(
    ("type_", "status", "cls"),
    [
        ("transaction_submission_disabled", 403, ResponseError),
        ("rate_limit_exceeded", 429, RateLimitError),
        ("stale_history", 503, ServerError),
        ("timeout", 504, ServerError),
        ("transaction_submission_timeout", 504, ServerError),
    ],
)
def test_class_of_an_error_no_public_server_gives(
    type_: str, status: int, cls: type[ResponseError]
) -> None:
    # Synthetic: these need a server that is failing, disabled or overloaded.
    error = error_for(response(status, problem(type_, status)))
    assert type(error) is cls
    assert error.type == type_


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (400, BadRequestError),
        (404, NotFoundError),
        (410, BeforeHistoryError),
        (429, RateLimitError),
        (418, ResponseError),
        (502, ServerError),
    ],
)
def test_class_by_status_without_a_problem(
    status: int, cls: type[ResponseError]
) -> None:
    # Synthetic: a proxy in front of Horizon answers with a page of its own.
    error = error_for(response(status, "<html>Bad Gateway</html>"))
    assert type(error) is cls
    assert error.problem is None
    assert error.type is None
    assert str(error) == f"HTTP {status}"


@pytest.mark.parametrize(
    ("location", "where"),
    [
        # The path and the query can hold a key, so only the scheme and host are shown.
        (
            "https://horizon.test:8443/v1/key?apikey=key",
            " to https://horizon.test:8443",
        ),
        ("https://horizon.test:443/", " to https://horizon.test"),
        ("/accounts/", ""),
        ("http://[::1", ""),
        (None, ""),
    ],
)
def test_redirect_says_where_to(location: str | None, where: str) -> None:
    # Synthetic: a redirect, as a load balancer answers `http://` with.
    headers = {} if location is None else {"Location": location}
    error = error_for(response(301, "<html>Moved</html>", **headers))
    assert type(error) is ResponseError
    assert error.problem is None
    assert str(error) == (
        f"HTTP 301: a redirect{where}, which the client does not follow"
    )


def test_unknown_problem_type_falls_back_to_the_status() -> None:
    # Synthetic: a problem type that a newer Horizon could add.
    error = error_for(response(404, problem("brand_new", 404)))
    assert type(error) is NotFoundError
    assert error.type == "brand_new"


def test_message_has_the_detail_or_the_title() -> None:
    found = load("errors/not_found_route.json")
    assert str(error_for(captured("errors/not_found_route.json"))) == (
        f"HTTP 404 not_found: {found['detail']}"
    )
    # A 406 has no detail.
    title = load("errors/not_acceptable.json")["title"]
    assert str(error_for(captured("errors/not_acceptable.json"))) == (
        f"HTTP 406 not_acceptable: {title}"
    )


@pytest.mark.parametrize(
    ("name", "field"),
    [
        ("errors/bad_request_limit.json", "limit"),
        ("errors/bad_request_cursor.json", "cursor"),
        ("errors/bad_request_order.json", "order"),
    ],
)
def test_bad_request_names_the_field(name: str, field: str) -> None:
    error = error_for(captured(name))
    assert isinstance(error, BadRequestError)
    assert error.invalid_field == field
    assert error.reason


def test_bad_request_without_extras() -> None:
    error = error_for(captured("errors/invalid_accounts_params.json"))
    assert isinstance(error, BadRequestError)
    assert error.invalid_field is None
    assert error.reason is None


def test_transaction_failed_extras() -> None:
    body = load("errors/transaction_failed.json")
    error = error_for(captured("errors/transaction_failed.json"))
    assert isinstance(error, TransactionFailedError)
    assert error.envelope_xdr == body["extras"]["envelope_xdr"]
    assert error.result_xdr == body["extras"]["result_xdr"]
    assert error.result_codes is not None
    assert error.result_codes.transaction == "tx_no_source_account"
    assert error.diagnostic_events == []
    assert error.extras == body["extras"]


def test_transaction_failed_with_diagnostic_events() -> None:
    # Synthetic: a failed contract call, which needs a deployed contract to capture.
    body = problem("transaction_failed", 400, diagnostic_events=["CCCC", 5])
    error = error_for(response(400, body))
    assert isinstance(error, TransactionFailedError)
    assert error.diagnostic_events == ["CCCC"]
    assert error.result_codes is None
    assert error.envelope_xdr is None
    assert error.result_xdr is None


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("2", 2.0),
        ("0.5", 0.5),
        ("-1", None),
        ("soon", None),
        ("inf", None),
        ("Infinity", None),
        ("1e400", None),
        ("nan", None),
    ],
)
def test_retry_after(header: str, expected: float | None) -> None:
    error = error_for(
        response(429, problem("rate_limit_exceeded", 429), **{"Retry-After": header})
    )
    assert isinstance(error, RateLimitError)
    assert error.retry_after == expected


def test_retry_after_absent() -> None:
    assert retry_after(response(429)) is None


def test_problem_of_rejects_other_json() -> None:
    assert problem_of(response(400, {"error": "nope"})) is None
    assert problem_of(response(400, [1, 2])) is None


def test_errors_keep_what_the_caller_needs() -> None:
    sent = response(504, problem("transaction_submission_timeout", 504))
    unknown = OutcomeUnknownError(
        "no answer", envelope_xdr="AAAA", hash="ab", response=sent
    )
    assert (unknown.envelope_xdr, unknown.hash, unknown.response) == (
        "AAAA",
        "ab",
        sent,
    )
    invalid = InvalidResponseError("unreadable", body={"a": 1}, response=sent)
    assert (invalid.body, invalid.response) == ({"a": 1}, sent)
    stream = StreamError("gave up", cursor="12")
    assert stream.cursor == "12"


def carried(error: HorizonError) -> tuple[str, dict[str, Any], object]:
    """What an error says and carries, in a form that compares by value."""
    kept = dict(vars(error))
    sent: httpx2.Response | None = kept.pop("response", None)
    return str(error), kept, sent and (sent.status_code, sent.headers, sent.content)


def through_pickle(error: HorizonError) -> HorizonError:
    restored: HorizonError = pickle.loads(pickle.dumps(error))  # noqa: S301
    return restored


def through_copy(error: HorizonError) -> HorizonError:
    return copy.copy(error)


def noted(error: HorizonError) -> HorizonError:
    error.add_note("raised by worker 3")
    return error


@pytest.mark.parametrize(
    "clone", [through_pickle, through_copy], ids=["pickle", "copy"]
)
@pytest.mark.parametrize(
    "error",
    [
        error_for(captured("errors/transaction_failed.json")),
        error_for(response(502, "<html>Bad Gateway</html>")),
        OutcomeUnknownError("no answer", envelope_xdr="AAAA"),
        OutcomeUnknownError(
            "late", envelope_xdr="AAAA", hash="ab", response=response(504)
        ),
        InvalidResponseError("unreadable", body={"a": 1}, response=response(200)),
        StreamError("gave up", cursor="12"),
        StreamError("gave up", cursor=None),
        noted(error_for(captured("errors/not_found_account.json"))),
    ],
    ids=[
        "a problem",
        "no problem",
        "unknown without a response",
        "unknown with a response",
        "invalid response",
        "stream with a cursor",
        "stream without a cursor",
        "a note",
    ],
)
def test_errors_survive_pickle_and_copy(
    error: HorizonError, clone: Callable[[HorizonError], HorizonError]
) -> None:
    # A process pool pickles what a worker raises, to hand it to the parent.
    back = clone(error)
    assert type(back) is type(error)
    assert back is not error
    assert carried(back) == carried(error)


def test_a_note_survives_pickle() -> None:
    error = noted(StreamError("gave up", cursor="12"))
    assert through_pickle(error).__notes__ == ["raised by worker 3"]
