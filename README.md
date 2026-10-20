# RepoReady

RepoReady is a local-first repository reproducibility and quality analyzer. It
checks whether a project has the dependency, environment, test, build, Docker,
and documentation signals needed for a predictable clean checkout.

The application is intentionally deterministic. Repository contents are scanned
locally with evidence-based rules; no generative AI API or third-party upload is
required.

## What is included

- React + TypeScript + Vite workspace UI.
- FastAPI service with SQLite scan history.
- ZIP import with path-traversal, symlink, file-count, upload-size, and
  uncompressed-size protections.
- Public HTTPS Git URL validation and guarded shallow cloning.
- Deterministic checks for JavaScript/TypeScript, Python, Rust, Go, Maven, and
  Gradle-style dependency files.
- Environment variable template coverage and conservative secret-like detection
  with redacted evidence.
- Static test readiness checks. Repository tests are **not** run automatically;
  reports say `not_run` unless an isolated execution feature is added later.
- Dockerfile and build-context checks, including broad base-image tags and
  missing `COPY`/`ADD` files.
- README, command-documentation, license, TODO/FIXME, and maintainability checks.
- Readiness score from 0 to 100 with category weights and severity penalties.
- Findings search/filter, finding detail evidence, JSON/Markdown export, history,
  and scan comparison.
- Synthetic fixtures and offline backend/frontend tests.

## Architecture

```text
frontend/       React, TypeScript, Vite, Vitest
backend/app/    FastAPI API, SQLite persistence, scanner and security boundary
backend/tests/  Offline API, archive, security, scanner, and fixture tests
```

The development UI uses `/api` and Vite proxies that path to FastAPI on port
8000. The production image serves the built UI through nginx and proxies `/api`
to the local FastAPI process.

## Requirements

- Node.js `22.23.3` from `.nvmrc`.
- Python `3.11.11` from `.python-version`.
- npm 10 or newer.
- Docker is optional for local development. It is required only for the bundled
  single-container deployment.

## Fresh checkout setup

From the repository root:

```bash
make setup
```

This creates `backend/.venv`, installs the pinned Python dependencies from
`backend/requirements.lock`, and runs `npm ci` using the committed
`frontend/package-lock.json`.

Copy `.env.example` to `.env` only when you need to override the documented
defaults. The default database is `backend/data/repoready.sqlite3`.

## Run locally

Start FastAPI in one terminal:

```bash
make run-backend
```

Start the Vite UI in another:

```bash
make run-frontend
```

Open <http://localhost:5173>. The backend health endpoint is available at
<http://localhost:8000/health>.

The main workflow is:

1. Open **Repositories**.
2. Submit a public HTTPS Git URL or upload a ZIP archive.
3. Review the persisted score and findings.
4. Open a finding for evidence and remediation guidance.
5. Export JSON or Markdown from the report.
6. Use **History** and **Compare** to review later scans.

## Test and build

The required project check is:

```bash
make test
```

It runs the backend pytest suite and frontend Vitest suite offline after setup.
The production frontend bundle and Python compilation check are:

```bash
make build
```

The backend-only check can also be run from its directory:

```bash
cd backend
make test
```

## Docker deployment

Build the reproducible single-container image:

```bash
docker build -t repoready .
```

Run it with a persistent local database:

```bash
docker run --rm -p 8080:8080 -v "$(pwd)/data:/data" repoready
```

Open <http://localhost:8080>. The container health endpoint is
<http://localhost:8080/health>.

The image contains the Vite production bundle, nginx, FastAPI/Uvicorn, Git, and
the pinned Python dependencies. Docker image build/run verification depends on
Docker being installed on the machine performing the check.

## API

FastAPI exposes interactive documentation at `/docs` when the backend is run
directly. The core operations are:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Backend and SQLite health |
| GET | `/dashboard` | Metrics derived from persisted scans |
| POST | `/scans/upload` | Analyze a ZIP upload (`archive` or `file`) |
| POST | `/scans/git` | Validate and analyze a public HTTPS Git URL |
| GET | `/scans` | Paginated scan history |
| GET | `/scans/{id}` | Full persisted report |
| GET | `/scans/{id}/findings` | Findings for one report |
| GET | `/scans/compare?base_id=&candidate_id=` | Finding and score comparison |
| GET | `/scans/{id}/export/json` | JSON report download |
| GET | `/scans/{id}/export/markdown` | Markdown report download |

## Scoring

The score is a weighted summary of the configured static checks:

| Category | Weight |
| --- | ---: |
| Dependencies | 25 |
| Environment | 15 |
| Test readiness | 25 |
| Docker/build readiness | 15 |
| Documentation | 20 |

Category baselines are reduced by documented finding severity penalties in
`backend/app/scanner.py`: critical 45, high 30, medium 15, and low 5 points,
bounded at zero. Informational findings do not reduce a score. Tests and Docker
builds are represented as `not_run`; static detection is never presented as a
successful execution.

The score is not a security certification, a production-readiness guarantee, or
proof that every platform-specific build will succeed.

## Security model and limitations

- Only public HTTPS Git URLs are accepted. Userinfo, non-default ports, local or
  private hosts, fragments, query strings, and unsafe refs are rejected.
- Git clone uses a non-interactive argument list with no shell and a shallow
  checkout. Clone and repository-size limits are enforced.
- ZIP paths are normalized before extraction. Absolute paths, traversal,
  symlinks, file/directory collisions, excessive file counts, and excessive
  uncompressed sizes are rejected.
- Repository scripts are not executed during static analysis.
- Potential secrets are never printed; evidence says only that a secret-like
  assignment was found and gives the file/line.
- Scan workspaces are temporary and cleaned up after each request.
- The scanner ignores common generated/vendor directories and skips binary or
  oversized text files.
- Git cloning requires network access only when the user explicitly requests a
  Git URL scan. ZIP scanning works offline.

## Repository layout and reproducibility files

- `.nvmrc` and `.python-version`: pinned runtime versions.
- `frontend/package-lock.json` and `backend/requirements.lock`: dependency locks.
- `.env.example`: placeholders and safe configuration defaults only.
- `Dockerfile` and `.dockerignore`: reproducible deployment definition.
- `Makefile`: setup, test, build, and run commands.
