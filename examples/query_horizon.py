"""Read an account, its latest transactions and its payments, page by page."""

from stellar_horizon import HorizonClient

# A busy account of an exchange. Put your own account here.
ACCOUNT = "GAPQZLGAUN6DOCHGVGTIHW3OCCCAZHGXIRLMKH76Z7764CINF4P7LBD4"

with HorizonClient("https://horizon.stellar.org") as client:
    account = client.accounts.get(ACCOUNT)
    print(f"sequence number: {account.sequence}")
    for balance in account.balances:
        # `:f` writes a balance of zero as 0.0000000; without it, Python writes 0E-7.
        print(f"holds {balance.balance:f} {balance.asset_code or balance.asset_type}")

    # Its latest transactions, the newest first.
    for transaction in client.transactions.list(account=ACCOUNT, order="desc", limit=5):
        print(f"{transaction.created_at:%Y-%m-%d %H:%M:%S} {transaction.hash}")

    # Its payments, the oldest first: 10 per request, and no more than 50 in all.
    first = client.payments.list(account=ACCOUNT, order="asc", limit=10)
    payments = list(first.iter_records(max_records=50))
    oldest = payments[0]
    print(f"{len(payments)} payments; the oldest is a {oldest.type}")
    print(f"from {oldest.created_at:%Y-%m-%d}, in {oldest.transaction_hash}")
