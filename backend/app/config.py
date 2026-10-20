"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:  # pragma: no cover - defensive configuration guard
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime limits and storage settings for the backend."""

    database_path: Path
    max_upload_bytes: int = 50 * 1024 * 1024
    max_archive_files: int = 5_000
    max_archive_uncompressed_bytes: int = 500 * 1024 * 1024
    max_scan_files: int = 20_000
    max_scan_file_bytes: int = 2 * 1024 * 1024
    git_timeout_seconds: int = 120
    git_max_repository_bytes: int = 500 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        backend_root = Path(__file__).resolve().parents[1]
        database_path = Path(
            os.getenv("REPOREADY_DATABASE_PATH", str(backend_root / "data" / "repoready.sqlite3"))
        ).expanduser()
        return cls(
            database_path=database_path,
            max_upload_bytes=_positive_int("REPOREADY_MAX_UPLOAD_BYTES", cls.max_upload_bytes),
            max_archive_files=_positive_int("REPOREADY_MAX_ARCHIVE_FILES", cls.max_archive_files),
            max_archive_uncompressed_bytes=_positive_int(
                "REPOREADY_MAX_ARCHIVE_UNCOMPRESSED_BYTES", cls.max_archive_uncompressed_bytes
            ),
            max_scan_files=_positive_int("REPOREADY_MAX_SCAN_FILES", cls.max_scan_files),
            max_scan_file_bytes=_positive_int("REPOREADY_MAX_SCAN_FILE_BYTES", cls.max_scan_file_bytes),
            git_timeout_seconds=_positive_int("REPOREADY_GIT_TIMEOUT_SECONDS", cls.git_timeout_seconds),
            git_max_repository_bytes=_positive_int(
                "REPOREADY_GIT_MAX_REPOSITORY_BYTES", cls.git_max_repository_bytes
            ),
        )
