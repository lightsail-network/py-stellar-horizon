# Guide

## Creating a client

`HorizonClient` talks to one Horizon server. Use it as a context manager, or call
`close()` when you are done, so that its connections are released:

```python
from stellar_horizon import HorizonClient

with HorizonClient("https://horizon-testnet.stellar.org") as client:
    pass  # client.accounts, client.transactions, ...
```

Create the client once and reuse it: it keeps connections to the server open between
requests.

`AsyncHorizonClient` has the same methods for `asyncio`; see [Async](#async).

### Settings

```python
import httpx2

from stellar_horizon import HorizonClient

client = HorizonClient(
    "https://horizon-testnet.stellar.org",
    timeout=30,  # seconds, or an httpx2.Timeout
    max_retries=3,  # try a failed GET again up to 3 times; see below
    app_name="my-wallet",  # sent as X-App-Name, for the server's logs
    app_version="1.4.0",  # sent as X-App-Version
    http_client=httpx2.Client(proxy="http://localhost:8080"),
)
client.close()
```

- **`timeout`** is 60 seconds by default. Horizon answers a `GET` within 55 seconds and
  holds a submission for up to 30, so the default only ends a request when the server
  or the network has stopped answering. When you pass `http_client` and no `timeout`,
  the timeout of your client is used, unless it is httpx2's default of 5 seconds, which
  is too short for a submission.
- **`max_retries`** is 2 by default: a single `GET` is tried again up to twice after a
  transport error, or after a 429, 502, 503 or 504, and `max_retries=0` turns that off.
  The waits start at half a second and double, are never shorter than the server's
  `Retry-After`, and add up to at most 60 seconds per call. A 404, another 4xx, and a
  response that cannot be read are raised at once. A submission is never sent twice, whatever `max_retries` is, and streams have
  their own rule.
- **`http_client`** is an `httpx2.Client` of your own, for proxies, TLS settings,
  connection limits or a custom transport. The client sends its requests through it and
  leaves it open on `close()`: it is yours to close.
- **`headers`** are sent with every request; see [Authentication](#authentication).

### Certificates

httpx2 checks the server's certificate against the certificate store of the operating
system. A minimal container image may have no certificates: install the CA
certificates package of the distribution, or point `SSL_CERT_FILE` at a bundle.

## Reading

Each kind of resource has an attribute of the client: `accounts`, `transactions`,
`operations`, `payments`, `effects`, `ledgers`, `offers`, `trades`,
`trade_aggregations`, `order_book`, `paths`, `assets`, `claimable_balances` and
`liquidity_pools`. The [API coverage](api-coverage.md) page lists which method calls
which route.

What the methods return are the models in `stellar_horizon.models`; import them from
there when you name them, in a type annotation or a `match`:

```python
from stellar_horizon import HorizonClient, NotFoundError
from stellar_horizon.models import Account, PaymentOperation
```

`get()` fetches one resource, and `list()` one page of them:

```py
account = client.accounts.get("G...")
print(f"sequence number {account.sequence}, {len(account.balances)} balances")

page = client.transactions.list(order="desc", limit=10)
```

### Scopes

Records that belong to another resource are listed by naming it. These are the routes
`/accounts/{id}/payments`, `/ledgers/{sequence}/operations` and so on:

```py
client.payments.list(account="G...")
client.operations.list(ledger=52_000_000)
client.effects.list(transaction="3389e9f0...")
client.trades.list(liquidity_pool="dd7b1ab8...")
```

A method takes at most one scope. Arguments that Horizon would refuse together, or
answer wrongly, raise `ValueError` before anything is sent, with the names of the
arguments.

### Values

The resources are frozen [pydantic](https://docs.pydantic.dev/) models. Amounts are
`Decimal`, so that no stroop is lost, and times are `datetime` in UTC. Identifiers stay
strings as Horizon sends them, offer IDs included.

Python writes a `Decimal` of zero with seven decimal places as `0E-7`. To print an
amount as Horizon wrote it, `0.0000000`, format it with `f`: `f"{balance.balance:f}"`.

An asset can be given as `"native"`, as `"CODE:ISSUER"`, or as an `Asset` model taken
from another response:

```py
usdc = "USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"
book = client.order_book.get(selling="native", buying=usdc, limit=5)
for level in book.bids:
    print(f"{level.amount} at {level.price}")
```

### Operations and effects

Each type of operation and effect has its own class, such as `PaymentOperation` or
`AccountCreditedEffect`. A page of them holds the class of each record. Tell them apart
with `match` or `isinstance`:

```py
from stellar_horizon.models import CreateAccountOperation, PaymentOperation

for operation in client.operations.list(account="G...", limit=50):
    match operation:
        case PaymentOperation():
            print(f"paid {operation.amount} {operation.asset_code or 'XLM'}")
        case CreateAccountOperation():
            print(f"created {operation.account} with {operation.starting_balance}")
        case _:
            print(operation.type)
```

The class is chosen by `type_i`, the number of the type, which never changes; `type`,
its name, is kept as Horizon sent it. Comparing `type_i` does not narrow the type for a
type checker, because `UnknownOperation` can have any number.

## Paging

A list method returns one page. Iterating it yields its records and fetches nothing:

```py
page = client.transactions.list(account="G...", order="desc", limit=20)
for transaction in page:
    print(transaction.hash)
```

`page.next()` fetches the page after it, in the same order. `page.iter_records()` goes
through this page and the pages after it, until a page comes back empty; pass
`max_records` to stop sooner, because a history endpoint can hold millions of records.

Paging is not a snapshot. Each page is read when it is fetched, so records that arrive
in the meantime show up on a later page, and a list of current state, such as offers,
can change between two pages.

### What `prev()` returns

`page.prev()` follows the page's `prev` link as Horizon wrote it. This is what the other
Stellar SDKs do, for JavaScript, Java and Go among them, and this package keeps the same
behaviour on purpose: a page means the same thing in every language, and what you read
about paging in the Horizon documentation or in examples for another SDK holds here
too.

Horizon builds that link by turning the order around and starting from the first record
of the page. So the previous page has the records you expect, but:

- **in the opposite order**, and
- **its `next()` goes on in the opposite direction**, away from the page you started
  from.

With transactions in descending order, three to a page, where a larger number is newer:

```py
page = client.transactions.list(order="desc", limit=3)  # 9 8 7   (order=desc)
older = page.next()  # 6 5 4   (order=desc)
back = older.prev()  # 7 8 9   (order=asc)
back.next()  # 10 11 12
```

`back` holds the records of `page`, oldest first, and `back.next()` returns records newer
than all of them, not `6 5 4` again.

To page back and forth, for example behind the buttons of a user interface, keep the
pages you have fetched and go back through them, or ask again with a cursor:

```py
pages = [client.transactions.list(order="desc", limit=20)]
pages.append(pages[-1].next())  # forward
pages.pop()  # back: the previous page, as it was
```

Before the first page of a history in ascending order there is nothing the server
keeps, and Horizon answers its `prev` link with 410: `prev()` raises
`BeforeHistoryError`.

`page.links` has the `self`, `next` and `prev` links as Horizon sent them. Two endpoints
differ: trade aggregations send an empty `prev` link, so `prev()` raises `PagingError`,
and path finding returns a list with no links at all.

Trade aggregations in ascending order, the default, need an `end_time` to page forward.
Without one, Horizon writes `start_time=0` into the `next` link, a bug of Horizon 30.0.1,
so `next()` returns the first page again, and `iter_records()` yields it twice before it
raises `PagingError`. Like the other Stellar SDKs, this package follows the link as
Horizon wrote it rather than working around it, so that paging behaves alike in every
language:

```py
page = client.trade_aggregations.list(
    "native", usdc, 3_600_000, start_time=start, end_time=end
)
for bucket in page.iter_records():
    print(f"{bucket.timestamp}: closed at {bucket.close}")
```

## Streaming

A stream yields records as Horizon ingests them. Every resource that Horizon can stream
has a `stream()` method, which takes the same scopes as `list()`:

```py
with client.payments.stream(account="G...") as stream:
    for payment in stream:
        print(f"{payment.id}: {payment.type}")
```

Use the stream as a context manager, or call `stream.close()`, so that its connection is
released when you stop reading.

A stream belongs to the thread that reads it. While a read waits for the next record,
another thread cannot stop it, and `close()` from there raises. To stop a waiting
stream from outside, use `AsyncHorizonClient` and cancel the task that reads it.

### Where a stream starts

- **`cursor="now"`**, the default of every stream of history, starts after the latest
  ledger that the server reported when the stream was opened.
- **A paging token** starts after that record. `stream.cursor` is the paging token of
  the last record that the stream yielded.
- **`cursor=None`** starts at the oldest history the server keeps.
- **An empty string**, `cursor=""`, starts there too: Horizon reads it as no cursor,
  and the client sends it as it is. Check a cursor that comes from a file or a
  database before you pass it, or an empty one replays the whole history.

To continue where a program stopped, save `stream.cursor` after you have handled each
record, and pass it back the next time:

```py
from pathlib import Path

saved = Path("payments.cursor")
cursor = saved.read_text() if saved.exists() else "now"
with client.payments.stream(account="G...", cursor=cursor) as stream:
    for payment in stream:
        handle(payment)
        if stream.cursor is not None:
            # Replace the file in one step: a crash in the middle of a plain write
            # would leave it empty, and an empty cursor starts at the oldest history.
            draft = saved.with_suffix(".tmp")
            draft.write_text(stream.cursor)
            draft.replace(saved)
```

A cursor older than the history the server keeps is moved forward by the server,
without notice, to the oldest ledger it has, and the records in between are missed.
`client.root().history_elder_ledger` says how far back the server goes.

### What a stream promises

- Within one stream, each record is yielded once, and in order.
- Across restarts, a program that saves the cursor after handling a record gets every
  record at least once. A crash between handling a record and saving the cursor repeats
  that record, so make handling it safe to repeat.
- Only within the history the server keeps.

### On a poor connection

A stream runs over many connections, one after the other, and that is normal. Horizon
ends every stream response after its connection timeout, 55 seconds by default, or after
200 records. The client ends a connection on which nothing came for 15 seconds, because
a dead connection looks the same as a quiet one.

Either way the stream connects again from its cursor without you seeing it, and nothing
is lost on the way. A quiet stream makes a new request about every 15 seconds.

A connection that worked is never a failure, however it ends: it delivered a record,
was ended by the server, or stayed open for 15 seconds. Not getting a working
connection is a failure: no connection, no answer, a 429 or 5xx, or a connection that
dies at once. Failures wait 1 second, then longer each time up to 30 seconds, and no
shorter than the server's `Retry-After`. Each is logged at `WARNING` on the logger
`stellar_horizon`.

When failures have gone on for `give_up_after` seconds without one working connection,
the stream raises `StreamError`, which has the `cursor` to start again from. The default
is 5 minutes; `give_up_after=None` never gives up. A redirect, a 4xx other than 429,
a problem in an `error` event that does not pass, and a record that cannot be read end
the stream at once.

### Objects and offers

`order_book.stream()` and `accounts.stream_data()` yield one object: as it is when the
stream opens, then each time it changes. The server checks once per ledger, so states in
between are not seen, and an object equal to the last one is not yielded again. These
streams have no cursor.

`offers.stream(seller=...)` is not a feed of changes. It yields the offers of the account
that are open now, by increasing ID, and then each new offer. It never yields a change
to an offer or its removal; to follow those, stream the account's effects or trades.
Its cursor is an offer ID. `cursor="now"` raises `ValueError`: Horizon would read it as
a place in the history, which is above every offer ID, and send no offer at all.

Horizon cannot stream an account in a useful way: it sends the account once per
connection and never again. Stream the account's transactions, operations or effects,
and fetch the account when they say it changed.

## Submitting

The package sends transactions that are already built and signed, as base64 XDR. Build
them with the [Python Stellar SDK](https://github.com/StellarCN/py-stellar-base); with
it, the XDR is `envelope.to_xdr()`.

### `submit()`

`transactions.submit()` sends the transaction and waits, for up to 30 seconds, until it
is in a ledger:

```py
from stellar_horizon import OutcomeUnknownError, TransactionFailedError

try:
    transaction = client.transactions.submit(envelope.to_xdr())
except TransactionFailedError as error:
    print(f"did not succeed: {error.result_codes}")
except OutcomeUnknownError as error:
    print(f"not known; look it up later: {error.hash}")
else:
    print(f"{transaction.hash} is in ledger {transaction.ledger}")
```

### `enqueue()`

`transactions.enqueue()` hands the transaction to stellar-core and returns as soon as
stellar-core has looked at it, without waiting for a ledger. It returns the result for
every answer of stellar-core; look at `tx_status`:

```py
result = client.transactions.enqueue(envelope.to_xdr())
match result.tx_status:
    case "PENDING":
        pass  # On its way into a ledger. Fetch transactions.get(result.hash) later.
    case "DUPLICATE":
        pass  # Sent before, and still on its way.
    case "TRY_AGAIN_LATER":
        pass  # stellar-core is busy, or has a transaction of the same account.
    case "ERROR":
        print(result.error_result_xdr)  # Refused; the TransactionResult says why.
```

### Three outcomes

A submission succeeds, does not succeed, or its outcome is not known.

| Outcome | What you get |
|---|---|
| Succeeded | The return value |
| Did not succeed | `TransactionFailedError`, `BadRequestError`, another `ResponseError`, or `TransportError` when no connection could be made |
| Not known | `OutcomeUnknownError` |

A transaction that did not succeed was either refused, or applied and failed:

- **Refused**: no connection could be made, Horizon refused the request, for example
  because the envelope is malformed, or stellar-core refused the transaction, for
  example because its sequence number is not the next one or its fee is too low.
  Nothing was charged.
- **Failed**: `TransactionFailedError` also comes for a transaction that is in a
  ledger and failed when it was applied, for example a payment whose source lacked the
  funds. Its fee was charged and its sequence number is used.

`TransactionFailedError.result_codes` says why. To know whether the transaction is in a
ledger, look it up with `transactions.get()`.

The outcome is not known when the connection broke or timed out after the request was
sent, when the answer cannot be read, or on a 5xx. One 5xx is a refusal: 503
`stale_history`, which Horizon sends before it submits anything, raises `ServerError`.
The transaction may be in a ledger
already, or on its way into one. `OutcomeUnknownError` has the `envelope_xdr`, the
`hash` when Horizon gave it, and the `response` when there was one.

Then send the same envelope again, which is safe: it is the same transaction, and the
network applies it once at most. Or look the hash up with `transactions.get()` after the
transaction's time bounds have passed: a 404 right after a submission does not mean
that it failed.

The client never sends a submission twice by itself. Cancelling an `await` on `submit()`
or `enqueue()` leaves the outcome unknown too.

### Payments that need a memo

[SEP-29](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0029.md)
lets an account, usually an exchange's, ask that every payment to it carry a memo, by
setting its data entry `config.memo_required` to `1`. A payment without one is likely
to be lost.

This package does not read transactions, so `submit()` and `enqueue()` do not check
this. They offer the lookup that the check needs:

```py
client.accounts.requires_memo("G...")  # True if the account asks for a memo
```

It returns `False` for an account without the entry, for one that does not exist, and
for a muxed address, `M...`, which SEP-29 exempts. The check itself, which looks at the
memo and the destination of each payment, path payment and merge, belongs in the Python
Stellar SDK, which builds the transaction. Until the SDK has it,
[`examples/check_memo_required.py`](https://github.com/lightsail-network/py-stellar-horizon/blob/main/examples/check_memo_required.py)
shows it written out.

## Errors

Every error that the package raises comes from `HorizonError`:

```text
HorizonError
├── TransportError            no usable response: connection, TLS, timeout, decoding
├── ResponseError             a status that is not a success: 3xx, 4xx, 5xx
│   ├── BadRequestError         400
│   ├── NotFoundError           404
│   ├── BeforeHistoryError      410: older than the history the server keeps
│   ├── RateLimitError          429
│   ├── TransactionFailedError  400 transaction_failed
│   └── ServerError             5xx
├── OutcomeUnknownError       a submission whose outcome is not known
├── InvalidResponseError      a response the models cannot read
├── StreamError               a stream that cannot go on
└── PagingError               a page with no link to follow
```

- **`ResponseError`** has the `response`, and Horizon's problem document as `problem`,
  with the short `type`, such as `not_found`, the `status_code` and the `extras`.
  `BadRequestError` adds `invalid_field` and `reason`, `RateLimitError` adds
  `retry_after`, and `TransactionFailedError` adds `result_codes`, `envelope_xdr`,
  `result_xdr` and `diagnostic_events`.
- **A redirect** is a `ResponseError` too. The client does not follow redirects, so a
  base URL that redirects, such as `http://` for a server that wants `https://`, raises
  it at the first request, with the scheme and host to use in its message.
- **`TransportError`** keeps the httpx2 exception as `__cause__`.
- **`InvalidResponseError`** has the `body` that could not be read, and the `response`.
- **Wrong arguments** raise `ValueError` or `TypeError` before anything is sent.

The errors can be pickled, with the response they carry, so a process pool can hand
one from a worker to its parent.

## Async

`AsyncHorizonClient` has the same resources and methods. Requests are awaited, pages
and streams are iterated with `async for`, and `close()` is `aclose()`:

```py
import asyncio

from stellar_horizon import AsyncHorizonClient


async def main() -> None:
    async with AsyncHorizonClient("https://horizon-testnet.stellar.org") as client:
        root = await client.root()
        print(root.history_latest_ledger)
        async with client.ledgers.stream() as stream:
            async for ledger in stream:
                print(f"ledger {ledger.sequence} closed at {ledger.closed_at}")


asyncio.run(main())
```

The pages of an async client are `AsyncPage`, with `await page.next()` and
`async for record in page.iter_records()`. Pass an `httpx2.AsyncClient` as `http_client`.
It is tested on asyncio.

## A newer Horizon

The models were checked against the Horizon release in `stellar_horizon.HORIZON_VERSION`.
A newer Horizon keeps working:

- **New fields** are kept, and can be read from `model_extra`:

  ```python
  from stellar_horizon.models import Asset

  asset = Asset.model_validate({"asset_type": "native", "new_field": 1})
  assert asset.model_extra == {"new_field": 1}
  ```

- **New types of operations and effects** are read as `UnknownOperation` and
  `UnknownEffect`, with their fields in `model_extra`.
- **New endpoints and parameters** can be reached with `client.request()`, which sends
  any request, raises errors like the other methods, and returns the `httpx2.Response`:

  ```py
  response = client.request("GET", "/offers", params={"limit": "1"})
  print(f"latest ledger: {response.headers['Latest-Ledger']}")
  print(response.json())
  ```

  Horizon sends the `Latest-Ledger` header with the current state, such as accounts,
  offers and path finding, and not with history, such as ledgers or transactions.

## Authentication

Providers of Horizon ask for a key in one of three places. Each works with the client.

A key in the path is part of the base URL. The path is kept in every request, also when
following the links of a page:

```python
from stellar_horizon import HorizonClient

client = HorizonClient("https://horizon.example.com/v1/my-key")
client.close()
```

A key in the query string is part of the base URL too. Its parameters are sent with
every request, streams and submissions included. If the server echoes them in the links
of a page, the base URL's value is used, once:

```python
from stellar_horizon import HorizonClient

client = HorizonClient("https://horizon.example.com/?apikey=my-key")
client.close()
```

A key in a header goes in `headers`. They are sent with every request, streams and
submissions included, and take the place of headers of the same name:

```python
from stellar_horizon import HorizonClient

client = HorizonClient(
    "https://horizon.example.com", headers={"Authorization": "Bearer my-key"}
)
client.close()
```

`headers` can be used together with an `http_client` of your own.

The client sends requests only to the host of the base URL: the links in a response
lend their query string, never their host.

!!! warning "Keys in logs"

    `repr()` of a client shows only the scheme and the host of the base URL. httpx2,
    however, logs every request at the `INFO` level with its full URL, path and query
    string included. If the key is in the URL, keep the `httpx2` logger at `WARNING`
    or above:

    ```python
    import logging

    logging.getLogger("httpx2").setLevel(logging.WARNING)
    ```
