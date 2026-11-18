# Generated from _async/test_pages.py by scripts/unasync.py. Do not edit.
"""Pages: their links, and going through their records."""

import pytest

from stellar_horizon import InvalidResponseError, Page, PagingError
from tests._sync.clients import client_for
from tests.support import (
    BASE,
    SMALL_ACCOUNT,
    SMALL_PAYMENTS,
    FakeHorizon,
    captured,
    json_response,
    load,
    records,
)


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
    assert ids == [record["id"] for name in names for record in records(name)]
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
