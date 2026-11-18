"""Refuse to send a payment that SEP-29 says needs a memo, before submitting it.

SEP-29 lets an account, such as an exchange's, say that payments to it must carry a
memo, by setting the data entry `config.memo_required` to `1`. This package offers the
lookup, `client.accounts.requires_memo()`; the check reads the transaction, which the
Python Stellar SDK builds.

The script makes an account on the test network that requires a memo. It shows the
check stopping a payment to it that has none, and letting one with a memo through.
"""

from collections.abc import Callable

import httpx2
from stellar_sdk import (
    Account,
    AccountMerge,
    Asset,
    FeeBumpTransactionEnvelope,
    Keypair,
    Network,
    NoneMemo,
    PathPaymentStrictReceive,
    PathPaymentStrictSend,
    Payment,
    TransactionBuilder,
    TransactionEnvelope,
)

from stellar_horizon import HorizonClient

TESTNET = "https://horizon-testnet.stellar.org"


def check_memo_required(
    client: HorizonClient, envelope: TransactionEnvelope | FeeBumpTransactionEnvelope
) -> None:
    """Raise `ValueError` if a destination of the transaction requires a memo."""
    if isinstance(envelope, FeeBumpTransactionEnvelope):
        envelope = envelope.transaction.inner_transaction_envelope
    transaction = envelope.transaction
    if not isinstance(transaction.memo, NoneMemo):
        return
    checked: set[str] = set()
    for index, operation in enumerate(transaction.operations):
        if not isinstance(
            operation,
            Payment | PathPaymentStrictReceive | PathPaymentStrictSend | AccountMerge,
        ):
            continue
        destination = operation.destination
        # A muxed destination already says who the payment is for.
        if destination.account_muxed_id is not None:
            continue
        if destination.account_id in checked:
            continue
        checked.add(destination.account_id)
        if client.accounts.requires_memo(destination.account_id):
            msg = f"operation {index}: {destination.account_id} requires a memo"
            raise ValueError(msg)


def fund(keypair: Keypair) -> None:
    """Create an account on the test network with friendbot."""
    httpx2.get(
        "https://friendbot.stellar.org", params={"addr": keypair.public_key}, timeout=60
    ).raise_for_status()


def signed(
    client: HorizonClient,
    source: Keypair,
    add: Callable[[TransactionBuilder], TransactionBuilder],
) -> TransactionEnvelope:
    """A transaction of `source` with the operations that `add` appends, signed."""
    record = client.accounts.get(source.public_key)
    builder = TransactionBuilder(
        Account(source.public_key, record.sequence),
        Network.TESTNET_NETWORK_PASSPHRASE,
        base_fee=100,
    )
    envelope = add(builder).set_timeout(60).build()
    envelope.sign(source)
    return envelope


def pay(builder: TransactionBuilder) -> TransactionBuilder:
    """Add a payment of one lumen to the exchange."""
    return builder.append_payment_op(exchange.public_key, Asset.native(), "1")


def send(client: HorizonClient, payment: TransactionEnvelope) -> None:
    """Send a payment, unless a destination of it requires a memo that it lacks."""
    try:
        check_memo_required(client, payment)
    except ValueError as error:
        print(f"not sent: {error}")
        return
    result = client.transactions.submit(payment.to_xdr())
    print(f"sent: {result.hash}")


exchange, customer = Keypair.random(), Keypair.random()
fund(exchange)
fund(customer)

with HorizonClient(TESTNET) as client:
    # The exchange asks for a memo on every payment to it.
    asks = signed(
        client, exchange, lambda b: b.append_manage_data_op("config.memo_required", "1")
    )
    asked = client.transactions.submit(asks.to_xdr())
    print(f"the exchange asks for a memo, in {asked.hash}")
    print(f"requires a memo: {client.accounts.requires_memo(exchange.public_key)}")

    # The same payment twice: without a memo, which the check stops, and with one.
    send(client, signed(client, customer, pay))
    send(client, signed(client, customer, lambda b: pay(b).add_text_memo("order 42")))
