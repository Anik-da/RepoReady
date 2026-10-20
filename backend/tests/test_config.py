from __future__ import annotations

from app.config import (
    DEFAULT_GIT_TIMEOUT_SECONDS,
    DEFAULT_MAX_ARCHIVE_FILES,
    DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    DEFAULT_MAX_SCAN_FILE_BYTES,
    DEFAULT_MAX_SCAN_FILES,
    DEFAULT_MAX_UPLOAD_BYTES,
    Settings,
)


def test_settings_from_env_uses_numeric_defaults_with_slots():
    settings = Settings.from_env()

    assert settings.max_upload_bytes == DEFAULT_MAX_UPLOAD_BYTES
    assert settings.max_archive_files == DEFAULT_MAX_ARCHIVE_FILES
    assert settings.max_archive_uncompressed_bytes == DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES
    assert settings.max_scan_files == DEFAULT_MAX_SCAN_FILES
    assert settings.max_scan_file_bytes == DEFAULT_MAX_SCAN_FILE_BYTES
    assert settings.git_timeout_seconds == DEFAULT_GIT_TIMEOUT_SECONDS
