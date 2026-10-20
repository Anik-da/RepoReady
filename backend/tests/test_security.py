from __future__ import annotations

from typing import Any
from pathlib import Path

import pytest

import app.security as security
from app.security import (
    GitCloneError,
    GitValidationError,
    clone_public_git_repository,
    enforce_repository_size_limits,
    validate_git_ref,
    validate_public_https_git_url,
)


def test_public_https_git_url_is_normalized():
    assert validate_public_https_git_url("HTTPS://GitHub.com/example/project.git") == (
        "https://github.com/example/project.git"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/project.git",
        "https://user:password@github.com/example/project.git",
        "https://127.0.0.1/example/project.git",
        "https://github.com:8443/example/project.git",
        "https://localhost/example/project.git",
        "https://github.com/example/project.git?token=secret",
        "https://github.com/../project.git",
        "https://github.com/",
    ],
)
def test_git_url_rejects_unsafe_inputs(url: str):
    with pytest.raises(GitValidationError):
        validate_public_https_git_url(url)


@pytest.mark.parametrize("ref", ["-c core.sshCommand=evil", "../main", "main..bad", "main//bad"])
def test_git_ref_rejects_option_or_path_injection(ref: str):
    with pytest.raises(GitValidationError):
        validate_git_ref(ref)


def test_cloned_repository_size_limit_is_enforced(tmp_path: Path):
    (tmp_path / "large.bin").write_bytes(b"x" * 20)

    with pytest.raises(GitCloneError, match="byte limit"):
        enforce_repository_size_limits(tmp_path, max_bytes=10, max_files=10)


def test_git_clone_is_shallow_noninteractive_and_shell_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(security, "assert_resolves_to_public_host", lambda url: None)
    monkeypatch.setattr(security.subprocess, "run", fake_run)
    destination = tmp_path / "repo"
    clone_public_git_repository(
        "https://example.com/repo.git",
        destination,
        ref="main",
        timeout_seconds=7,
    )

    command = captured["command"]
    assert command[:6] == ["git", "clone", "--depth", "1", "--no-tags", "--single-branch"]
    assert "--branch" in command
    assert command[-2:] == ["https://example.com/repo.git", str(destination.resolve())]
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"]["timeout"] == 7
    assert captured["kwargs"]["env"]["GIT_TERMINAL_PROMPT"] == "0"
