from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

import pytest

import app.main as main_module


def _zip_directory(directory: Path, top_level: str = "repository") -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(directory.rglob("*")):
            if file.is_file():
                archive.write(file, f"{top_level}/{file.relative_to(directory).as_posix()}")
    return payload.getvalue()


def _upload(client, fixture: Path):
    return client.post(
        "/scans/upload",
        files={
            "archive": (
                f"{fixture.name}.zip",
                _zip_directory(fixture),
                "application/zip",
            )
        },
    )


def test_health_and_upload_persist_findings_and_exports(client, fixture_root: Path):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["database"] == "ok"

    response = _upload(client, fixture_root / "complete_repo")
    assert response.status_code == 201, response.text
    bundle = response.json()
    scan_id = bundle["id"]
    assert bundle["status"] == "complete"
    assert bundle["source_type"] == "upload"
    assert bundle["score"] == 94
    assert bundle["summary"]["category_scores"]["tests"] == 100
    assert any(item["code"] == "tests.detected" for item in bundle["findings"])

    detail = client.get(f"/scans/{scan_id}")
    assert detail.status_code == 200
    assert detail.json()["repository_fingerprint"] == bundle["repository_fingerprint"]

    findings = client.get(f"/scans/{scan_id}/findings")
    assert findings.status_code == 200
    assert len(findings.json()["findings"]) == len(bundle["findings"])

    json_export = client.get(f"/scans/{scan_id}/export/json")
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    assert json_export.json()["id"] == scan_id

    markdown_export = client.get(f"/scans/{scan_id}/export/markdown")
    assert markdown_export.status_code == 200
    assert f"# RepoReady scan `{scan_id}`" in markdown_export.text
    assert "## Category scores" in markdown_export.text

    history = client.get("/scans")
    assert history.status_code == 200
    assert history.json()["items"][0]["id"] == scan_id

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    dashboard_body = dashboard.json()
    assert dashboard_body["metrics"]
    assert dashboard_body["recentScans"][0]["id"] == scan_id
    assert dashboard_body["recentScans"][0]["score"] == 94


def test_history_comparison_reports_score_and_finding_changes(client, fixture_root: Path):
    complete = _upload(client, fixture_root / "complete_repo")
    minimal = _upload(client, fixture_root / "minimal_repo")
    assert complete.status_code == minimal.status_code == 201
    base_id = complete.json()["id"]
    candidate_id = minimal.json()["id"]

    comparison = client.get(
        "/scans/compare",
        params={"base_id": base_id, "candidate_id": candidate_id},
    )
    assert comparison.status_code == 200
    body = comparison.json()
    assert body["score_delta"] == -94
    assert body["category_score_delta"]["tests"] == -100
    assert any(item["code"] == "tests.missing" for item in body["findings_added"])
    assert any(item["code"] == "tests.detected" for item in body["findings_resolved"])

    path_comparison = client.get(f"/scans/{base_id}/compare/{candidate_id}")
    assert path_comparison.status_code == 200
    assert path_comparison.json()["score_delta"] == -94


def test_invalid_archive_is_recorded_as_failed_scan(client):
    response = client.post(
        "/scans/upload",
        files={"archive": ("broken.zip", b"not a zip", "application/zip")},
    )
    assert response.status_code == 400
    history = client.get("/scans").json()["items"]
    assert history[0]["status"] == "failed"
    assert history[0]["error"]


def test_upload_accepts_conventional_file_field(client, fixture_root: Path):
    response = client.post(
        "/scans/upload",
        files={"file": ("minimal.zip", _zip_directory(fixture_root / "minimal_repo"), "application/zip")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "complete"


def test_invalid_git_url_is_rejected_without_clone(client):
    response = client.post("/scans/git", json={"url": "http://github.com/example/repo.git"})
    assert response.status_code == 400
    assert "HTTPS" in response.json()["detail"]
    assert client.get("/scans").json()["items"] == []


def test_git_scan_uses_guarded_clone_and_persists_result(
    client, fixture_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    def fake_clone(url: str, destination: Path, *, ref: str | None, timeout_seconds: int):
        assert url == "https://example.com/repo.git"
        assert ref == "main"
        assert timeout_seconds == 5
        shutil.copytree(fixture_root / "minimal_repo", destination)

    monkeypatch.setattr(main_module, "clone_public_git_repository", fake_clone)
    response = client.post(
        "/scans/git",
        json={"url": "https://example.com/repo.git", "ref": "main"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["source_type"] == "git"
    assert response.json()["status"] == "complete"


def test_missing_scan_returns_404(client):
    assert client.get("/scans/does-not-exist").status_code == 404
    assert client.get("/scans/does-not-exist/export/json").status_code == 404
