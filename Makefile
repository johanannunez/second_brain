.PHONY: test lint dry-run

# The managed workspace home can be read-only. Keep uv's cache in writable storage.
export UV_CACHE_DIR ?= /tmp/uv-cache-second-brain

test:
	uv run --locked --group dev pytest

lint:
	uv run --locked --group dev ruff check .

dry-run:
	@test -n "$(WORKER)" || (echo 'Usage: make dry-run WORKER=<name>' >&2; exit 2)
	uv run --locked --group dev python -m sb.dry_run --worker "$(WORKER)"
