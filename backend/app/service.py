"""Application services shared by HTTP routes and tests."""

from __future__ import annotations

import uuid
from pathlib import Path

from .config import Settings
from .database import Database
from .scanner import ScanLimits, scan_repository


def new_scan_id() -> str:
    return uuid.uuid4().hex


def start_scan(
    database: Database,
    *,
    source_type: str,
    source_name: str,
    source_url: str | None,
) -> str:
    scan_id = new_scan_id()
    database.create_scan(
        scan_id=scan_id,
        source_type=source_type,
        source_name=source_name,
        source_url=source_url,
    )
    return scan_id


def finish_scan(database: Database, settings: Settings, scan_id: str, root: Path) -> dict[str, object]:
    try:
        report = scan_repository(
            root,
            limits=ScanLimits(
                max_files=settings.max_scan_files,
                max_file_bytes=settings.max_scan_file_bytes,
            ),
        )
        database.complete_scan(
            scan_id=scan_id,
            score=report.score,
            grade=report.grade,
            summary=report.summary,
            repository_fingerprint=report.repository_fingerprint,
            findings=[finding.as_dict(index) for index, finding in enumerate(report.findings)],
        )
    except Exception as exc:
        database.fail_scan(scan_id=scan_id, error=str(exc))
        raise
    bundle = database.get_bundle(scan_id)
    if bundle is None:  # pragma: no cover - impossible after create_scan
        raise RuntimeError("Scan disappeared while being finalized")
    return bundle
