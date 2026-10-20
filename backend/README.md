# RepoReady Backend

FastAPI service for deterministic repository-readiness scans.

## Local setup

The backend targets Python 3.11. Create the project-local environment and install
the pinned dependencies:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.txt
```

The service creates a SQLite database at `data/repoready.sqlite3` by default.
Set `REPOREADY_DATABASE_PATH` to use another path. Runtime limits are configurable
with the `REPOREADY_*` environment variables in `app/config.py`.

## Run

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health is available at `GET /health`. Upload a ZIP at `POST /scans/upload` or
submit a public HTTPS Git URL at `POST /scans/git`.

## Test

```bash
make test
```

The test suite is offline after dependencies are installed and uses synthetic
repositories under `tests/fixtures`.

## Docker

```bash
docker build -t repoready-backend .
docker run --rm -p 8000:8000 -v "$PWD/data:/app/data" repoready-backend
```

## API outline

- `GET /health`
- `POST /scans/upload`
- `POST /scans/git`
- `GET /scans`
- `GET /scans/{scan_id}`
- `GET /scans/{scan_id}/findings`
- `GET /scans/compare?base_id=...&candidate_id=...`
- `GET /scans/{scan_id}/export/json`
- `GET /scans/{scan_id}/export/markdown`
