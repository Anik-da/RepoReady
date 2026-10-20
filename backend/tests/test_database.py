from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database import Database


def test_legacy_findings_schema_is_migrated_to_support_critical(tmp_path: Path):
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE scans (
            id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_url TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            score INTEGER,
            grade TEXT,
            summary_json TEXT NOT NULL DEFAULT '{}',
            repository_fingerprint TEXT,
            error TEXT
        );
        CREATE TABLE findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT NOT NULL,
            code TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high')),
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            remediation TEXT,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            sort_order INTEGER NOT NULL DEFAULT 0,
            UNIQUE(scan_id, code)
        );
        CREATE INDEX idx_findings_scan_order ON findings(scan_id, sort_order, id);
        """
    )
    connection.close()

    database = Database(path)
    database.create_scan(scan_id="scan", source_type="upload", source_name="repo.zip", source_url=None)
    database.complete_scan(
        scan_id="scan",
        score=1,
        grade="F",
        summary={"finding_counts": {"critical": 1}},
        repository_fingerprint="fingerprint",
        findings=[
            {
                "code": "environment.secret",
                "category": "environment",
                "severity": "critical",
                "title": "Secret",
                "description": "Redacted",
                "evidence": [],
            }
        ],
    )

    bundle = database.get_bundle("scan")
    assert bundle is not None
    assert bundle["findings"][0]["severity"] == "critical"
