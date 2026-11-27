# pyright: reportPrivateUsage=false
"""Streams: where they start, and what follows when a connection ends."""

import json
import logging
from collections.abc import AsyncIterator

import httpx2
import pytest

from stellar_horizon import (
    AsyncStream,
    BadRequestError,
    InvalidResponseError,
    NotFoundError,
    ResponseError,
    StreamError,
)
from stellar_horizon import _requests as rq
from stellar_horizon.models import Operation
from tests._async.clients import client_for
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

pytestmark = pytest.mark.anyio


async def test_stream_starts_now_and_continues_from_the_last_record(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    horizon.on(
        "/payments",
        captured(FIRST_STREAM),
        captured("streams/quiet.sse"),
        captured(SECOND_STREAM),
    )
    first_ids, second_ids = event_ids(FIRST_STREAM), event_ids(SECOND_STREAM)
    async with (
        client_for(horizon) as client,
        client.payments.stream() as stream,
    ):
        assert stream.cursor == NOW
        ids = [(await anext(stream)).id for _ in range(len(first_ids) + 1)]
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


async def test_stream_from_the_oldest_history(horizon: FakeHorizon) -> None:
    horizon.on("/payments", captured(FIRST_STREAM))
    async with client_for(horizon) as client:
        stream = client.payments.stream(cursor=None)
        assert stream.cursor is None
        record = await anext(stream)
        await stream.aclose()
    assert record.id == event_ids(FIRST_STREAM)[0]
    assert horizon.paths() == ["/payments"]
    assert "cursor" not in horizon.requests[0].url.params


async def test_stream_from_an_empty_cursor(horizon: FakeHorizon) -> None:
    # Horizon reads an empty cursor as none, and starts at the oldest history it
    # keeps. The client sends it as it is, and does not ask the root for `now`.
    horizon.on("/payments", captured(FIRST_STREAM))
    async with (
        client_for(horizon) as client,
        client.payments.stream(cursor="") as stream,
    ):
        record = await anext(stream)
    assert record.id == event_ids(FIRST_STREAM)[0]
    assert horizon.paths() == ["/payments"]
    assert horizon.requests[0].url.params["cursor"] == ""


async def test_stream_from_a_cursor(horizon: FakeHorizon) -> None:
    cursor = event_ids(FIRST_STREAM)[-1]
    horizon.on(SMALL_PAYMENTS, captured(SECOND_STREAM))
    async with (
        client_for(horizon) as client,
        client.payments.stream(account=SMALL_ACCOUNT, cursor=cursor) as stream,
    ):
        assert stream.cursor == cursor
        await anext(stream)
    # A cursor is sent as it is: the client does not ask the server anything first.
    assert horizon.paths() == [SMALL_PAYMENTS]
    assert horizon.requests[0].url.params["cursor"] == cursor


async def test_stream_raises_what_does_not_pass(horizon: FakeHorizon) -> None:
    horizon.on("/payments", captured("errors/bad_request_cursor.json"))
    async with client_for(horizon) as client:
        with pytest.raises(BadRequestError):
            async with client.payments.stream(cursor="-1") as stream:
                await anext(stream)
    assert horizon.paths() == ["/payments"]


async def test_stream_retries_what_passes(
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
    async with client_for(horizon) as client, client.payments.stream() as stream:
        record = await anext(stream)
    assert record.id == event_ids(FIRST_STREAM)[0]
    assert len(waits) == 5
    assert waits[1] >= 7
    assert len(caplog.records) == 5
    # `now` is resolved once, when the stream is entered.
    assert horizon.paths().count("/") == 1


async def test_stream_ends_at_a_redirect(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    # A redirect stays, so waiting for it to pass would only hide it. The same
    # holds for the root, which a stream that starts now reads first.
    horizon.on("/payments", redirect("https://horizon.test/payments"))
    async with client_for(horizon) as client:
        with pytest.raises(ResponseError, match="redirect"):
            async with client.payments.stream(cursor="1") as stream:
                await anext(stream)
        horizon.on("/", redirect("https://horizon.test/"))
        with pytest.raises(ResponseError, match="redirect"):
            async with client.payments.stream() as stream:
                await anext(stream)
    assert waits == []
    assert horizon.paths() == ["/payments", "/"]


async def test_stream_ends_at_a_redirect_when_the_http_client_follows_them(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    horizon.on("/payments", redirect("https://elsewhere.test/moved", 307))
    async with client_for(horizon, follow_redirects=True) as client:
        with pytest.raises(ResponseError, match="redirect"):
            async with client.payments.stream(cursor="1") as stream:
                await anext(stream)
    assert waits == []
    assert horizon.paths() == ["/payments"]


async def test_stream_gives_up(horizon: FakeHorizon) -> None:
    # Synthetic: the server cannot be reached.
    horizon.on("/payments", httpx2.ConnectError("refused"))
    async with client_for(horizon) as client:
        with pytest.raises(StreamError, match="no working connection") as caught:
            async with client.payments.stream(give_up_after=0) as stream:
                await anext(stream)
    assert caught.value.cursor == NOW
    assert isinstance(caught.value.__cause__, httpx2.ConnectError)


async def test_stream_ends_at_an_error_that_stays(horizon: FakeHorizon) -> None:
    # Synthetic: an error event in the middle of a stream.
    horizon.on(
        "/payments",
        sse(OPEN, "event: error\ndata: problem: not_found. full details: x"),
    )
    async with client_for(horizon) as client:
        with pytest.raises(StreamError, match="not_found"):
            async with client.payments.stream() as stream:
                await anext(stream)


async def test_stream_record_that_cannot_be_read(horizon: FakeHorizon) -> None:
    # Synthetic: records that Horizon does not send.
    horizon.on(
        "/payments", sse(OPEN, 'id: 5\ndata: {"id": "5"}'), sse(OPEN, "data: nope")
    )
    async with client_for(horizon) as client:
        with pytest.raises(InvalidResponseError, match="cannot be read"):
            async with client.payments.stream() as stream:
                await anext(stream)
        stream = client.payments.stream()
        with pytest.raises(InvalidResponseError, match="not JSON"):
            async with stream:
                await anext(stream)
        # The record that cannot be read does not move the cursor.
        assert stream.cursor == NOW


async def test_stream_waits_for_the_root_at_the_start(
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
    async with client_for(horizon, max_retries=5) as client:
        stream = client.payments.stream()
        async with stream:
            assert stream.cursor == NOW
            await anext(stream)
    assert horizon.paths()[:4] == ["/", "/", "/", "/payments"]
    assert horizon.requests[3].url.params["cursor"] == NOW
    # The stream's rule, not max_retries: the first wait is no shorter than 4 seconds.
    assert waits[0] >= 4
    assert len(waits) >= 2


async def test_stream_start_that_fails_tries_again_when_read_again(
    horizon: FakeHorizon,
) -> None:
    # Synthetic: a root that cannot be read the first time.
    horizon.on(
        "/", json_response(404, problem("not_found", 404)), captured("root.json")
    )
    horizon.on("/payments", captured(FIRST_STREAM))
    async with client_for(horizon) as client:
        stream = client.payments.stream()
        with pytest.raises(NotFoundError):
            await anext(stream)
        # Read again, the stream resolves `now` instead of starting without a cursor.
        await anext(stream)
        await stream.aclose()
    assert horizon.paths()[:3] == ["/", "/", "/payments"]
    assert horizon.requests[2].url.params["cursor"] == NOW


async def test_stream_gives_up_on_the_root(horizon: FakeHorizon) -> None:
    horizon.on("/", json_response(503, problem("still_ingesting", 503)))
    async with client_for(horizon) as client:
        stream = client.payments.stream(give_up_after=0)
        with pytest.raises(StreamError, match="still_ingesting") as caught:
            await stream.__aenter__()
    assert caught.value.cursor is None
    assert "/payments" not in horizon.paths()


async def test_stream_close_before_use(horizon: FakeHorizon) -> None:
    async with client_for(horizon) as client:
        stream = client.payments.stream()
        await stream.aclose()
    assert horizon.requests == []


async def test_stream_survives_a_reset_after_delivering(horizon: FakeHorizon) -> None:
    # Synthetic: the connection breaks after the first record of a real stream.
    events = captured(FIRST_STREAM).content.split(b"\n\n")

    async def body() -> AsyncIterator[bytes]:
        yield b"\n\n".join(events[:2]) + b"\n\n"
        raise httpx2.ReadError("reset")

    reset = httpx2.Response(
        200, content=body(), headers={"content-type": "text/event-stream"}
    )
    unknown_event = sse(OPEN, "event: other\ndata: x")
    horizon.on("/payments", reset, unknown_event, captured(SECOND_STREAM))
    async with client_for(horizon) as client, client.payments.stream() as stream:
        first, second = (await anext(stream)).id, (await anext(stream)).id
    assert [first, second] == [event_ids(FIRST_STREAM)[0], event_ids(SECOND_STREAM)[0]]
    streams = [r for r in horizon.requests if r.url.path != "/"]
    assert streams[1].url.params["cursor"] == first


async def test_stream_that_is_silent_until_the_timeout_is_replaced_at_once(
    horizon: FakeHorizon, waits: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    # Synthetic: a quiet connection, which the client ends by its read timeout. It is
    # not a failure: nothing is logged, and the next connection follows without a wait.
    async def body() -> AsyncIterator[bytes]:
        yield (OPEN + "\n\n").encode()
        raise httpx2.ReadTimeout("silent")

    quiet = httpx2.Response(
        200, content=body(), headers={"content-type": "text/event-stream"}
    )
    horizon.on("/payments", quiet, captured(FIRST_STREAM))
    caplog.set_level(logging.WARNING, logger="stellar_horizon")
    async with (
        client_for(horizon) as client,
        client.payments.stream(cursor="1") as stream,
    ):
        record = await anext(stream)
    assert record.id == event_ids(FIRST_STREAM)[0]
    assert waits == [0]
    assert caplog.records == []
    assert [request.url.params["cursor"] for request in horizon.requests] == ["1", "1"]


async def test_stream_that_ends_early_is_a_failure(
    horizon: FakeHorizon, waits: list[float]
) -> None:
    # Synthetic: a connection that opens and ends without `close`.
    horizon.on("/payments", sse(OPEN), captured(FIRST_STREAM))
    async with client_for(horizon) as client:
        stream = client.payments.stream(cursor=None)
        records = [record.id async for record in _first(stream)]
    assert records == [event_ids(FIRST_STREAM)[0]]
    assert len(waits) == 1
    assert 0.5 <= waits[0] <= 1.0  # the first wait after a failure, with jitter


async def _first(stream: AsyncStream[Operation]) -> AsyncIterator[Operation]:
    async with stream:
        async for record in stream:
            yield record
            return


async def test_object_stream_drops_repeats(horizon: FakeHorizon) -> None:
    # Synthetic events around a real account: Horizon sends an account once.
    same = f"data: {json.dumps(ACCOUNT)}"
    changed = f"data: {json.dumps(ACCOUNT | {'sequence': '1'})}"
    horizon.on(f"/accounts/{ACCOUNT_ID}", sse(OPEN, same, same, changed))
    async with client_for(horizon) as client:
        stream = client._session.stream(
            rq.account(ACCOUNT_ID), kind="object", cursor=None, give_up_after=None
        )
        async with stream:
            assert (await anext(stream)).sequence == int(ACCOUNT["sequence"])
            assert (await anext(stream)).sequence == 1
            assert stream.cursor is None
    assert "cursor" not in horizon.requests[0].url.params
