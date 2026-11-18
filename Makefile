.PHONY: check format lint typecheck test build release-prep

check: lint typecheck test

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

test:
	uv run pytest --cov --cov-report=term-missing

build:
	uv build

# Usage: make release-prep VERSION=0.1.0
release-prep:
	@test -n "$(VERSION)" || (echo "VERSION is required" >&2; exit 1)
	uv version $(VERSION)
	uv run git-cliff --unreleased --tag v$(VERSION) --prepend CHANGELOG.md
