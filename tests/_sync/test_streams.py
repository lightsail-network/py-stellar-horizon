# Generated from _async/test_streams.py by scripts/unasync.py. Do not edit.
# pyright: reportPrivateUsage=false
"""Streams: where they start, and what follows when a connection ends."""

import json
import logging
from collections.abc import Iterator

import httpx2
import pytest

from stellar_horizon import (
    BadRequestError,
    InvalidResponseError,
    NotFoundError,
    ResponseError,
    Stream,
    StreamError,
)
from stellar_horizon import _requests as rq
from stellar_horizon.models import Operation
from tests._sync.clients import client_for
from tests.support import (
    ACCOUNT,
    ACCOUNT_ID,
    FIRST_STREAM,
    NOW,
    OPEN,
    SECOND_STREAM,
    SMALL_ACCOUNT,
    SMALL_PAYMENTS,
    FakeHorizon,
    captured,
    event_ids,
    json_response,
    problem,
    redirect,
    sse,
)


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


def test_stream_sends_its_own_accept_header(horizon: FakeHorizon) -> None:
    horizon.on("/payments", captured(FIRST_STREAM))
    with (
        client_for(horizon, headers={"Accept": "application/json"}) as client,
        client.payments.stream() as stream,
    ):
        next(stream)
    root, payments = horizon.requests
    assert root.url.path == "/"
    assert root.headers.get_list("accept") == ["application/json"]
    assert payments.headers.get_list("accept") == ["text/event-stream"]


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


def test_stream_ends_at_a_redirect_when_the_http_client_follows_them(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    horizon.on("/payments", redirect("https://elsewhere.test/moved", 307))
    with client_for(horizon, follow_redirects=True) as client:
        with pytest.raises(ResponseError, match="redirect"):
            with client.payments.stream(cursor="1") as stream:
                next(stream)
    assert waits == []
    assert horizon.paths() == ["/payments"]


def test_stream_gives_up(horizon: FakeHorizon) -> None:
    # Synthetic: the server cannot be reached.
    horizon.on("/payments", httpx2.ConnectError("refused"))
    with client_for(horizon) as client:
        with pytest.raises(StreamError, match="no working connection") as caught:
            with client.payments.stream(give_up_after=0) as stream:
                next(stream)
    assert caught.value.cursor == NOW
    assert isinstance(caught.value.__cause__, httpx2.ConnectError)


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


def test_stream_connects_afresh_once_the_root_answers(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    # Synthetic: the root fails until give_up_after is almost over, then answers, and
    # the first connection fails once.
    horizon.on(
        "/",
        httpx2.ConnectError("refused"),
        httpx2.ConnectError("refused"),
        httpx2.ConnectError("refused"),
        captured("root.json"),
    )
    horizon.on("/payments", httpx2.ConnectError("refused"), captured(FIRST_STREAM))
    with client_for(horizon) as client:
        stream = client.payments.stream(give_up_after=7)
        # Time passes only in the waits, and each wait is as long as it can be.
        stream._policy.clock = lambda: sum(waits)
        stream._policy.jitter = lambda: 1.0
        with stream:
            next(stream)
    assert horizon.paths() == ["/", "/", "/", "/", "/payments", "/payments"]
    # The connections neither give up at their first failure nor continue the
    # backoff of the root: the wait after that failure is the first one again.
    assert waits == [1, 2, 4, 1]


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


def test_stream_gives_up_on_the_root(horizon: FakeHorizon) -> None:
    horizon.on("/", json_response(503, problem("still_ingesting", 503)))
    with client_for(horizon) as client:
        stream = client.payments.stream(give_up_after=0)
        with pytest.raises(StreamError, match="still_ingesting") as caught:
            stream.__enter__()
    assert caught.value.cursor is None
    assert "/payments" not in horizon.paths()


def test_stream_close_before_use(horizon: FakeHorizon) -> None:
    horizon.on("/payments", captured(FIRST_STREAM))
    with client_for(horizon) as client:
        stream = client.payments.stream(cursor="1")
        stream.close()
        # A closed stream yields nothing, and closing it again does no harm.
        with pytest.raises(StopIteration):
            next(stream)
        stream.close()
    assert horizon.requests == []


def test_stream_closed_before_use_does_not_start_when_entered(
    horizon: FakeHorizon,
) -> None:
    horizon.on("/", captured("root.json"))
    horizon.on("/payments", captured(FIRST_STREAM))
    with client_for(horizon) as client:
        stream = client.payments.stream()
        stream.close()
        with stream as entered:
            assert entered is stream
            assert stream.cursor is None
            with pytest.raises(StopIteration):
                next(stream)
    assert horizon.requests == []


def test_stream_left_without_a_read_stays_closed(horizon: FakeHorizon) -> None:
    horizon.on("/", captured("root.json"))
    horizon.on("/payments", captured(FIRST_STREAM))
    with client_for(horizon) as client:
        with client.payments.stream() as stream:
            pass
        with pytest.raises(StopIteration):
            next(stream)
    assert horizon.paths() == ["/"]


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
