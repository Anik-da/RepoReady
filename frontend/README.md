# RepoReady frontend

RepoReady is a dark, developer-tool workspace for importing repositories, following scan progress, reviewing findings, comparing scan history, and exporting reports.

## Requirements

- Node.js `22.23.3` (see `.nvmrc`)
- npm 10+

## Setup

```bash
npm ci
```

The UI uses `/api` by default. Point it at a running backend with `VITE_API_BASE_URL` when needed:

```bash
VITE_API_BASE_URL=http://localhost:8000/api npm run dev
```

## Run

```bash
npm run dev
```

Open `http://localhost:5173`.

## Test

```bash
npm test
```

The Vitest + React Testing Library suite covers loading, empty, error, successful API responses, primary navigation, and the API-unavailable fallback state.

## Production build

```bash
npm run build
npm run preview
```

## Docker

```bash
docker run --rm -p 8080:80 repoready-frontend
```

## API integration points

The client keeps the API boundary in `src/lib/api.ts` and currently expects:

- `GET /dashboard` (optional aggregate endpoint; the UI derives dashboard data from `/scans` when it is not available)
- `GET /scans?limit=100` for history
- `POST /scans/git` with `{ url, ref }`
- `POST /scans/upload` with multipart `file` and optional `branch`
- `GET /scans/:id`
- `GET /scans/compare?base_id=:id&candidate_id=:id`
- `GET /scans/:id/export/json`
- `GET /scans/:id/export/markdown`

Network errors and unavailable gateway responses show a recoverable error state. A successful API response with empty arrays remains empty in the UI; the client does not invent metrics or reports when the API is unavailable.
