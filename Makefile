.PHONY: install install-ml test test-all lint format eval eval-full ablations serve

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
	uv run python eval/run_eval.py --mode fast

eval-full:
	uv run --extra ml python eval/run_eval.py --mode full

ablations:
	uv run --extra ml python eval/run_ablations.py --mode full

serve:
	uv run uvicorn --factory guardbank.api:serve_app --port 8000
