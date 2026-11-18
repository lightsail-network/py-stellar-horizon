# Generated from _async/_page.py by scripts/unasync.py. Do not edit.
"""A page of records, and the pages next to it."""

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Generic, TypeVar

from stellar_horizon._reading import follow, same
from stellar_horizon._requests import Request
from stellar_horizon.errors import PagingError

if TYPE_CHECKING:
    from ._session import Session

__all__ = ["Page"]

T = TypeVar("T")


class Page(Generic[T]):
    """One page of records.

    Iterating a page yields its records and fetches nothing. `next()` and `prev()`
    fetch the neighbouring pages, and `iter_records()` goes through the records of the
    pages that follow.

    Paging is not a snapshot: records that are written while the pages are read can be
    missed or seen twice, depending on the order.
    """

    def __init__(
        self,
        session: "Session",
        request: Request[T],
        records: list[T],
        links: Mapping[str, str],
    ) -> None:
        self._session = session
        self._request = request
        self.records: list[T] = records
        """The records of this page."""
        self.links: dict[str, str] = dict(links)
        """The href of each link of the page, by name: `self`, `next`, `prev`."""

    def __iter__(self) -> Iterator[T]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} of {len(self.records)} records>"

    def next(self) -> "Page[T]":
        """Fetch the next page.

        Raises:
            PagingError: The page has no link to a next page.
        """
        return self._session.page(follow(self._request, self.links, "next"))

    def prev(self) -> "Page[T]":
        """Fetch the previous page, by following the page's `prev` link as it is.

        This is what the other Stellar SDKs do, and it is kept on purpose, so that
        paging works the same in every language. Horizon's `prev` link turns the
        order around. The page it returns holds the
        records before this one, but in the opposite order, and its own `next()` goes
        on in that opposite direction, away from this page. To go back and forth, keep
        the pages you have fetched instead of calling `prev()`; see the guide.

        Raises:
            PagingError: The page has no link to a previous page.
        """
        return self._session.page(follow(self._request, self.links, "prev"))

    def iter_records(self, *, max_records: int | None = None) -> Iterator[T]:
        """Yield the records of this page and of the pages after it.

        It stops at an empty page, or after `max_records` records. Without a limit, a
        history endpoint can yield millions of records.

        Raises:
            PagingError: A page links to itself, so going on would never end.
        """
        if max_records is not None and max_records < 0:
            msg = "max_records must not be negative"
            raise ValueError(msg)
        page = self
        count = 0
        while True:
            for record in page.records:
                if max_records is not None and count >= max_records:
                    return
                yield record
                count += 1
            if not page.records or (max_records is not None and count >= max_records):
                return
            following = follow(page._request, page.links, "next")
            if same(following, page._request):
                msg = "the next page link repeats the request, so paging would not end"
                raise PagingError(msg)
            page = self._session.page(following)
