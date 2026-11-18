.PHONY: check format lint typecheck test generate check-generated build release-prep

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

# Write the sync code in _sync/ from the async code in _async/.
generate:
	uv run python scripts/unasync.py

check-generated:
	uv run python scripts/unasync.py --check

test:
	uv run pytest --cov --cov-report=term-missing

build:
	uv build

# Usage: make release-prep VERSION=0.1.0
release-prep:
	@test -n "$(VERSION)" || (echo "VERSION is required" >&2; exit 1)
	uv version $(VERSION)
	uv run git-cliff --unreleased --tag v$(VERSION) --prepend CHANGELOG.md
