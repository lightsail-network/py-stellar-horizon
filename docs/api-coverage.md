# API coverage

<!-- Written by scripts/api_coverage.py from tests/routes.json. Do not edit. -->

Every route of Horizon 30.0.1, as its
[router](https://github.com/stellar/stellar-horizon/blob/01ba44a988b3ebc2d68d3cb6747fa2c2733773cd/internal/httpx/router.go) defines them, and the method that calls it. A test checks
that each listed method requests its route, and that every route is either called or
left out for the reason given below.

Anything that is not listed can still be reached with `client.request()`.

| Route | Returns | Method | Stream |
|---|---|---|---|
| `GET /health` | one resource | not offered | — |
| `GET /` | one resource | `client.root()` | — |
| `GET /fee_stats` | one resource | `client.fee_stats()` | — |
| `GET /accounts` | a page | `client.accounts.list(signer=…)` | — |
| `GET /accounts/{account_id}` | one resource | `client.accounts.get(account_id)` | not offered |
| `GET /accounts/{account_id}/data/{key}` | one resource | `client.accounts.data(account_id, key)` | `client.accounts.stream_data(account_id, key)` |
| `GET /accounts/{account_id}/offers` | a page | not offered | `client.offers.stream(seller=…)` |
| `GET /accounts/{account_id}/effects` | a page | `client.effects.list(account=…)` | `client.effects.stream(account=…)` |
| `GET /accounts/{account_id}/operations` | a page | `client.operations.list(account=…)` | `client.operations.stream(account=…)` |
| `GET /accounts/{account_id}/payments` | a page | `client.payments.list(account=…)` | `client.payments.stream(account=…)` |
| `GET /accounts/{account_id}/trades` | a page | `client.trades.list(account=…)` | `client.trades.stream(account=…)` |
| `GET /accounts/{account_id}/transactions` | a page | `client.transactions.list(account=…)` | `client.transactions.stream(account=…)` |
| `GET /claimable_balances` | a page | `client.claimable_balances.list()` | — |
| `GET /claimable_balances/{id}` | one resource | `client.claimable_balances.get(balance_id)` | — |
| `GET /claimable_balances/{claimable_balance_id}/operations` | a page | `client.operations.list(claimable_balance=…)` | `client.operations.stream(claimable_balance=…)` |
| `GET /claimable_balances/{claimable_balance_id}/transactions` | a page | `client.transactions.list(claimable_balance=…)` | `client.transactions.stream(claimable_balance=…)` |
| `GET /liquidity_pools` | a page | `client.liquidity_pools.list()` | — |
| `GET /liquidity_pools/{liquidity_pool_id}` | one resource | `client.liquidity_pools.get(pool_id)` | — |
| `GET /liquidity_pools/{liquidity_pool_id}/operations` | a page | `client.operations.list(liquidity_pool=…)` | `client.operations.stream(liquidity_pool=…)` |
| `GET /liquidity_pools/{liquidity_pool_id}/transactions` | a page | `client.transactions.list(liquidity_pool=…)` | `client.transactions.stream(liquidity_pool=…)` |
| `GET /liquidity_pools/{liquidity_pool_id}/effects` | a page | `client.effects.list(liquidity_pool=…)` | `client.effects.stream(liquidity_pool=…)` |
| `GET /liquidity_pools/{liquidity_pool_id}/trades` | a page | `client.trades.list(liquidity_pool=…)` | `client.trades.stream(liquidity_pool=…)` |
| `GET /offers` | a page | `client.offers.list()` | — |
| `GET /offers/{offer_id}` | one resource | `client.offers.get(offer_id)` | — |
| `GET /offers/{offer_id}/trades` | a page | `client.trades.list(offer=…)` | `client.trades.stream(offer=…)` |
| `GET /assets` | a page | `client.assets.list()` | — |
| `GET /paths` | a list | not offered | — |
| `GET /paths/strict-receive` | a list | `client.paths.strict_receive(destination_asset=…, destination_amount=…, source_account=…)` | — |
| `GET /paths/strict-send` | a list | `client.paths.strict_send(source_asset=…, source_amount=…, destination_account=…)` | — |
| `GET /order_book` | one resource | `client.order_book.get(selling, buying)` | `client.order_book.stream(selling, buying)` |
| `GET /ledgers` | a page | `client.ledgers.list()` | `client.ledgers.stream()` |
| `GET /ledgers/{ledger_id}` | one resource | `client.ledgers.get(sequence)` | — |
| `GET /ledgers/{ledger_id}/transactions` | a page | `client.transactions.list(ledger=…)` | `client.transactions.stream(ledger=…)` |
| `GET /ledgers/{ledger_id}/effects` | a page | `client.effects.list(ledger=…)` | `client.effects.stream(ledger=…)` |
| `GET /ledgers/{ledger_id}/operations` | a page | `client.operations.list(ledger=…)` | `client.operations.stream(ledger=…)` |
| `GET /ledgers/{ledger_id}/payments` | a page | `client.payments.list(ledger=…)` | `client.payments.stream(ledger=…)` |
| `GET /transactions` | a page | `client.transactions.list()` | `client.transactions.stream()` |
| `GET /transactions/{tx_id}` | one resource | `client.transactions.get(transaction_hash)` | — |
| `GET /transactions/{tx_id}/effects` | a page | `client.effects.list(transaction=…)` | `client.effects.stream(transaction=…)` |
| `GET /transactions/{tx_id}/operations` | a page | `client.operations.list(transaction=…)` | `client.operations.stream(transaction=…)` |
| `GET /transactions/{tx_id}/payments` | a page | `client.payments.list(transaction=…)` | `client.payments.stream(transaction=…)` |
| `GET /operations` | a page | `client.operations.list()` | `client.operations.stream()` |
| `GET /operations/{id}` | one resource | `client.operations.get(operation_id)` | — |
| `GET /operations/{op_id}/effects` | a page | `client.effects.list(operation=…)` | `client.effects.stream(operation=…)` |
| `GET /payments` | a page | `client.payments.list()` | `client.payments.stream()` |
| `GET /effects` | a page | `client.effects.list()` | `client.effects.stream()` |
| `GET /trades` | a page | `client.trades.list()` | `client.trades.stream()` |
| `GET /trade_aggregations` | a page | `client.trade_aggregations.list(base_asset, counter_asset, resolution)` | — |
| `POST /transactions` | one resource | `client.transactions.submit(transaction)` | — |
| `POST /transactions_async` | one resource | `client.transactions.enqueue(transaction)` | — |
| `GET /friendbot` | a redirect | not offered | — |

## Left out

- `GET /health`: It tells a load balancer whether the server is up, and is not part of the API.
- The stream of `GET /accounts/{account_id}`: Horizon v30 sends the account once per connection and never again, because it compares only the account ID to tell whether the account changed.
- `GET /accounts/{account_id}/data/{key}` as raw bytes, `application/octet-stream`: `data()` returns the same bytes, decoded from the JSON body.
- `GET /accounts/{account_id}/offers`: As a page, it holds the same offers as `/offers?seller=`, which `client.offers.list(seller=…)` calls. Its stream is offered.
- `GET /paths`: An older name of `/paths/strict-receive`, which `paths.strict_receive()` calls.
- `GET /friendbot`: A redirect, for `GET` and `POST`, to the friendbot of a test network, only on servers configured with one. Call friendbot itself.
