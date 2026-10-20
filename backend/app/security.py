"""Validation and subprocess safeguards for public Git sources."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


class GitValidationError(ValueError):
    """Raised when a Git source is not an allowed public HTTPS URL."""


class GitCloneError(RuntimeError):
    """Raised when a guarded Git clone fails."""


_LOCAL_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
}
_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    return address.is_global and not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def validate_public_https_git_url(url: str) -> str:
    """Validate and normalize a public HTTPS Git URL.

    Userinfo, query strings, fragments, non-HTTPS schemes, non-default ports,
    and hosts that are clearly local/private are rejected before Git is invoked.
    """

    if not isinstance(url, str) or not url or len(url) > 2_048:
        raise GitValidationError("Git URL must be a non-empty string under 2,048 characters")
    if any(ord(character) < 32 for character in url):
        raise GitValidationError("Git URL contains control characters")
    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        raise GitValidationError("Only HTTPS Git URLs are allowed")
    if parts.username or parts.password:
        raise GitValidationError("Git URLs with credentials are not allowed")
    if parts.query or parts.fragment:
        raise GitValidationError("Git URLs may not contain query strings or fragments")
    try:
        port = parts.port
    except ValueError as exc:
        raise GitValidationError("Git URL contains an invalid port") from exc
    if port not in (None, 443):
        raise GitValidationError("Only the default HTTPS port is allowed")
    host = parts.hostname
    if not host:
        raise GitValidationError("Git URL must include a hostname")
    host = host.rstrip(".").lower()
    if any(character.isspace() for character in host) or "\\" in host:
        raise GitValidationError("Git URL contains an invalid hostname")
    if host in _LOCAL_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise GitValidationError("Local and internal Git hosts are not allowed")
    if not _is_public_ip(host):
        raise GitValidationError("Git host must be public")
    if not parts.path or parts.path == "/":
        raise GitValidationError("Git URL must include a repository path")
    if "\\" in parts.path or "\x00" in parts.path:
        raise GitValidationError("Git URL contains an invalid repository path")
    if any(segment in {".", ".."} for segment in parts.path.split("/")):
        raise GitValidationError("Git URL contains an invalid repository path")
    return f"https://{host}{parts.path}"


def validate_git_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    if not isinstance(ref, str) or not _REF_PATTERN.fullmatch(ref):
        raise GitValidationError("Git ref contains unsupported characters")
    if ref.startswith("-") or ref.startswith("/") or ref.endswith("/"):
        raise GitValidationError("Git ref has an invalid boundary")
    if ".." in ref or "@{" in ref or "//" in ref:
        raise GitValidationError("Git ref contains an invalid sequence")
    return ref


def assert_resolves_to_public_host(url: str) -> None:
    """Reject DNS names resolving to non-public addresses when DNS is available."""

    host = urlsplit(url).hostname
    if not host or not _is_public_ip(host):
        raise GitValidationError("Git host must be public")
    try:
        addresses = {
            str(result[4][0])
            for result in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror:
        # Let Git produce the actionable network error for an unresolvable public
        # hostname. This keeps URL validation deterministic and offline-testable.
        return
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise GitValidationError("Git host resolves to a non-public address")


def clone_public_git_repository(
    url: str,
    destination: Path,
    *,
    ref: str | None = None,
    timeout_seconds: int = 120,
) -> None:
    """Clone a public repository with no shell, credentials, or interactive prompts."""

    safe_url = validate_public_https_git_url(url)
    safe_ref = validate_git_ref(ref)
    assert_resolves_to_public_host(safe_url)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--no-tags",
        "--single-branch",
    ]
    if safe_ref:
        command.extend(["--branch", safe_ref])
    command.extend(["--", safe_url, str(destination)])
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "true",
        }
    )
    try:
        result = subprocess.run(
            command,
            cwd=destination.parent,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitCloneError(f"Git clone exceeded the {timeout_seconds}-second timeout") from exc
    except OSError as exc:
        raise GitCloneError("Git executable could not be started") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "clone failed").strip().splitlines()
        message = detail[-1][:500] if detail else "clone failed"
        raise GitCloneError(f"Git clone failed: {message}")


def enforce_repository_size_limits(
    repository_root: Path,
    *,
    max_bytes: int,
    max_files: int,
) -> None:
    """Bound the materialized clone before any repository content is scanned."""

    total_bytes = 0
    file_count = 0
    for directory, directories, filenames in os.walk(repository_root, topdown=True, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name.lower() not in {".git", ".hg", ".svn"}
            and not (Path(directory) / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if path.is_symlink():
                continue
            try:
                size = path.stat().st_size
            except OSError as exc:
                raise GitCloneError("Cloned repository contains an unreadable file") from exc
            file_count += 1
            if file_count > max_files:
                raise GitCloneError(f"Cloned repository contains more than {max_files} files")
            total_bytes += size
            if total_bytes > max_bytes:
                raise GitCloneError(f"Cloned repository exceeds the {max_bytes}-byte limit")
