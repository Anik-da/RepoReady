from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def fixture_root() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def client(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "repoready.sqlite3",
        max_upload_bytes=2 * 1024 * 1024,
        max_archive_files=100,
        max_archive_uncompressed_bytes=4 * 1024 * 1024,
        max_scan_files=1_000,
        max_scan_file_bytes=2 * 1024 * 1024,
        git_timeout_seconds=5,
    )
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client
