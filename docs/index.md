# py-stellar-horizon

A typed Python client for [Horizon](https://developers.stellar.org/docs/data/apis/horizon),
the REST API of the [Stellar](https://stellar.org) network. It reads from Horizon and
submits transactions; to build and sign them, use the
[Python Stellar SDK](https://github.com/StellarCN/py-stellar-base).

!!! warning

    Releases before 1.0 may still change the API.

!!! note

    Horizon is nearing its end of life and gets no new features. For new projects, look
    at [Stellar RPC](https://developers.stellar.org/docs/data/apis/rpc) first. This
    package is for applications that need what only Horizon offers.

## Install

```shell
pip install stellar-horizon
```

## Example

```py
from stellar_horizon import HorizonClient

ACCOUNT = "GALAXYVOIDAOPZTDLHILAJQKCVVFMD4IKLXLSZV5YHO7VY74IWZILUTO"

with HorizonClient("https://horizon.stellar.org") as client:
    account = client.accounts.get(ACCOUNT)
    for balance in account.balances:
        print(f"{balance.balance:f} {balance.asset_code or balance.asset_type}")

    for payment in client.payments.list(account=account.account_id, order="desc"):
        print(f"{payment.created_at}: {payment.type}")

    with client.ledgers.stream() as stream:
        for ledger in stream:
            print(f"ledger {ledger.sequence} closed at {ledger.closed_at}")
```

The [guide](guide.md) covers paging, streaming, submitting transactions and errors,
and `AsyncHorizonClient`, the same client for `asyncio`.
