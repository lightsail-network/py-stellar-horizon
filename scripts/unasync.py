"""Write the synchronous code from the asynchronous code.

The async modules in `src/stellar_horizon/_async/` and the async tests in
`tests/_async/` are the source. This script turns each into its sync twin under
`_sync/` with a fixed table of replacements, tidies it with ruff and writes it, or with
`--check` fails if a committed file differs from what it would write.

It works on text, not on a syntax tree, so the async code is written to keep the
replacements simple: no `async`/`await` inside strings that must survive, and no names
that contain one of the replaced words by accident. A replacement that leaves `async`,
`await` or `anyio` behind fails the run.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAIRS = [
    (
        ROOT / "src" / "stellar_horizon" / "_async",
        ROOT / "src" / "stellar_horizon" / "_sync",
    ),
    (ROOT / "tests" / "_async", ROOT / "tests" / "_sync"),
]
HEADER = "# Generated from {source} by scripts/unasync.py. Do not edit.\n"

# Regular expressions, applied in order.
REPLACEMENTS = [
    (r"\basync def\b", "def"),
    (r"\basync with\b", "with"),
    (r"\basync for\b", "for"),
    (r"\bawait ", ""),
    (r"pytestmark = pytest\.mark\.anyio\n", ""),
    (r"@pytest\.mark\.anyio\n", ""),
    (r"\bimport anyio\b", "import time"),
    (r"\banyio\.sleep\b", "time.sleep"),
    (r"\b_async\b", "_sync"),
    (r"\bAsyncByteStream\b", "SyncByteStream"),
    (r"\bAsyncGenerator\[(\w+), None\]", r"Generator[\1, None, None]"),
    # AsyncHorizonClient, AsyncPage, AsyncClient, AsyncIterator and the like.
    (r"\bAsync(?=[A-Z])", ""),
    (r"\bStopAsyncIteration\b", "StopIteration"),
    (r"\b__aenter__\b", "__enter__"),
    (r"\b__aexit__\b", "__exit__"),
    (r"\b__aiter__\b", "__iter__"),
    (r"\b__anext__\b", "__next__"),
    (r"\baiter_bytes\b", "iter_bytes"),
    (r"\baiter_sse\b", "iter_sse"),
    (r"\baread\b", "read"),
    (r"\baclose\b", "close"),
    (r"\baclosing\b", "closing"),
    (r"\banext\b", "next"),
    (r"\bhandle_async_request\b", "handle_request"),
]
LEFTOVER = re.compile(r"\b(async|await|anyio)\b")


def unasync(text: str) -> str:
    """Return the sync version of the async source `text`."""
    for pattern, replacement in REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    return text


def _ruff(arguments: list[str], text: str) -> str:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "ruff", *arguments, "-"],
        input=text,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise SystemExit(result.stderr)
    return result.stdout


def tidy(text: str, path: Path) -> str:
    """Sort the imports of `text` and format it, as ruff would the file at `path`.

    The replacements can leave imports out of order, and a name imported twice, as
    `AsyncIterator, Iterator` becomes `Iterator, Iterator`.
    """
    name = ["--stdin-filename", str(path)]
    text = _ruff(["check", "--select", "I", "--fix", "--quiet", *name], text)
    return _ruff(["format", *name], text)


def expected_files() -> dict[Path, str]:
    """Map every file to generate to its content."""
    files: dict[Path, str] = {}
    for source_dir, target_dir in PAIRS:
        for source in sorted(source_dir.glob("*.py")):
            target = target_dir / source.name
            text = unasync(source.read_text(encoding="utf-8"))
            leftover = [
                f"{source.relative_to(ROOT)}:{number}: {line.strip()}"
                for number, line in enumerate(text.splitlines(), 1)
                if LEFTOVER.search(line)
            ]
            if leftover:
                msg = "async code left after the replacements:\n" + "\n".join(leftover)
                raise SystemExit(msg)
            header = HEADER.format(
                source=source.relative_to(source_dir.parent).as_posix()
            )
            files[target] = tidy(header + text, target)
    return files


def generated_files() -> set[Path]:
    """Return the files that a previous run wrote."""
    found: set[Path] = set()
    for _, target_dir in PAIRS:
        for path in target_dir.glob("*.py"):
            if path.read_text(encoding="utf-8").startswith("# Generated from "):
                found.add(path)
    return found


def main() -> int:
    """Write the sync files, or check them with `--check`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if a file differs")
    args = parser.parse_args()

    expected = expected_files()
    stale = generated_files() - expected.keys()
    differ = sorted(
        path
        for path, text in expected.items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    )
    if args.check:
        for path in [*differ, *sorted(stale)]:
            print(f"out of date: {path.relative_to(ROOT)}")
        return 1 if differ or stale else 0
    for path in differ:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected[path], encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    for path in sorted(stale):
        path.unlink()
        print(f"removed {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
