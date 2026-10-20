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


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_FILES = 5_000
DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
DEFAULT_MAX_SCAN_FILES = 20_000
DEFAULT_MAX_SCAN_FILE_BYTES = 2 * 1024 * 1024
DEFAULT_GIT_TIMEOUT_SECONDS = 120
DEFAULT_GIT_MAX_REPOSITORY_BYTES = 500 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime limits and storage settings for the backend."""

    database_path: Path
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_archive_files: int = DEFAULT_MAX_ARCHIVE_FILES
    max_archive_uncompressed_bytes: int = DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES
    max_scan_files: int = DEFAULT_MAX_SCAN_FILES
    max_scan_file_bytes: int = DEFAULT_MAX_SCAN_FILE_BYTES
    git_timeout_seconds: int = DEFAULT_GIT_TIMEOUT_SECONDS
    git_max_repository_bytes: int = DEFAULT_GIT_MAX_REPOSITORY_BYTES

    @classmethod
    def from_env(cls) -> "Settings":
        backend_root = Path(__file__).resolve().parents[1]
        database_path = Path(
            os.getenv("REPOREADY_DATABASE_PATH", str(backend_root / "data" / "repoready.sqlite3"))
        ).expanduser()
        return cls(
            database_path=database_path,
            max_upload_bytes=_positive_int("REPOREADY_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES),
            max_archive_files=_positive_int("REPOREADY_MAX_ARCHIVE_FILES", DEFAULT_MAX_ARCHIVE_FILES),
            max_archive_uncompressed_bytes=_positive_int(
                "REPOREADY_MAX_ARCHIVE_UNCOMPRESSED_BYTES", DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES
            ),
            max_scan_files=_positive_int("REPOREADY_MAX_SCAN_FILES", DEFAULT_MAX_SCAN_FILES),
            max_scan_file_bytes=_positive_int("REPOREADY_MAX_SCAN_FILE_BYTES", DEFAULT_MAX_SCAN_FILE_BYTES),
            git_timeout_seconds=_positive_int("REPOREADY_GIT_TIMEOUT_SECONDS", DEFAULT_GIT_TIMEOUT_SECONDS),
            git_max_repository_bytes=_positive_int(
                "REPOREADY_GIT_MAX_REPOSITORY_BYTES", DEFAULT_GIT_MAX_REPOSITORY_BYTES
            ),
        )
