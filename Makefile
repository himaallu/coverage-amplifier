.PHONY: install test eval-live lint

VENV = .venv
PYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest
RUFF = $(VENV)/bin/ruff
MYPY = $(VENV)/bin/mypy

install:
	uv venv --python 3.12 || python3.12 -m venv $(VENV)
	uv pip install -e ".[dev]" || $(VENV)/bin/pip install -e ".[dev]"
	cd frontend && npm install

lint:
	$(RUFF) check .
	$(RUFF) format --check .
	$(MYPY) backend

test: lint
	$(PYTEST) backend/tests \
		-m "not live" \
		--cov=backend/app/extraction \
		--cov=backend/app/generation \
		--cov=backend/app/verification \
		--cov=backend/app/guardrails \
		--cov-report=term-missing \
		--cov-fail-under=85
	cd frontend && npm test

eval-live:
	$(PYTHON) -m backend.app.evals.runner --live
