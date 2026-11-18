"""Print the payments of an account as they happen, and remember where to continue."""

from pathlib import Path

from stellar_horizon import HorizonClient
from stellar_horizon.models import CreateAccountOperation, PaymentOperation

# A busy account of an exchange. It sends or receives a payment about once a minute,
# so that the stream has something to show soon. Put your own account here.
ACCOUNT = "GAPQZLGAUN6DOCHGVGTIHW3OCCCAZHGXIRLMKH76Z7764CINF4P7LBD4"
CURSOR_FILE = Path("payments.cursor")


def save(cursor: str) -> None:
    """Replace the cursor file in one step.

    A crash in the middle of a plain write would leave the file empty, and an
    empty cursor starts a stream at the oldest history the server keeps.
    """
    draft = CURSOR_FILE.with_suffix(".tmp")
    draft.write_text(cursor)
    draft.replace(CURSOR_FILE)


# Continue where the last run stopped, or start with what happens from now on.
cursor = CURSOR_FILE.read_text().strip() if CURSOR_FILE.exists() else "now"

with (
    HorizonClient("https://horizon.stellar.org") as client,
    client.payments.stream(account=ACCOUNT, cursor=cursor) as stream,
):
    for payment in stream:
        match payment:
            case CreateAccountOperation():
                print(f"created {payment.account} with {payment.starting_balance} XLM")
            case PaymentOperation():
                asset = payment.asset_code or "XLM"
                if payment.to == ACCOUNT:
                    print(f"received {payment.amount} {asset} from {payment.from_}")
                else:
                    print(f"sent {payment.amount} {asset} to {payment.to}")
            case _:
                print(f"{payment.type} in {payment.transaction_hash}")
        # Save the cursor after handling the record: a restart then repeats nothing
        # that was handled, and misses nothing that was not.
        if stream.cursor is not None:
            save(stream.cursor)
