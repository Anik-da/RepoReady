from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from app.archive import ArchiveSecurityError, safe_extract_zip, select_repository_root


def _write_zip(path: Path, entries: list[tuple[str, bytes, int | None]]):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data, mode in entries:
            info = ZipInfo(name)
            info.compress_type = ZIP_DEFLATED
            if mode is not None:
                info.external_attr = mode << 16
            archive.writestr(info, data)


def test_safe_zip_extracts_nested_repository_and_unwraps_root(tmp_path: Path):
    archive_path = tmp_path / "repo.zip"
    _write_zip(archive_path, [("project/README.md", b"hello", None)])

    extracted = safe_extract_zip(archive_path, tmp_path / "extracted")

    root = select_repository_root(extracted)
    assert root.name == "project"
    assert (root / "README.md").read_text(encoding="utf-8") == "hello"


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "C:\\outside.txt", "folder/../../outside.txt"])
def test_safe_zip_rejects_traversal_and_absolute_paths(tmp_path: Path, name: str):
    archive_path = tmp_path / "unsafe.zip"
    _write_zip(archive_path, [(name, b"nope", None)])

    with pytest.raises(ArchiveSecurityError):
        safe_extract_zip(archive_path, tmp_path / "extracted")


def test_safe_zip_rejects_symlinks(tmp_path: Path):
    archive_path = tmp_path / "symlink.zip"
    _write_zip(archive_path, [("link", b"target", 0o120777)])

    with pytest.raises(ArchiveSecurityError, match="symlinks"):
        safe_extract_zip(archive_path, tmp_path / "extracted")


def test_safe_zip_enforces_uncompressed_limit(tmp_path: Path):
    archive_path = tmp_path / "large.zip"
    _write_zip(archive_path, [("large.txt", b"x" * 100, None)])

    with pytest.raises(ArchiveSecurityError, match="uncompressed size"):
        safe_extract_zip(archive_path, tmp_path / "extracted", max_uncompressed_bytes=10)


def test_safe_zip_rejects_file_directory_collisions(tmp_path: Path):
    archive_path = tmp_path / "collision.zip"
    _write_zip(archive_path, [("same", b"file", None), ("same/child.txt", b"child", None)])

    with pytest.raises(ArchiveSecurityError, match="collision"):
        safe_extract_zip(archive_path, tmp_path / "extracted")
