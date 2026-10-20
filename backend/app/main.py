"""FastAPI entrypoint for the RepoReady repository scanner."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .archive import ArchiveSecurityError, safe_extract_zip, select_repository_root
from .config import Settings
from .database import Database
from .schemas import GitScanRequest
from .security import (
    GitCloneError,
    GitValidationError,
    clone_public_git_repository,
    enforce_repository_size_limits,
    validate_git_ref,
    validate_public_https_git_url,
)
from .service import finish_scan, start_scan


def _source_name(filename: str | None) -> str:
    if not filename:
        return "uploaded-repository.zip"
    name = Path(filename).name.strip()
    return name[:255] or "uploaded-repository.zip"


async def _save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> None:
    written = 0
    try:
        with destination.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise ArchiveSecurityError(f"Upload exceeds the {max_bytes}-byte limit")
                output.write(chunk)
    finally:
        await upload.close()


def _not_found(scan_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Scan '{scan_id}' was not found")


def _comparison(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    base_summary = base.get("summary") or {}
    candidate_summary = candidate.get("summary") or {}
    base_scores = base_summary.get("category_scores", {}) if isinstance(base_summary, dict) else {}
    candidate_scores = candidate_summary.get("category_scores", {}) if isinstance(candidate_summary, dict) else {}
    if not isinstance(base_scores, dict):
        base_scores = {}
    if not isinstance(candidate_scores, dict):
        candidate_scores = {}
    categories = sorted(set(base_scores) | set(candidate_scores))
    category_delta = {
        category: int(candidate_scores.get(category, 0)) - int(base_scores.get(category, 0))
        for category in categories
    }
    base_findings = {
        item["code"]: item
        for item in base.get("findings", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    candidate_findings = {
        item["code"]: item for item in candidate.get("findings", []) if isinstance(item, dict)
    }
    added_codes = sorted(set(candidate_findings) - set(base_findings))
    resolved_codes = sorted(set(base_findings) - set(candidate_findings))
    common_codes = sorted(set(base_findings) & set(candidate_findings))
    comparable_keys = ("category", "severity", "title", "description", "remediation", "evidence")
    changed_codes = [
        code
        for code in common_codes
        if {key: base_findings[code].get(key) for key in comparable_keys}
        != {key: candidate_findings[code].get(key) for key in comparable_keys}
    ]
    return {
        "base_scan_id": base["id"],
        "candidate_scan_id": candidate["id"],
        "score_delta": int(candidate.get("score") or 0) - int(base.get("score") or 0),
        "category_score_delta": category_delta,
        "findings_added": [candidate_findings[code] for code in added_codes],
        "findings_resolved": [base_findings[code] for code in resolved_codes],
        "findings_changed": [candidate_findings[code] for code in changed_codes],
        "findings_unchanged": [
            candidate_findings[code] for code in common_codes if code not in changed_codes
        ],
    }


def _markdown(bundle: dict[str, Any]) -> str:
    summary = bundle.get("summary") or {}
    category_scores = summary.get("category_scores", {}) if isinstance(summary, dict) else {}
    lines = [
        f"# RepoReady scan `{bundle['id']}`",
        "",
        f"- **Source:** {bundle['source_name']}",
        f"- **Type:** {bundle['source_type']}",
        f"- **Status:** {bundle['status']}",
        f"- **Score:** {bundle.get('score', 'n/a')} ({bundle.get('grade', 'n/a')})",
        f"- **Created:** {bundle['created_at']}",
        "",
        "## Category scores",
        "",
        "| Category | Score |",
        "| --- | ---: |",
    ]
    for category in sorted(category_scores):
        lines.append(f"| {category.title()} | {category_scores[category]} |")
    lines.extend(["", "## Findings", ""])
    findings = bundle.get("findings", [])
    if not findings:
        lines.append("No findings.")
    else:
        for finding in findings:
            lines.extend(
                [
                    f"### [{finding['severity'].upper()}] {finding['title']}",
                    "",
                    finding["description"],
                ]
            )
            if finding.get("remediation"):
                lines.append(f"\n**Remediation:** {finding['remediation']}")
            evidence = finding.get("evidence", [])
            if evidence:
                lines.extend(["", "Evidence:"])
                for item in evidence:
                    location = item.get("path", ".")
                    detail = item.get("detail", "")
                    lines.append(f"- `{location}` — {detail}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _dashboard(database: Database) -> dict[str, object]:
    """Build dashboard data from persisted scans only.

    The dashboard intentionally returns empty metrics when there are no completed
    scans. This keeps the UI honest and makes the endpoint useful for both the
    production app and empty-state tests.
    """

    rows = database.list_scans(limit=100, offset=0)
    bundles = [database.get_bundle(row["id"]) for row in rows]
    bundles = [bundle for bundle in bundles if bundle is not None]
    completed = [bundle for bundle in bundles if bundle.get("status") == "complete"]

    recent_scans: list[dict[str, object]] = []
    repositories_by_name: dict[str, dict[str, object]] = {}
    total_findings = 0
    critical_count = 0
    high_count = 0

    for bundle in bundles:
        findings = bundle.get("findings", [])
        findings = findings if isinstance(findings, list) else []
        total_findings += len(findings)
        critical_count += sum(1 for finding in findings if finding.get("severity") == "critical")
        high_count += sum(1 for finding in findings if finding.get("severity") == "high")
    for bundle in bundles[:8]:
        findings = bundle.get("findings", [])
        findings = findings if isinstance(findings, list) else []
        status_value = str(bundle.get("status", "failed"))
        recent_scans.append(
            {
                "id": bundle["id"],
                "repository": bundle.get("source_name", "Repository"),
                "branch": "default",
                "status": status_value,
                "score": bundle.get("score"),
                "findings": len(findings),
                "critical": sum(1 for finding in findings if finding.get("severity") == "critical"),
                "startedAt": bundle.get("created_at"),
                "completedAt": bundle.get("completed_at"),
                "source": str(bundle.get("source_type", "repository")).title(),
                "progress": 100 if status_value == "complete" else 0,
            }
        )
        name = str(bundle.get("source_name", "Repository"))
        if name not in repositories_by_name:
            repositories_by_name[name] = {
                "id": name,
                "name": name,
                "provider": str(bundle.get("source_type", "repository")).title(),
                "branch": "default",
                "lastScanAt": bundle.get("completed_at") or bundle.get("created_at"),
                "score": bundle.get("score"),
                "status": status_value,
            }

    metrics: list[dict[str, object]] = []
    if completed:
        scored = [bundle["score"] for bundle in completed if isinstance(bundle.get("score"), int)]
        average_score = round(sum(scored) / len(scored)) if scored else None
        metrics = [
            {
                "id": "repositories",
                "label": "Repositories analyzed",
                "value": len(repositories_by_name),
                "detail": f"{len(completed)} completed scan{'s' if len(completed) != 1 else ''}",
                "trend": "flat",
                "trendLabel": "from stored results",
            },
            {
                "id": "findings",
                "label": "Findings detected",
                "value": total_findings,
                "detail": f"{critical_count} critical · {high_count} high",
                "trend": "flat",
                "trendLabel": "from stored results",
            },
            {
                "id": "score",
                "label": "Average readiness score",
                "value": f"{average_score}/100" if average_score is not None else "—",
                "detail": "Completed scans only",
                "trend": "flat",
                "trendLabel": "from stored results",
            },
            {
                "id": "latest",
                "label": "Latest scan status",
                "value": str(completed[0].get("status", "unknown")).title(),
                "detail": str(completed[0].get("source_name", "Repository")),
                "trend": "flat",
                "trendLabel": "most recent",
            },
        ]

    return {
        "metrics": metrics,
        "recentScans": recent_scans,
        "repositories": list(repositories_by_name.values())[:8],
        "generatedAt": rows[0].get("created_at") if rows else None,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    database = Database(settings.database_path)
    app = FastAPI(
        title="RepoReady Backend",
        version="1.0.0",
        description="Deterministic repository readiness scanning API.",
    )
    app.state.settings = settings
    app.state.database = database

    @app.get("/health")
    def health() -> dict[str, object]:
        try:
            database_ok = database.health()
        except Exception:
            database_ok = False
        return {
            "status": "ok" if database_ok else "degraded",
            "database": "ok" if database_ok else "error",
            "scanner_version": "2026.10.1",
        }

    @app.get("/dashboard")
    def dashboard() -> dict[str, object]:
        return _dashboard(database)

    @app.post("/scans/upload", status_code=status.HTTP_201_CREATED)
    async def scan_upload(
        archive: UploadFile | None = File(default=None),
        file: UploadFile | None = File(default=None),
    ) -> dict[str, object]:
        upload = archive or file
        if upload is None:
            raise HTTPException(status_code=400, detail="Upload a ZIP archive in the 'archive' or 'file' field")
        scan_id = start_scan(
            database,
            source_type="upload",
            source_name=_source_name(upload.filename),
            source_url=None,
        )
        try:
            with tempfile.TemporaryDirectory(prefix="repoready-upload-") as temporary_directory:
                temporary_root = Path(temporary_directory)
                archive_path = temporary_root / "repository.zip"
                await _save_upload(upload, archive_path, settings.max_upload_bytes)
                extracted_path = temporary_root / "extracted"
                await run_in_threadpool(
                    safe_extract_zip,
                    archive_path,
                    extracted_path,
                    max_files=settings.max_archive_files,
                    max_uncompressed_bytes=settings.max_archive_uncompressed_bytes,
                )
                repository_root = select_repository_root(extracted_path)
                return await run_in_threadpool(finish_scan, database, settings, scan_id, repository_root)
        except (ArchiveSecurityError, ValueError) as exc:
            database.fail_scan(scan_id=scan_id, error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            database.fail_scan(scan_id=scan_id, error=str(exc))
            raise HTTPException(status_code=500, detail="Repository scan failed") from exc

    @app.post("/scans/{scan_id}/rerun", status_code=status.HTTP_201_CREATED)
    def rerun_scan(scan_id: str) -> dict[str, object]:
        previous = database.get_bundle(scan_id)
        if previous is None:
            raise _not_found(scan_id)
        if previous.get("source_type") != "git" or not previous.get("source_url"):
            raise HTTPException(
                status_code=409,
                detail="Uploaded scans cannot be rerun because repository contents are not retained; upload the ZIP again",
            )
        new_id: str | None = None
        try:
            safe_url = validate_public_https_git_url(str(previous["source_url"]))
            new_id = start_scan(
                database,
                source_type="git",
                source_name=str(previous.get("source_name", "repository")),
                source_url=safe_url,
            )
            with tempfile.TemporaryDirectory(prefix="repoready-rerun-") as temporary_directory:
                repository_root = Path(temporary_directory) / "repository"
                clone_public_git_repository(
                    safe_url,
                    repository_root,
                    ref=None,
                    timeout_seconds=settings.git_timeout_seconds,
                )
                enforce_repository_size_limits(
                    repository_root,
                    max_bytes=settings.git_max_repository_bytes,
                    max_files=settings.max_scan_files,
                )
                return finish_scan(database, settings, new_id, repository_root)
        except GitValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except GitCloneError as exc:
            if new_id:
                database.fail_scan(scan_id=new_id, error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            if new_id:
                database.fail_scan(scan_id=new_id, error=str(exc))
            raise HTTPException(status_code=500, detail="Repository rerun failed") from exc

    @app.post("/scans/git", status_code=status.HTTP_201_CREATED)
    def scan_git(request: GitScanRequest) -> dict[str, object]:
        try:
            safe_url = validate_public_https_git_url(request.url)
            safe_ref = validate_git_ref(request.ref)
        except GitValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        scan_id = start_scan(
            database,
            source_type="git",
            source_name=safe_url.rsplit("/", 1)[-1] or safe_url,
            source_url=safe_url,
        )
        try:
            with tempfile.TemporaryDirectory(prefix="repoready-git-") as temporary_directory:
                repository_root = Path(temporary_directory) / "repository"
                clone_public_git_repository(
                    safe_url,
                    repository_root,
                    ref=safe_ref,
                    timeout_seconds=settings.git_timeout_seconds,
                )
                enforce_repository_size_limits(
                    repository_root,
                    max_bytes=settings.git_max_repository_bytes,
                    max_files=settings.max_scan_files,
                )
                bundle = finish_scan(database, settings, scan_id, repository_root)
                return bundle
        except GitValidationError as exc:
            database.fail_scan(scan_id=scan_id, error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except GitCloneError as exc:
            database.fail_scan(scan_id=scan_id, error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            database.fail_scan(scan_id=scan_id, error=str(exc))
            raise HTTPException(status_code=500, detail="Repository scan failed") from exc

    @app.get("/scans/compare")
    def compare_scans(
        base_id: str = Query(min_length=1, max_length=64),
        candidate_id: str = Query(min_length=1, max_length=64),
    ) -> dict[str, object]:
        base = database.get_bundle(base_id)
        candidate = database.get_bundle(candidate_id)
        if base is None:
            raise _not_found(base_id)
        if candidate is None:
            raise _not_found(candidate_id)
        return _comparison(base, candidate)

    @app.get("/scans")
    def list_scan_history(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        return {"items": database.list_scans(limit=limit, offset=offset), "limit": limit, "offset": offset}

    @app.get("/scans/{scan_id}")
    def get_scan(scan_id: str) -> dict[str, object]:
        bundle = database.get_bundle(scan_id)
        if bundle is None:
            raise _not_found(scan_id)
        return bundle

    @app.delete("/scans/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_scan(scan_id: str) -> Response:
        if not database.delete_scan(scan_id):
            raise _not_found(scan_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/scans/{scan_id}/findings")
    def get_findings(scan_id: str) -> dict[str, object]:
        bundle = database.get_bundle(scan_id)
        if bundle is None:
            raise _not_found(scan_id)
        return {"scan_id": scan_id, "findings": bundle["findings"]}

    @app.get("/scans/{scan_id}/compare/{other_id}")
    def compare_scan_path(scan_id: str, other_id: str) -> dict[str, object]:
        base = database.get_bundle(scan_id)
        candidate = database.get_bundle(other_id)
        if base is None:
            raise _not_found(scan_id)
        if candidate is None:
            raise _not_found(other_id)
        return _comparison(base, candidate)

    @app.get("/scans/{scan_id}/export/json")
    def export_json(scan_id: str) -> Response:
        bundle = database.get_bundle(scan_id)
        if bundle is None:
            raise _not_found(scan_id)
        payload = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{scan_id}.json"'},
        )

    @app.get("/scans/{scan_id}/export/markdown")
    def export_markdown(scan_id: str) -> Response:
        bundle = database.get_bundle(scan_id)
        if bundle is None:
            raise _not_found(scan_id)
        return Response(
            content=_markdown(bundle),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{scan_id}.md"'},
        )

    return app


app = create_app()
