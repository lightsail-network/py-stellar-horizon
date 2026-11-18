.PHONY: check format lint typecheck test generate check-generated build docs docs-serve release-prep

check: lint check-generated typecheck test

format:
	uv run ruff check --fix .
	uv run ruff format .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy
	uv run pyright
	uv run pyright --verifytypes stellar_horizon --ignoreexternal

# Write the sync code in _sync/ from the async code in _async/, and the coverage page
# from tests/routes.json.
generate:
	uv run python scripts/unasync.py
	uv run python scripts/api_coverage.py

check-generated:
	uv run python scripts/unasync.py --check
	uv run python scripts/api_coverage.py --check

test:
	uv run pytest --cov --cov-report=term-missing

build:
	uv build

# The docs show the changelog from a copy, which works on every platform without a
# symlink and without replacing Zensical's default Markdown extensions with an include.
docs/changelog.md: CHANGELOG.md
	cp CHANGELOG.md docs/changelog.md

docs: docs/changelog.md
	uv run --group docs zensical build --strict

docs-serve: docs/changelog.md
	uv run --group docs zensical serve

# Usage: make release-prep VERSION=0.1.0
release-prep:
	@test -n "$(VERSION)" || (echo "VERSION is required" >&2; exit 1)
	uv version $(VERSION)
	uv run git-cliff --unreleased --tag v$(VERSION) --prepend CHANGELOG.md
