.PHONY: setup test build backend-test frontend-test run-backend run-frontend

PYTHON ?= backend/.venv/bin/python
NPM ?= npm

setup:
	python3.11 -m venv backend/.venv
	$(PYTHON) -m pip install --requirement backend/requirements.lock
	$(NPM) --prefix frontend ci

backend-test:
	$(PYTHON) -m pytest -q backend/tests

frontend-test:
	$(NPM) --prefix frontend test

test: backend-test frontend-test

build:
	$(NPM) --prefix frontend run build
	$(PYTHON) -m compileall -q backend/app backend/tests

run-backend:
	$(PYTHON) -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000

run-frontend:
	$(NPM) --prefix frontend run dev
