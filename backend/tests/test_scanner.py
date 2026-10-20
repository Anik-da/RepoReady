from __future__ import annotations

from pathlib import Path

from app.scanner import ScanLimits, ScanLimitError, scan_repository


def test_complete_fixture_has_evidence_and_expected_scores(fixture_root: Path):
    report = scan_repository(fixture_root / "complete_repo")

    assert report.score == 94
    assert report.grade == "A"
    assert report.category_scores == {
        "dependencies": 100,
        "environment": 100,
        "tests": 100,
        "docker": 100,
        "documentation": 70,
    }
    assert {finding.code for finding in report.findings} >= {
        "dependencies.manifest_detected",
        "environment.template_detected",
        "tests.detected",
        "docker.configuration_detected",
        "documentation.detected",
    }
    test_finding = next(finding for finding in report.findings if finding.code == "tests.detected")
    assert test_finding.evidence[0].path == "tests/test_smoke.py"


def test_minimal_fixture_reports_missing_categories(fixture_root: Path):
    report = scan_repository(fixture_root / "minimal_repo")

    assert report.score == 0
    assert report.grade == "F"
    assert {finding.code for finding in report.findings} == {
        "dependencies.manifest_missing",
        "environment.template_missing",
        "tests.missing",
        "docker.configuration_missing",
        "documentation.missing",
    }
    assert all(finding.evidence for finding in report.findings)


def test_scans_are_deterministic_and_ignore_generated_directories(tmp_path: Path, fixture_root: Path):
    repository = tmp_path / "repo"
    repository.mkdir()
    for source in (fixture_root / "complete_repo").rglob("*"):
        if source.is_file():
            target = repository / source.relative_to(fixture_root / "complete_repo")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    generated = repository / "node_modules" / "ignored.js"
    generated.parent.mkdir()
    generated.write_text("ignored", encoding="utf-8")

    first = scan_repository(repository)
    second = scan_repository(repository)

    assert first.repository_fingerprint == second.repository_fingerprint
    assert first.summary == second.summary
    assert [finding.as_dict() for finding in first.findings] == [
        finding.as_dict() for finding in second.findings
    ]
    assert first.file_count == 8


def test_scan_file_limit_is_enforced(tmp_path: Path):
    for index in range(3):
        (tmp_path / f"file-{index}.txt").write_text(str(index), encoding="utf-8")

    try:
        scan_repository(tmp_path, limits=ScanLimits(max_files=2))
    except ScanLimitError as exc:
        assert "more than 2 files" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("expected ScanLimitError")
