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
print(f"sender:   {sender.public_key}")
print(f"receiver: {receiver.public_key}")

with HorizonClient("https://horizon-testnet.stellar.org") as client:
    # A transaction carries the next sequence number of its source account.
    account = client.accounts.get(sender.public_key)
    source = Account(sender.public_key, account.sequence)
    transaction = (
        TransactionBuilder(source, Network.TESTNET_NETWORK_PASSPHRASE, base_fee=100)
        .add_text_memo("Hello, Stellar!")
        .append_payment_op(receiver.public_key, Asset.native(), "350.1234567")
        .set_timeout(30)
        .build()
    )
    transaction.sign(sender)

    try:
        result = client.transactions.submit(transaction.to_xdr())
    except TransactionFailedError as error:
        # stellar-core refused it, or it is in a ledger and failed. The codes say why.
        codes = error.result_codes
        print(f"failed: {codes.transaction if codes else error}")
        if codes and codes.operations:
            print(f"operations: {', '.join(codes.operations)}")
    except OutcomeUnknownError as error:
        # Sending the same envelope again is safe: it is the same transaction.
        print(f"no answer; look up {error.hash or transaction.hash_hex()} later")
    else:
        print(f"succeeded: {result.hash}")
        print(f"in ledger {result.ledger}, for a fee of {result.fee_charged} stroops")
        balance = client.accounts.get(receiver.public_key).balances[0]
        print(f"the receiver now holds {balance.balance} XLM")
