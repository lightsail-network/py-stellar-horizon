# API reference

The clients, pages, streams and errors are imported from `stellar_horizon`; the models
from `stellar_horizon.models`. The async classes have the same methods as the sync
ones, as coroutines: `AsyncHorizonClient` for `HorizonClient`, `AsyncPage` for `Page`,
`AsyncStream` for `Stream`, and the resources of an async client for those below.

## Clients

::: stellar_horizon.HorizonClient

::: stellar_horizon.AsyncHorizonClient
    options:
      members: false

## Pages and streams

::: stellar_horizon.Page

::: stellar_horizon.Stream

## Resources

The attributes of a client, such as `client.accounts`. Their classes are not imported
by name.

::: stellar_horizon._sync._resources
    options:
      show_root_heading: false
      show_root_toc_entry: false
      filters: []
      members:
        - Accounts
        - Transactions
        - Operations
        - Payments
        - Effects
        - Ledgers
        - Offers
        - Trades
        - TradeAggregations
        - OrderBooks
        - Paths
        - Assets
        - ClaimableBalances
        - LiquidityPools

## Models

Every model can be imported from `stellar_horizon.models`, and from the module of its
resource, such as `stellar_horizon.models.offer`.

Models can be pickled, but a pickle is not guaranteed to load in another release: the
module of a class, which a pickle records, and the fields of a model can change between
releases. To store models, keep `model_dump_json()` and validate it again.

### Common values

::: stellar_horizon.models.common
    options:
      show_root_heading: false
      show_root_toc_entry: false

::: stellar_horizon.models.base
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Root

::: stellar_horizon.models.root
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Accounts

::: stellar_horizon.models.account
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Ledgers

::: stellar_horizon.models.ledger
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Fee statistics

::: stellar_horizon.models.fee_stats
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Transactions

::: stellar_horizon.models.transaction
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Operations

::: stellar_horizon.models.operations
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Effects

::: stellar_horizon.models.effects
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Offers

::: stellar_horizon.models.offer
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Trades

::: stellar_horizon.models.trade
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Trade aggregations

::: stellar_horizon.models.trade_aggregation
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Order books

::: stellar_horizon.models.order_book
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Paths

::: stellar_horizon.models.path
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Assets

::: stellar_horizon.models.asset_stat
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Claimable balances

::: stellar_horizon.models.claimable_balance
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Liquidity pools

::: stellar_horizon.models.liquidity_pool
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Problems

::: stellar_horizon.models.problem
    options:
      show_root_heading: false
      show_root_toc_entry: false

## Errors

::: stellar_horizon.errors
    options:
      show_root_heading: false
      show_root_toc_entry: false
      members:
        - HorizonError
        - TransportError
        - ResponseError
        - BadRequestError
        - NotFoundError
        - BeforeHistoryError
        - RateLimitError
        - TransactionFailedError
        - ServerError
        - OutcomeUnknownError
        - InvalidResponseError
        - StreamError
        - PagingError

## Constants

::: stellar_horizon.HORIZON_VERSION
