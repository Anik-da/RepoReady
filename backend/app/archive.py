"""Safe ZIP handling with traversal, symlink, and decompression limits."""

from __future__ import annotations

import ntpath
import posixpath
import stat
import zipfile
from pathlib import Path, PurePosixPath


class ArchiveSecurityError(ValueError):
    """Raised when an archive violates extraction safety constraints."""


def _safe_member_path(name: str) -> PurePosixPath | None:
    if not name or "\x00" in name:
        raise ArchiveSecurityError("Archive contains an invalid member name")
    normalized_name = name.replace("\\", "/")
    drive, _ = ntpath.splitdrive(normalized_name)
    if drive or normalized_name.startswith("/"):
        raise ArchiveSecurityError("Archive contains an absolute path")
    normalized = posixpath.normpath(normalized_name)
    if normalized in ("", "."):
        return None
    if normalized == ".." or normalized.startswith("../"):
        raise ArchiveSecurityError("Archive contains a path traversal entry")
    return PurePosixPath(normalized)


def safe_extract_zip(
    archive_path: Path,
    destination: Path,
    *,
    max_files: int = 5_000,
    max_uncompressed_bytes: int = 500 * 1024 * 1024,
) -> Path:
    """Extract a ZIP into ``destination`` and return the destination path."""

    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if not zipfile.is_zipfile(archive_path):
        raise ArchiveSecurityError("Uploaded file is not a valid ZIP archive")
    seen: set[str] = set()
    actual_bytes = 0
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveSecurityError("Could not read ZIP archive") from exc
    with archive:
        members = archive.infolist()
        if len(members) > max_files:
            raise ArchiveSecurityError(f"Archive contains more than {max_files} entries")
        for info in members:
            member_path = _safe_member_path(info.filename)
            if member_path is None:
                continue
            key = member_path.as_posix()
            if key in seen:
                raise ArchiveSecurityError("Archive contains duplicate paths")
            seen.add(key)
            mode = (info.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(mode):
                raise ArchiveSecurityError("Archive symlinks are not allowed")
            target = (destination / Path(*member_path.parts)).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise ArchiveSecurityError("Archive path escapes extraction directory") from exc
            is_directory = info.is_dir() or info.filename.endswith(("/", "\\"))
            if is_directory:
                try:
                    target.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise ArchiveSecurityError("Archive contains a file/directory collision") from exc
                continue
            if info.file_size > max_uncompressed_bytes - actual_bytes:
                raise ArchiveSecurityError("Archive exceeds the uncompressed size limit")
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("xb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        actual_bytes += len(chunk)
                        if actual_bytes > max_uncompressed_bytes:
                            raise ArchiveSecurityError("Archive exceeds the uncompressed size limit")
                        output.write(chunk)
            except (FileExistsError, IsADirectoryError, NotADirectoryError) as exc:
                raise ArchiveSecurityError("Archive contains a file/directory collision") from exc
    return destination


def select_repository_root(extracted_root: Path) -> Path:
    """Unwrap the common single top-level directory produced by ZIP tools."""

    current = extracted_root.resolve()
    for _ in range(5):
        entries = sorted(current.iterdir(), key=lambda item: item.name)
        if len(entries) != 1 or not entries[0].is_dir() or entries[0].is_symlink():
            break
        current = entries[0]
    return current
