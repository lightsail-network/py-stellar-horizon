# Generated from _async/test_data_entries.py by scripts/unasync.py. Do not edit.
"""The data entries of an account, and the SEP-29 lookup."""

import pytest

from stellar_horizon import NotFoundError, ServerError
from tests._sync.clients import client_for
from tests.support import ACCOUNT_ID, FakeHorizon, captured, json_response, manifest

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
