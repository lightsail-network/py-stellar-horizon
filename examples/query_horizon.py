"""Read the transactions and payments of an account, and go through pages."""

from stellar_horizon import HorizonClient

ACCOUNT = "GB6NVEN5HSUBKMYCE5ZOWSK5K23TBWRUQLZY3KNMXUZ3AQ2ESC4MY4AQ"

with HorizonClient("https://horizon.stellar.org") as client:
    # The latest transactions of an account.
    for transaction in client.transactions.list(account=ACCOUNT, order="desc", limit=5):
        print(transaction.hash, transaction.created_at, transaction.successful)

    # Every payment of the account, oldest first, 10 per request, at most 50.
    first = client.payments.list(account=ACCOUNT, order="asc", limit=10)
    payments = list(first.iter_records(max_records=50))
    print(f"{len(payments)} payments; the first is a {payments[0].type}")
