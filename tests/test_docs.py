"""The documentation: its Python examples run, or at least compile.

A `python` block runs here, offline. A `py` block needs a server, a signed envelope or
names from the text around it, so it is only compiled.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
RUNS = re.compile(r"^ *```python\n(.*?)^ *```$", re.DOTALL | re.MULTILINE)
COMPILES = re.compile(r"^ *```py\n(.*?)^ *```$", re.DOTALL | re.MULTILINE)


def dedent(block: str) -> str:
    lines = block.splitlines()
    indent = min(len(line) - len(line.lstrip()) for line in lines if line.strip())
    return "\n".join(line[indent:] for line in lines) + "\n"


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_examples_run(page: Path) -> None:
    for example in RUNS.findall(page.read_text(encoding="utf-8")):
        exec(dedent(example), {})  # noqa: S102


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_examples_compile(page: Path) -> None:
    for example in COMPILES.findall(page.read_text(encoding="utf-8")):
        compile(dedent(example), str(page), "exec")


def test_the_guide_has_examples() -> None:
    guide = (ROOT / "docs" / "guide.md").read_text(encoding="utf-8")
    assert len(RUNS.findall(guide)) >= 5
    assert len(COMPILES.findall(guide)) >= 10
