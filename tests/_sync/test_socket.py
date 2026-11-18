# Generated from _async/test_socket.py by scripts/unasync.py. Do not edit.
# pyright: reportPrivateUsage=false
"""Streams over a real socket, against a server on localhost.

The events are captured payments; when and how the server sends them is scripted.
"""

import threading
from collections.abc import Iterator

import httpx2
import pytest

from stellar_horizon import HorizonClient
from stellar_horizon._sync import _stream
from tests.local_server import Connection, LocalHorizon
from tests.support import CLOSE, OPEN, stream_records

RECORDS = stream_records("streams/payments_1.sse")
IDS = [record.split("\n", 1)[0].removeprefix("id: ") for record in RECORDS]
START = "1"


@pytest.fixture(autouse=True)
def no_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    def sleep(_: float) -> None:
        pass

    monkeypatch.setattr(_stream, "_sleep", sleep)


@pytest.fixture
def local() -> Iterator[LocalHorizon]:
    server = LocalHorizon(lambda connection: connection.send(OPEN, CLOSE))
    with server:
        yield server
    assert server.failures == []


def cursors(local: LocalHorizon) -> list[str]:
    return [httpx2.URL(path).params["cursor"] for path in local.requests]


def test_records_arrive_as_they_are_sent(local: LocalHorizon) -> None:
    sent_first = threading.Event()
    go_on = threading.Event()

    def answer(connection: Connection) -> None:
        connection.send(OPEN, RECORDS[0])
        sent_first.set()
        connection.wait(go_on)
        connection.send(RECORDS[1], CLOSE)

    local.answers = [answer]
    with (
        HorizonClient(local.url) as client,
        client.payments.stream(cursor=START) as stream,
    ):
        # The first record is read while the server still holds the second back.
        first = next(stream)
        assert sent_first.is_set()
        go_on.set()
        second = next(stream)
    assert [first.id, second.id] == IDS[:2]


def test_a_body_that_ends_without_close(local: LocalHorizon) -> None:
    def ends(connection: Connection) -> None:
        connection.send(OPEN, RECORDS[0], RECORDS[1])
        connection.end()

    def closes(connection: Connection) -> None:
        connection.send(OPEN, RECORDS[2], CLOSE)

    local.answers = [ends, closes]
    with (
        HorizonClient(local.url) as client,
        client.payments.stream(cursor=START) as stream,
    ):
        ids = [(next(stream)).id for _ in range(3)]
    assert ids == IDS
    assert cursors(local)[:2] == [START, IDS[1]]


def test_a_reset_in_the_middle_of_an_event(local: LocalHorizon) -> None:
    read_first = threading.Event()

    def resets(connection: Connection) -> None:
        connection.send(OPEN, RECORDS[0])
        # A reset drops what the client has not read yet, so wait until it has.
        connection.wait(read_first)
        connection.send_raw(RECORDS[1][:50])
        connection.reset()

    def resumes(connection: Connection) -> None:
        connection.send(OPEN, RECORDS[1], CLOSE)

    local.answers = [resets, resumes]
    with (
        HorizonClient(local.url) as client,
        client.payments.stream(cursor=START) as stream,
    ):
        first = next(stream)
        read_first.set()
        second = next(stream)
    assert [first.id, second.id] == IDS[:2]
    assert cursors(local)[:2] == [START, IDS[0]]


def test_a_silent_connection_is_given_up(local: LocalHorizon) -> None:
    released: list[bool] = []

    def silent(connection: Connection) -> None:
        connection.send(OPEN)
        released.append(connection.wait_until_released())

    def answers(connection: Connection) -> None:
        connection.send(OPEN, RECORDS[0], CLOSE)

    local.answers = [silent, answers]
    with HorizonClient(local.url) as client:
        client._session.stream_timeout = httpx2.Timeout(5.0, read=0.2)
        with client.payments.stream(cursor=START) as stream:
            record = next(stream)
    assert record.id == IDS[0]
    assert released == [True]


def test_close_releases_the_connection(local: LocalHorizon) -> None:
    def holds(connection: Connection) -> None:
        connection.send(OPEN, RECORDS[0])
        connection.wait_until_released()

    local.answers = [holds]
    with HorizonClient(local.url) as client:
        stream = client.payments.stream(cursor=START)
        next(stream)
        stream.close()
        assert local.released.wait(5)
        with pytest.raises(StopIteration):
            next(stream)
