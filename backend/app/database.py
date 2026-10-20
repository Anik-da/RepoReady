"""Small SQLite persistence layer for scan records and findings."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('upload', 'git')),
    source_name TEXT NOT NULL,
    source_url TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'complete', 'failed')),
    score INTEGER,
    grade TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}',
    repository_fingerprint TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_scans_created_at ON scans(created_at DESC);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
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

CREATE INDEX IF NOT EXISTS idx_findings_scan_order ON findings(scan_id, sort_order, id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class Database:
    """Connection-per-operation SQLite repository.

    SQLite connections are intentionally short lived. This avoids sharing a connection
    across FastAPI worker threads while retaining WAL mode for concurrent reads.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(SCHEMA)

    def health(self) -> bool:
        with closing(self.connect()) as connection:
            connection.execute("SELECT 1").fetchone()
        return True

    def create_scan(
        self,
        *,
        scan_id: str,
        source_type: str,
        source_name: str,
        source_url: str | None,
    ) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                INSERT INTO scans (
                    id, source_type, source_name, source_url, created_at, status
                ) VALUES (?, ?, ?, ?, ?, 'running')
                """,
                (scan_id, source_type, source_name, source_url, utc_now()),
            )

    def complete_scan(
        self,
        *,
        scan_id: str,
        score: int,
        grade: str,
        summary: dict[str, Any],
        repository_fingerprint: str,
        findings: Iterable[dict[str, Any]],
    ) -> None:
        finding_rows = list(findings)
        with closing(self.connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE scans
                SET completed_at = ?, status = 'complete', score = ?, grade = ?,
                    summary_json = ?, repository_fingerprint = ?, error = NULL
                WHERE id = ?
                """,
                (
                    utc_now(),
                    score,
                    grade,
                    json.dumps(summary, sort_keys=True, separators=(",", ":")),
                    repository_fingerprint,
                    scan_id,
                ),
            )
            connection.execute("DELETE FROM findings WHERE scan_id = ?", (scan_id,))
            connection.executemany(
                """
                INSERT INTO findings (
                    scan_id, code, category, severity, title, description,
                    remediation, evidence_json, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        scan_id,
                        finding["code"],
                        finding["category"],
                        finding["severity"],
                        finding["title"],
                        finding["description"],
                        finding.get("remediation"),
                        json.dumps(finding.get("evidence", []), sort_keys=True, separators=(",", ":")),
                        finding.get("sort_order", index),
                    )
                    for index, finding in enumerate(finding_rows)
                ],
            )
            connection.commit()

    def fail_scan(self, *, scan_id: str, error: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                UPDATE scans
                SET completed_at = ?, status = 'failed', error = ?
                WHERE id = ?
                """,
                (utc_now(), error[:1_000], scan_id),
            )

    def get_scan(self, scan_id: str) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return dict(row) if row else None

    def list_scans(self, *, limit: int, offset: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, source_type, source_name, source_url, created_at,
                       completed_at, status, score, grade, repository_fingerprint, error
                FROM scans
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_findings(self, scan_id: str) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT code, category, severity, title, description,
                       remediation, evidence_json, sort_order
                FROM findings
                WHERE scan_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (scan_id,),
            ).fetchall()
        findings: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["evidence"] = _json_loads(item.pop("evidence_json"), [])
            item.pop("sort_order", None)
            findings.append(item)
        return findings

    def get_bundle(self, scan_id: str) -> dict[str, Any] | None:
        scan = self.get_scan(scan_id)
        if scan is None:
            return None
        summary = _json_loads(scan.pop("summary_json", "{}"), {})
        scan["summary"] = summary
        scan["findings"] = self.list_findings(scan_id)
        return scan
