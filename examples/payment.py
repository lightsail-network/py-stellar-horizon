"""Build, sign and submit a payment on the test network.

The Python Stellar SDK builds and signs the transaction; this package reads the
account and submits it. The two accounts are new ones, funded by the test network's
friendbot.
"""

import httpx2
from stellar_sdk import Account, Asset, Keypair, Network, TransactionBuilder

from stellar_horizon import HorizonClient, OutcomeUnknownError, TransactionFailedError

sender = Keypair.random()
receiver = Keypair.random()
for keypair in (sender, receiver):
    httpx2.get(
        "https://friendbot.stellar.org", params={"addr": keypair.public_key}, timeout=60
    ).raise_for_status()

with HorizonClient("https://horizon-testnet.stellar.org") as client:
    record = client.accounts.get(sender.public_key)
    source = Account(sender.public_key, record.sequence)
    transaction = (
        TransactionBuilder(source, Network.TESTNET_NETWORK_PASSPHRASE, base_fee=100)
        .add_text_memo("Hello, Stellar!")
        .append_payment_op(receiver.public_key, Asset.native(), "350.1234567")
        .set_timeout(30)
        .build()
    )
    transaction.sign(sender)
    envelope = transaction.to_xdr()

    try:
        result = client.transactions.submit(envelope)
    except TransactionFailedError as error:
        print("it did not succeed:", error.result_codes)
    except OutcomeUnknownError as error:
        # Sending the same envelope again is safe: it is the same transaction.
        print("no answer; look up", error.hash or transaction.hash_hex(), "later")
    else:
        print("in ledger", result.ledger, "with fee", result.fee_charged)
