.PHONY: test run

PYTHON ?= .venv/bin/python

test:
	$(PYTHON) -m pytest -q

run:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000
