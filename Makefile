.PHONY: install install-ml test test-all lint format eval

install:
	uv sync

install-ml:
	uv sync --extra ml

test:
	uv run pytest -q -m "not slow and not live"

test-all:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

eval:
	@echo "eval arrives in feat/eval"
