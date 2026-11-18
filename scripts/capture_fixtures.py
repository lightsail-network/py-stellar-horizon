"""Fetch response bodies from the public Horizon instances for the tests.

The fixtures are one set: one file for each case, whichever network it came from.
Bodies are written as Horizon sent them, and `tests/fixtures/manifest.json` records the
URL, the date, the status and the content type of each. Cases that no public server
gives on request are mocked in the tests instead.

Reading requests go to the public network, and to the test network for what the public
one lacks. Requests that submit transactions go to the test network, with accounts that
the script creates through friendbot.

`operations/inflation.json` comes from stellar-model 0.7.0: inflation was retired in
protocol 12, and the public servers no longer keep history that old.

Usage:
    uv run python scripts/capture_fixtures.py            # fetch what is missing
    uv run python scripts/capture_fixtures.py --force    # fetch everything again
"""

import argparse
import datetime as dt
import json
import warnings
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx2
from stellar_sdk import (
    Account,
    Asset,
    Keypair,
    LiquidityPoolAsset,
    Network,
    TransactionBuilder,
)
from stellar_sdk.operation.allow_trust import TrustLineEntryFlag

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
MANIFEST = FIXTURES / "manifest.json"
NETWORKS = {
    "mainnet": "https://horizon.stellar.org",
    "testnet": "https://horizon-testnet.stellar.org",
}
# An account that exists on the public network and holds several assets.
MAINNET_ACCOUNT = "GALAXYVOIDAOPZTDLHILAJQKCVVFMD4IKLXLSZV5YHO7VY74IWZILUTO"
# An account on the public network with three payments: two pages of two, then empty.
SMALL_ACCOUNT = "GBVF5SBMKRAVL5L2L3F2KUKYFKXTX7ZL57JB4NQUP7LEDDK2XPEZQUNA"
# A valid account ID that no account on the public network has.
MISSING_ACCOUNT = "GAB5L2N54ZYS2DCUOEEHI2F646EOMS2JZY3PGFKYSYW2EQEWK5QJNLGP"
EVENT_STREAM = {"Accept": "text/event-stream"}
OPERATION_TYPES = [
    "create_account",
    "payment",
    "path_payment_strict_receive",
    "manage_sell_offer",
    "create_passive_sell_offer",
    "set_options",
    "change_trust",
    "allow_trust",
    "account_merge",
    "inflation",
    "manage_data",
    "bump_sequence",
    "manage_buy_offer",
    "path_payment_strict_send",
    "create_claimable_balance",
    "claim_claimable_balance",
    "begin_sponsoring_future_reserves",
    "end_sponsoring_future_reserves",
    "revoke_sponsorship",
    "clawback",
    "clawback_claimable_balance",
    "set_trust_line_flags",
    "liquidity_pool_deposit",
    "liquidity_pool_withdraw",
    "invoke_host_function",
    "extend_footprint_ttl",
    "restore_footprint",
]
EFFECT_TYPES = [
    "account_created",
    "account_removed",
    "account_credited",
    "account_debited",
    "account_thresholds_updated",
    "account_home_domain_updated",
    "account_flags_updated",
    "account_inflation_destination_updated",
    "signer_created",
    "signer_removed",
    "signer_updated",
    "trustline_created",
    "trustline_removed",
    "trustline_updated",
    "trustline_authorized",
    "trustline_deauthorized",
    "trustline_authorized_to_maintain_liabilities",
    "trustline_flags_updated",
    "trade",
    "data_created",
    "data_removed",
    "data_updated",
    "sequence_bumped",
    "claimable_balance_created",
    "claimable_balance_claimant_created",
    "claimable_balance_claimed",
    "account_sponsorship_created",
    "account_sponsorship_updated",
    "account_sponsorship_removed",
    "trustline_sponsorship_created",
    "trustline_sponsorship_updated",
    "trustline_sponsorship_removed",
    "data_sponsorship_created",
    "data_sponsorship_updated",
    "data_sponsorship_removed",
    "claimable_balance_sponsorship_created",
    "claimable_balance_sponsorship_updated",
    "claimable_balance_sponsorship_removed",
    "signer_sponsorship_created",
    "signer_sponsorship_updated",
    "signer_sponsorship_removed",
    "claimable_balance_clawed_back",
    "liquidity_pool_deposited",
    "liquidity_pool_withdrew",
    "liquidity_pool_trade",
    "liquidity_pool_created",
    "liquidity_pool_removed",
    "liquidity_pool_revoked",
    "contract_credited",
    "contract_debited",
]
# USDC of Circle on the public network, which has an active market.
USDC = "USDC:GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"
USDC_PARAMS = (
    "credit_alphanum4&{side}_asset_code=USDC"
    "&{side}_asset_issuer=GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"
)
SEARCH_PAGES = 150
# Operations captured by ID, from the test network as of 2026-11-14, which is reset now
# and then: a claimable balance with nested predicates, and a Wasm upload, whose
# `parameters` and `asset_balance_changes` are null.
PINNED_OPERATIONS = {
    "create_claimable_balance": "24562930850734081",
    "invoke_host_function_upload": "24569918762553345",
}
# Not on any public server any more; see the module docstring.
NOT_SEARCHED = {"inflation"}


class Capturer:
    """Fetches bodies and keeps the manifest."""

    def __init__(self, *, force: bool) -> None:
        self.force = force
        self.client = httpx2.Client(timeout=60, follow_redirects=False)
        self.manifest: dict[str, dict[str, object]] = (
            json.loads(MANIFEST.read_text(encoding="utf-8"))
            if MANIFEST.exists()
            else {}
        )
        self.versions: dict[str, str] = {}

    def horizon_version(self, network: str) -> str:
        """Return the version of Horizon that serves `network`."""
        if network not in self.versions:
            root = self.client.get(NETWORKS[network]).json()
            self.versions[network] = str(root["horizon_version"])
        return self.versions[network]

    def get_json(self, url: str) -> Any:  # noqa: ANN401
        """Fetch `url` and return its decoded body."""
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    def capture(
        self,
        name: str,
        network: str,
        path: str,
        *,
        method: str = "GET",
        data: Mapping[str, str] | None = None,
        content: str | None = None,
        headers: Mapping[str, str] | None = None,
        suffix: str = ".json",
    ) -> httpx2.Response | None:
        """Store the body of `path` on `network` as `<network>/<name><suffix>`.

        Returns the response, or `None` when the file exists and `--force` is off.
        """
        relative = f"{name}{suffix}"
        target = FIXTURES / relative
        if target.exists() and not self.force:
            return None
        url = NETWORKS[network] + path
        if headers == EVENT_STREAM:
            response = self.read_stream(url)
        else:
            response = self.client.request(
                method, url, data=data, content=content, headers=headers
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        entry: dict[str, object] = {
            "source": "capture",
            "url": url,
            "captured": dt.datetime.now(dt.UTC).date().isoformat(),
            "horizon_version": self.horizon_version(network),
            "status": response.status_code,
            "content_type": response.headers.get("content-type", ""),
        }
        if method != "GET":
            entry["method"] = method
        self.manifest[relative] = entry
        print(f"captured {relative} ({response.status_code})")
        return response

    def read_stream(self, url: str) -> httpx2.Response:
        """Read an event stream until the server ends it, and return it as one body."""
        with self.client.stream(
            "GET", url, headers=EVENT_STREAM, timeout=httpx2.Timeout(60, read=90)
        ) as response:
            body = b"".join(response.iter_bytes())
            return httpx2.Response(
                response.status_code,
                headers={"content-type": response.headers.get("content-type", "")},
                content=body,
            )

    def capture_pages(self, name: str, network: str, path: str) -> None:
        """Store a page, every page after it up to an empty one, and one prev page."""
        response = self.capture(f"{name}_1", network, path)
        number = 1
        while response is not None:
            body = response.json()
            records = body["_embedded"]["records"]
            if number == 2:  # noqa: PLR2004
                prev = httpx2.URL(body["_links"]["prev"]["href"])
                self.capture(f"{name}_2_prev", network, prev.raw_path.decode())
            if not records:
                break
            number += 1
            following = httpx2.URL(body["_links"]["next"]["href"])
            response = self.capture(
                f"{name}_{number}", network, following.raw_path.decode()
            )

    def find_operations(self, network: str) -> dict[str, str]:
        """Walk recent operations on `network` for the types that are still missing."""
        wanted = {
            name
            for name in OPERATION_TYPES
            if name not in PINNED_OPERATIONS
            and name not in NOT_SEARCHED
            and not (FIXTURES / "operations" / f"{name}.json").exists()
        }
        found: dict[str, str] = {}
        url = NETWORKS[network] + "/operations?order=desc&limit=200&include_failed=true"
        for _ in range(SEARCH_PAGES):
            if not wanted - found.keys():
                break
            page = self.get_json(url)
            records = page["_embedded"]["records"]
            if not records:
                break
            for record in records:
                if record["type"] in wanted and record["type"] not in found:
                    found[record["type"]] = record["id"]
            url = page["_links"]["next"]["href"]
        return found

    def save_manifest(self) -> None:
        """Write the manifest, sorted."""
        MANIFEST.write_text(
            json.dumps(dict(sorted(self.manifest.items())), indent=2) + "\n",
            encoding="utf-8",
        )


def capture_pages_and_streams(capturer: Capturer) -> None:
    """Pages that link to each other, and event streams as the server sent them."""
    capturer.capture_pages(
        "pages/payments",
        "mainnet",
        f"/accounts/{SMALL_ACCOUNT}/payments?order=asc&limit=2",
    )
    recent = capturer.get_json(NETWORKS["mainnet"] + "/payments?order=desc&limit=20")[
        "_embedded"
    ]["records"]
    start = recent[-1]["paging_token"]
    first = capturer.capture(
        "streams/payments_1",
        "mainnet",
        f"/payments?cursor={start}&limit=3",
        headers=EVENT_STREAM,
        suffix=".sse",
    )
    if first is not None:
        ids = [
            line.removeprefix("id: ")
            for line in first.text.splitlines()
            if line.startswith("id: ")
        ]
        capturer.capture(
            "streams/payments_2",
            "mainnet",
            f"/payments?cursor={ids[-1]}&limit=3",
            headers=EVENT_STREAM,
            suffix=".sse",
        )
    # An account that is not active: the server ends the stream after its timeout.
    capturer.capture(
        "streams/quiet",
        "mainnet",
        f"/accounts/{SMALL_ACCOUNT}/payments?cursor=now&limit=3",
        headers=EVENT_STREAM,
        suffix=".sse",
    )


def capture_resources(capturer: Capturer) -> None:
    """One resource and one page of each kind that the earlier steps lack."""
    latest = capturer.get_json(NETWORKS["mainnet"] + "/ledgers?order=desc&limit=1")
    sequence = latest["_embedded"]["records"][0]["sequence"]
    capturer.capture("ledger", "mainnet", f"/ledgers/{sequence}")
    capturer.capture("ledgers", "mainnet", "/ledgers?order=desc&limit=5")
    capturer.capture("fee_stats", "mainnet", "/fee_stats")
    capturer.capture("operations", "mainnet", "/operations?order=desc&limit=50")
    for name, collection in [
        ("offer", "offers"),
        ("claimable_balance", "claimable_balances"),
        ("liquidity_pool", "liquidity_pools"),
    ]:
        page = capturer.capture(
            f"{collection}", "mainnet", f"/{collection}?order=desc&limit=10"
        )
        if page is not None:
            first = page.json()["_embedded"]["records"][0]
            capturer.capture(name, "mainnet", f"/{collection}/{first['id']}")
    capturer.capture("trades", "mainnet", "/trades?order=desc&limit=10")
    capturer.capture(
        "trades_liquidity_pool",
        "mainnet",
        "/trades?trade_type=liquidity_pool&order=desc&limit=5",
    )
    capturer.capture(
        "trade_aggregations",
        "mainnet",
        "/trade_aggregations?base_asset_type=native&counter_asset_type="
        + USDC_PARAMS.format(side="counter")
        + "&resolution=3600000&order=desc&limit=5",
    )
    order_book = (
        "/order_book?selling_asset_type=native&buying_asset_type="
        + USDC_PARAMS.format(side="buying")
        + "&limit=5"
    )
    capturer.capture("order_book", "mainnet", order_book)
    capturer.capture(
        "paths_strict_receive",
        "mainnet",
        "/paths/strict-receive?source_assets=native&destination_asset_type="
        + USDC_PARAMS.format(side="destination")
        + "&destination_amount=10",
    )
    capturer.capture(
        "paths_strict_send",
        "mainnet",
        f"/paths/strict-send?source_asset_type=native&source_amount=10"
        f"&destination_assets={USDC}",
    )
    capturer.capture("assets", "mainnet", "/assets?asset_code=USDC&limit=10")
    # Object streams and the stream of offers send what exists, then wait for
    # changes until the server ends the stream after its timeout.
    capturer.capture(
        "streams/order_book", "mainnet", order_book, headers=EVENT_STREAM, suffix=".sse"
    )
    offers = json.loads((FIXTURES / "offers.json").read_text(encoding="utf-8"))
    seller = offers["_embedded"]["records"][0]["seller"]
    capturer.capture(
        "streams/offers",
        "mainnet",
        f"/accounts/{seller}/offers?limit=3",
        headers=EVENT_STREAM,
        suffix=".sse",
    )


class EffectFinder:
    """Finds one effect of each type that has no fixture yet, and captures it.

    Effects have no route of their own, so each is captured as a page that holds only
    that effect, requested with the cursor of the effect before it.
    """

    def __init__(self, capturer: Capturer) -> None:
        self.capturer = capturer
        self.missing = [
            name
            for name in EFFECT_TYPES
            if not (FIXTURES / "effects" / f"{name}.json").exists()
        ]

    def take(
        self, network: str, path: str, records: list[Any], cursor: str | None
    ) -> None:
        """Capture the records whose type is missing, each by the cursor before it."""
        before = cursor
        for record in records:
            if record["type"] in self.missing and before is not None:
                self.capturer.capture(
                    f"effects/{record['type']}",
                    network,
                    f"{path}&limit=1&cursor={before}",
                )
                self.missing.remove(record["type"])
            before = record["paging_token"]

    def take_all(self, network: str, path: str) -> None:
        """Take from all the effects under `path`, in ascending order."""
        url = f"{NETWORKS[network]}{path}?order=asc&limit=200"
        records = self.capturer.get_json(url)["_embedded"]["records"]
        # In ascending order, the cursor before the first effect is "0".
        self.take(network, f"{path}?order=asc", records, "0")

    def from_operations(self) -> None:
        """Take from the effects of the operations that have fixtures."""
        for name, entry in sorted(self.capturer.manifest.items()):
            if self.missing and name.startswith("operations/"):
                url = str(entry["url"])
                for network, base in NETWORKS.items():
                    if entry.get("source") == "capture" and url.startswith(base):
                        self.take_all(network, url.removeprefix(base) + "/effects")

    def from_history(self) -> None:
        """Take from the recent effects of each network."""
        for network, base in NETWORKS.items():
            url = base + "/effects?order=desc&limit=200"
            cursor = None
            for _ in range(SEARCH_PAGES):
                if not self.missing:
                    return
                page = self.capturer.get_json(url)
                records = page["_embedded"]["records"]
                if not records:
                    break
                self.take(network, "/effects?order=desc", records, cursor)
                cursor = records[-1]["paging_token"]
                url = page["_links"]["next"]["href"]

    def from_new_transactions(self) -> None:
        """Make the effects that history lacks, on the test network, and take them."""
        for transaction_hash in make_rare_effects(self.capturer):
            self.take_all("testnet", f"/transactions/{transaction_hash}/effects")


def capture_effects(capturer: Capturer) -> None:
    """Capture one effect of each type.

    The effects come from the captured operations, then from recent history, then
    from transactions made for the purpose.
    """
    finder = EffectFinder(capturer)
    for step in [
        finder.from_operations,
        finder.from_history,
        finder.from_new_transactions,
    ]:
        if finder.missing:
            step()
    if finder.missing:
        print(f"effects not found: {', '.join(finder.missing)}")


def submit(
    capturer: Capturer,
    source: Keypair,
    build: Callable[[TransactionBuilder], TransactionBuilder],
    *signers: Keypair,
) -> str:
    """Submit a transaction of `source` on the test network, and return its hash."""
    testnet = NETWORKS["testnet"]
    account = capturer.get_json(f"{testnet}/accounts/{source.public_key}")
    builder = TransactionBuilder(
        Account(source.public_key, int(account["sequence"])),
        Network.TESTNET_NETWORK_PASSPHRASE,
        base_fee=100,
    )
    transaction = build(builder).set_timeout(300).build()
    transaction.sign(source)
    for signer in signers:
        transaction.sign(signer)
    response = capturer.client.post(
        f"{testnet}/transactions", data={"tx": transaction.to_xdr()}
    )
    if response.is_error:
        msg = f"submission failed: {response.text}"
        raise RuntimeError(msg)
    return str(response.json()["hash"])


def make_rare_effects(capturer: Capturer) -> list[str]:
    """Make the effects that recent history lacks, on the test network.

    Returns the hashes of the transactions, whose effects hold them: an authorization
    reduced and removed with `allow_trust`, which also revokes pool shares; a pool
    removed with its last trustline; and the four kinds of sponsorship moved from one
    sponsor to another.
    """
    # `allow_trust`, which stellar-sdk marks as deprecated, is the only operation that
    # gives the first two effects.
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    issuer, holder, sponsor, new_sponsor = (fund(capturer) for _ in range(4))
    sponsored = Keypair.random()
    asset = Asset("FIX", issuer.public_key)
    pool = LiquidityPoolAsset(Asset.native(), asset)
    hashes = [
        submit(
            capturer,
            issuer,
            lambda b: b.append_set_options_op(set_flags=3),
        ),
        submit(capturer, holder, lambda b: b.append_change_trust_op(asset)),
        submit(
            capturer,
            issuer,
            lambda b: b.append_allow_trust_op(
                holder.public_key, "FIX", TrustLineEntryFlag.AUTHORIZED_FLAG
            ).append_payment_op(holder.public_key, asset, "100"),
        ),
        # A pool that loses its only trustline is removed.
        submit(
            capturer,
            holder,
            lambda b: b.append_change_trust_op(pool).append_change_trust_op(pool, "0"),
        ),
        submit(
            capturer,
            holder,
            lambda b: b.append_change_trust_op(pool).append_liquidity_pool_deposit_op(
                pool.liquidity_pool_id, "10", "10", "0.5", "2"
            ),
        ),
        submit(
            capturer,
            issuer,
            lambda b: b.append_allow_trust_op(
                holder.public_key,
                "FIX",
                TrustLineEntryFlag.AUTHORIZED_TO_MAINTAIN_LIABILITIES_FLAG,
            ),
        ),
        submit(
            capturer,
            issuer,
            lambda b: b.append_allow_trust_op(holder.public_key, "FIX", False),  # noqa: FBT003
        ),
        submit(
            capturer,
            sponsor,
            lambda b: (
                b.append_begin_sponsoring_future_reserves_op(sponsored.public_key)
                .append_create_account_op(sponsored.public_key, "5")
                .append_change_trust_op(asset, source=sponsored.public_key)
                .append_manage_data_op("fixture", "1", source=sponsored.public_key)
                .append_ed25519_public_key_signer(
                    new_sponsor.public_key, 1, source=sponsored.public_key
                )
                .append_end_sponsoring_future_reserves_op(source=sponsored.public_key)
            ),
            sponsored,
        ),
        # Revoking inside a sponsorship of the sponsor moves each entry to the new one.
        submit(
            capturer,
            sponsor,
            lambda b: (
                b.append_begin_sponsoring_future_reserves_op(
                    sponsor.public_key, source=new_sponsor.public_key
                )
                .append_revoke_account_sponsorship_op(sponsored.public_key)
                .append_revoke_trustline_sponsorship_op(sponsored.public_key, asset)
                .append_revoke_data_sponsorship_op(sponsored.public_key, "fixture")
                .append_revoke_ed25519_public_key_signer_sponsorship_op(
                    sponsored.public_key, new_sponsor.public_key
                )
                .append_end_sponsoring_future_reserves_op()
            ),
            new_sponsor,
        ),
    ]
    print(f"made rare effects in {len(hashes)} transactions")
    return hashes


def capture_errors(capturer: Capturer) -> None:
    """Error responses that the public network gives to reading requests."""
    for name, path, headers in [
        ("not_found_account", f"/accounts/{MISSING_ACCOUNT}", None),
        ("not_found_route", "/nothing", None),
        ("invalid_accounts_params", "/accounts", None),
        ("bad_request_limit", "/transactions?limit=500", None),
        ("bad_request_cursor", "/transactions?cursor=-1", None),
        ("bad_request_order", "/transactions?order=up", None),
        ("before_history", "/ledgers/1", None),
        ("not_acceptable", f"/accounts?signer={MAINNET_ACCOUNT}", EVENT_STREAM),
        (
            "server_error",
            f"/liquidity_pools?account={MAINNET_ACCOUNT}&reserves=native",
            None,
        ),
    ]:
        capturer.capture(f"errors/{name}", "mainnet", path, headers=headers)


def fund(capturer: Capturer) -> Keypair:
    """Create an account on the test network with friendbot."""
    keypair = Keypair.random()
    response = capturer.client.get(
        "https://friendbot.stellar.org", params={"addr": keypair.public_key}
    )
    response.raise_for_status()
    return keypair


def envelope(source: Keypair, sequence: int) -> str:
    """A signed transaction that bumps the sequence number of `source` by one."""
    transaction = (
        TransactionBuilder(
            Account(source.public_key, sequence),
            Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=100,
        )
        .append_bump_sequence_op(sequence + 1)
        .set_timeout(300)
        .build()
    )
    transaction.sign(source)
    return transaction.to_xdr()


def capture_account_data(capturer: Capturer) -> None:
    """An account on the test network that requires a memo, as SEP-29 describes."""
    names = ["account_data/memo_required.json", "errors/not_found_data.json"]
    if not capturer.force and all((FIXTURES / name).exists() for name in names):
        return
    source = fund(capturer)
    account = capturer.get_json(f"{NETWORKS['testnet']}/accounts/{source.public_key}")
    transaction = (
        TransactionBuilder(
            Account(source.public_key, int(account["sequence"])),
            Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=100,
        )
        .append_manage_data_op("config.memo_required", "1")
        .set_timeout(300)
        .build()
    )
    transaction.sign(source)
    response = capturer.client.post(
        f"{NETWORKS['testnet']}/transactions", data={"tx": transaction.to_xdr()}
    )
    response.raise_for_status()
    data = f"/accounts/{source.public_key}/data"
    capturer.capture(
        "account_data/memo_required", "testnet", f"{data}/config.memo_required"
    )
    capturer.capture("errors/not_found_data", "testnet", f"{data}/no.such.key")
    capturer.capture(
        "streams/account_data",
        "testnet",
        f"{data}/config.memo_required",
        headers=EVENT_STREAM,
        suffix=".sse",
    )


def capture_submissions(capturer: Capturer) -> None:
    """Answers to submissions, on the test network."""
    capturer.capture(
        "errors/transaction_malformed",
        "testnet",
        "/transactions",
        data={"tx": "AAAA"},
        method="POST",
    )
    capturer.capture(
        "errors/unsupported_media_type",
        "testnet",
        "/transactions",
        content='{"tx": "AAAA"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    unfunded = envelope(Keypair.random(), 1)
    capturer.capture(
        "errors/transaction_failed",
        "testnet",
        "/transactions",
        data={"tx": unfunded},
        method="POST",
    )
    capturer.capture(
        "submissions/async_error",
        "testnet",
        "/transactions_async",
        data={"tx": unfunded},
        method="POST",
    )
    names = ["success", "async_pending", "async_resubmitted"]
    if not capturer.force and all(
        (FIXTURES / "submissions" / f"{name}.json").exists() for name in names
    ):
        return
    source = fund(capturer)
    account = capturer.get_json(f"{NETWORKS['testnet']}/accounts/{source.public_key}")
    sequence = int(account["sequence"])
    capturer.capture(
        "submissions/success",
        "testnet",
        "/transactions",
        data={"tx": envelope(source, sequence)},
        method="POST",
    )
    queued = envelope(source, sequence + 1)
    capturer.capture(
        "submissions/async_pending",
        "testnet",
        "/transactions_async",
        data={"tx": queued},
        method="POST",
    )
    # Sent again while the first is still waiting in the queue.
    capturer.capture(
        "submissions/async_resubmitted",
        "testnet",
        "/transactions_async",
        data={"tx": queued},
        method="POST",
    )


def main() -> int:
    """Capture every fixture that is missing, or all of them with `--force`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="fetch everything again")
    args = parser.parse_args()

    capturer = Capturer(force=args.force)
    try:
        capturer.capture("root", "mainnet", "/")
        capturer.capture("account", "mainnet", f"/accounts/{MAINNET_ACCOUNT}")
        capturer.capture("transactions", "mainnet", "/transactions?order=desc&limit=50")
        capturer.capture(
            "transactions_failed",
            "mainnet",
            "/transactions?order=desc&limit=50&include_failed=true",
        )
        capturer.capture("payments", "mainnet", "/payments?order=desc&limit=200")
        capturer.capture(
            "operations_joined",
            "mainnet",
            "/operations?order=desc&limit=10&join=transactions",
        )
        for name, operation_id in PINNED_OPERATIONS.items():
            capturer.capture(
                f"operations/{name}", "testnet", f"/operations/{operation_id}"
            )
        # Each network is searched only for the types that the one before lacked.
        for network in NETWORKS:
            for name, operation_id in capturer.find_operations(network).items():
                capturer.capture(
                    f"operations/{name}", network, f"/operations/{operation_id}"
                )
        capture_pages_and_streams(capturer)
        capture_resources(capturer)
        capture_effects(capturer)
        capture_errors(capturer)
        capture_submissions(capturer)
        capture_account_data(capturer)
    finally:
        capturer.save_manifest()
        capturer.client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
