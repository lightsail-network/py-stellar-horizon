"""Checked by mypy and pyright, never run: the types that callers see.

`assert_type` fails the type check if a method stops returning what it promises.
"""

from decimal import Decimal
from typing import assert_type

from stellar_horizon import (
    AsyncHorizonClient,
    AsyncPage,
    AsyncStream,
    HorizonClient,
    Page,
    Stream,
)
from stellar_horizon.models import (
    Account,
    Operation,
    PaymentOperation,
    Root,
    Transaction,
    UnknownOperation,
)


def sync_client(client: HorizonClient) -> None:
    assert_type(client.root(), Root)
    assert_type(client.accounts.get("G"), Account)
    accounts = client.accounts.list(signer="G")
    assert_type(accounts, Page[Account])
    assert_type(accounts.records, list[Account])
    assert_type(accounts.next(), Page[Account])
    for account in accounts:
        assert_type(account, Account)
    assert_type(client.transactions.get("ab"), Transaction)
    assert_type(client.transactions.list(), Page[Transaction])
    assert_type(client.transactions.submit("AAAA"), Transaction)
    assert_type(client.payments.list(), Page[Operation])
    with client.payments.stream() as stream:
        assert_type(stream, Stream[Operation])
        assert_type(stream.cursor, str | None)
        for payment in stream:
            assert_type(payment, Operation)


async def async_client(client: AsyncHorizonClient) -> None:
    assert_type(await client.root(), Root)
    assert_type(await client.accounts.get("G"), Account)
    accounts = await client.accounts.list(signer="G")
    assert_type(accounts, AsyncPage[Account])
    assert_type(await accounts.next(), AsyncPage[Account])
    async for account in accounts.iter_records():
        assert_type(account, Account)
    assert_type(await client.transactions.submit("AAAA"), Transaction)
    async with client.payments.stream() as stream:
        assert_type(stream, AsyncStream[Operation])
        async for payment in stream:
            assert_type(payment, Operation)


def narrowing(operation: Operation) -> None:
    match operation:
        case PaymentOperation():
            assert_type(operation.amount, Decimal)
        case UnknownOperation():
            assert_type(operation.type_i, int)
        case _:
            pass
