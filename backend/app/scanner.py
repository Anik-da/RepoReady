"""Deterministic repository inventory, evidence, and score calculation."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCANNER_VERSION = "2026.10.1"
CATEGORY_WEIGHTS = {
    "dependencies": 25,
    "environment": 15,
    "tests": 25,
    "docker": 15,
    "documentation": 20,
}

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "coverage",
}

PRIMARY_DEPENDENCY_NAMES = {
    "requirements.txt",
    "requirements.in",
    "pyproject.toml",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
    "environment.yml",
    "environment.yaml",
    "package.json",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "gradle.properties",
    "gemfile",
    "gemfile.lock",
    "composer.json",
    "composer.lock",
    "packages.config",
}

ENV_TEMPLATE_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    "env.example",
    "env.sample",
    "config.example",
    "config.example.json",
    "config.example.yaml",
    "config.example.yml",
}

TEST_FILE_SUFFIXES = (
    "_test.py",
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
    "_test.go",
    ".spec.rb",
)

LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".fs": "F#",
    ".swift": "Swift",
}


class ScanLimitError(ValueError):
    """Raised when a repository exceeds configured scanning limits."""


@dataclass(frozen=True, slots=True)
class ScanLimits:
    max_files: int = 20_000
    max_file_bytes: int = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RepositoryFile:
    path: str
    absolute_path: Path
    size: int
    content_sha256: str | None


@dataclass(frozen=True, slots=True)
class Evidence:
    path: str
    detail: str
    line: int | None = None

    def as_dict(self) -> dict[str, str | int | None]:
        return {"path": self.path, "detail": self.detail, "line": self.line}


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    category: str
    severity: str
    title: str
    description: str
    remediation: str | None
    evidence: tuple[Evidence, ...]

    def as_dict(self, sort_order: int = 0) -> dict[str, object]:
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "remediation": self.remediation,
            "evidence": [item.as_dict() for item in self.evidence],
            "sort_order": sort_order,
        }


@dataclass(frozen=True, slots=True)
class ScanReport:
    repository_fingerprint: str
    file_count: int
    ignored_file_count: int
    languages: tuple[str, ...]
    category_scores: dict[str, int]
    score: int
    grade: str
    findings: tuple[Finding, ...]

    @property
    def summary(self) -> dict[str, object]:
        return {
            "scanner_version": SCANNER_VERSION,
            "repository_fingerprint": self.repository_fingerprint,
            "file_count": self.file_count,
            "ignored_file_count": self.ignored_file_count,
            "languages": list(self.languages),
            "category_scores": self.category_scores,
            "category_weights": CATEGORY_WEIGHTS,
            "score": self.score,
            "grade": self.grade,
            "finding_counts": {
                severity: sum(1 for finding in self.findings if finding.severity == severity)
                for severity in ("info", "low", "medium", "high")
            },
        }


def _iter_repository_files(root: Path, limits: ScanLimits) -> tuple[list[RepositoryFile], int]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("Repository root must be a directory")
    files: list[RepositoryFile] = []
    ignored_count = 0
    for directory, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        directories[:] = sorted(
            directory_name
            for directory_name in directories
            if directory_name.lower() not in IGNORED_DIRECTORY_NAMES
            and not (Path(directory) / directory_name).is_symlink()
        )
        filenames = sorted(filenames)
        for filename in filenames:
            absolute_path = Path(directory) / filename
            if absolute_path.is_symlink():
                ignored_count += 1
                continue
            try:
                stat_result = absolute_path.stat()
            except OSError:
                ignored_count += 1
                continue
            relative_path = absolute_path.relative_to(root).as_posix()
            if len(files) >= limits.max_files:
                raise ScanLimitError(f"Repository contains more than {limits.max_files} files")
            content_sha256: str | None = None
            if stat_result.st_size <= limits.max_file_bytes:
                digest = hashlib.sha256()
                try:
                    with absolute_path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    content_sha256 = digest.hexdigest()
                except OSError:
                    ignored_count += 1
                    continue
            files.append(
                RepositoryFile(
                    path=relative_path,
                    absolute_path=absolute_path,
                    size=stat_result.st_size,
                    content_sha256=content_sha256,
                )
            )
    return files, ignored_count


def _read_text(file: RepositoryFile, *, max_characters: int = 200_000) -> str | None:
    if file.size > max_characters:
        return None
    try:
        data = file.absolute_path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8_192]:
        return None
    return data.decode("utf-8", errors="replace")[:max_characters]


def _evidence(files: Iterable[RepositoryFile], detail: str, limit: int = 8) -> tuple[Evidence, ...]:
    return tuple(Evidence(path=file.path, detail=detail) for file in list(files)[:limit])


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _fingerprint(files: Iterable[RepositoryFile]) -> str:
    digest = hashlib.sha256()
    for file in sorted(files, key=lambda item: item.path):
        digest.update(file.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(file.size).encode("ascii"))
        digest.update(b"\0")
        digest.update((file.content_sha256 or "large-file").encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _category_finding(
    *,
    code: str,
    category: str,
    severity: str,
    title: str,
    description: str,
    remediation: str | None,
    evidence: Iterable[Evidence],
) -> Finding:
    return Finding(
        code=code,
        category=category,
        severity=severity,
        title=title,
        description=description,
        remediation=remediation,
        evidence=tuple(evidence),
    )


def scan_repository(root: Path, *, limits: ScanLimits | None = None) -> ScanReport:
    """Scan a repository using stable paths, rules, and output ordering."""

    limits = limits or ScanLimits()
    files, ignored_count = _iter_repository_files(root, limits)
    dependency_files = [
        file
        for file in files
        if Path(file.path).name.lower() in PRIMARY_DEPENDENCY_NAMES
        or Path(file.path).suffix.lower() in {".csproj", ".fsproj", ".sln"}
    ]
    lock_file_names = {
        "poetry.lock",
        "pipfile.lock",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "go.sum",
        "cargo.lock",
        "gemfile.lock",
        "composer.lock",
    }
    lock_files = [file for file in dependency_files if Path(file.path).name.lower() in lock_file_names]
    primary_dependency_files = [file for file in dependency_files if file not in lock_files]

    env_templates = [file for file in files if Path(file.path).name.lower() in ENV_TEMPLATE_NAMES]
    secret_env_files = [
        file
        for file in files
        if Path(file.path).name.lower().startswith(".env")
        and Path(file.path).name.lower() not in ENV_TEMPLATE_NAMES
        and Path(file.path).name.lower() not in {".envrc"}
    ]

    test_files = [
        file
        for file in files
        if Path(file.path).name.lower().startswith("test_")
        or Path(file.path).name.lower().endswith(TEST_FILE_SUFFIXES)
        or any(part.lower() in {"test", "tests", "spec", "__tests__"} for part in Path(file.path).parts[:-1])
    ]
    ci_files = [
        file
        for file in files
        if file.path.lower().startswith(".github/workflows/")
        or Path(file.path).name.lower() in {".travis.yml", "appveyor.yml", "azure-pipelines.yml"}
    ]

    dockerfiles = [
        file
        for file in files
        if Path(file.path).name.lower() == "dockerfile"
        or Path(file.path).name.lower().startswith("dockerfile.")
    ]
    compose_files = [
        file
        for file in files
        if Path(file.path).name.lower()
        in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
    ]
    dockerignore_files = [file for file in files if Path(file.path).name.lower() == ".dockerignore"]

    readme_files = [file for file in files if Path(file.path).name.lower().startswith("readme")]
    docs_files = [
        file
        for file in files
        if any(part.lower() in {"docs", "documentation"} for part in Path(file.path).parts[:-1])
    ]
    supporting_docs = [
        file
        for file in files
        if Path(file.path).name.lower()
        in {"contributing.md", "contributing.rst", "license", "license.md", "license.txt"}
    ]

    category_scores: dict[str, int] = {}
    findings: list[Finding] = []

    if primary_dependency_files:
        category_scores["dependencies"] = 100
        findings.append(
            _category_finding(
                code="dependencies.manifest_detected",
                category="dependencies",
                severity="info",
                title="Dependency manifest detected",
                description="The repository declares at least one dependency source that can be inspected by a build or deployment system.",
                remediation=None,
                evidence=_evidence(primary_dependency_files, "Dependency manifest"),
            )
        )
        if lock_files:
            findings.append(
                _category_finding(
                    code="dependencies.lockfile_detected",
                    category="dependencies",
                    severity="info",
                    title="Dependency lockfile detected",
                    description="At least one lockfile is present, which helps make dependency resolution reproducible.",
                    remediation=None,
                    evidence=_evidence(lock_files, "Dependency lockfile"),
                )
            )
    elif lock_files:
        category_scores["dependencies"] = 60
        findings.append(
            _category_finding(
                code="dependencies.lockfile_only",
                category="dependencies",
                severity="medium",
                title="Only a dependency lockfile was detected",
                description="A lockfile is present without a primary manifest, so the intended dependency contract is unclear.",
                remediation="Keep the primary dependency manifest alongside its lockfile.",
                evidence=_evidence(lock_files, "Lockfile without a primary manifest"),
            )
        )
    else:
        category_scores["dependencies"] = 0
        findings.append(
            _category_finding(
                code="dependencies.manifest_missing",
                category="dependencies",
                severity="high",
                title="No dependency manifest detected",
                description="No supported dependency manifest was found in the repository.",
                remediation="Add the dependency manifest used by the project and pin versions where reproducibility matters.",
                evidence=(Evidence(path=".", detail="No supported dependency manifest found"),),
            )
        )

    if env_templates:
        category_scores["environment"] = 100
        findings.append(
            _category_finding(
                code="environment.template_detected",
                category="environment",
                severity="info",
                title="Environment template detected",
                description="A non-secret environment template is available for local setup and deployment configuration.",
                remediation=None,
                evidence=_evidence(env_templates, "Environment variable template"),
            )
        )
    elif secret_env_files:
        category_scores["environment"] = 20
        findings.append(
            _category_finding(
                code="environment.template_missing_secret_file_present",
                category="environment",
                severity="high",
                title="Environment file present without a template",
                description="An environment file is present, but no example/template file was found. Values are not read or included in evidence.",
                remediation="Keep secrets out of source control and add a redacted .env.example with required variable names.",
                evidence=_evidence(secret_env_files, "Environment file path only; contents intentionally omitted"),
            )
        )
    else:
        category_scores["environment"] = 0
        findings.append(
            _category_finding(
                code="environment.template_missing",
                category="environment",
                severity="medium",
                title="No environment template detected",
                description="No supported environment template was found to document required configuration variables.",
                remediation="Add a redacted .env.example or equivalent configuration template.",
                evidence=(Evidence(path=".", detail="No environment template found"),),
            )
        )

    if test_files:
        category_scores["tests"] = 100
        findings.append(
            _category_finding(
                code="tests.detected",
                category="tests",
                severity="info",
                title="Automated tests detected",
                description="The repository contains files or directories matching common automated-test conventions.",
                remediation=None,
                evidence=_evidence(test_files, "Test source or test directory"),
            )
        )
    elif ci_files:
        category_scores["tests"] = 20
        findings.append(
            _category_finding(
                code="tests.ci_without_test_files",
                category="tests",
                severity="medium",
                title="CI configuration found without test files",
                description="Continuous-integration configuration exists, but no common test file or test directory was detected.",
                remediation="Add a deterministic test suite and run it from CI.",
                evidence=_evidence(ci_files, "CI configuration"),
            )
        )
    else:
        category_scores["tests"] = 0
        findings.append(
            _category_finding(
                code="tests.missing",
                category="tests",
                severity="high",
                title="No automated tests detected",
                description="No common test file, test directory, or test runner convention was found.",
                remediation="Add a fast deterministic test command covering the important user flows.",
                evidence=(Evidence(path=".", detail="No test files or test directories found"),),
            )
        )

    docker_score = 0
    if dockerfiles:
        docker_score += 70
    if compose_files:
        docker_score += 20
    if dockerignore_files:
        docker_score += 10
    category_scores["docker"] = min(100, docker_score)
    if dockerfiles or compose_files or dockerignore_files:
        docker_evidence = _evidence(
            [*dockerfiles, *compose_files, *dockerignore_files], "Containerization file"
        )
        findings.append(
            _category_finding(
                code="docker.configuration_detected",
                category="docker",
                severity="info",
                title="Container configuration detected",
                description="The repository includes container build or orchestration configuration.",
                remediation=None,
                evidence=docker_evidence,
            )
        )
        if not dockerfiles:
            findings.append(
                _category_finding(
                    code="dockerfile.missing",
                    category="docker",
                    severity="low",
                    title="Dockerfile not detected",
                    description="Container orchestration files exist, but no Dockerfile was found.",
                    remediation="Add a pinned, minimal Dockerfile when the repository is expected to build as a container.",
                    evidence=_evidence(compose_files, "Compose file without Dockerfile"),
                )
            )
    else:
        findings.append(
            _category_finding(
                code="docker.configuration_missing",
                category="docker",
                severity="low",
                title="No container configuration detected",
                description="No Dockerfile, compose file, or .dockerignore was found.",
                remediation="Add container configuration if deployment or local reproducibility requires Docker.",
                evidence=(Evidence(path=".", detail="No container configuration found"),),
            )
        )

    readme_quality = 0
    nonempty_readmes = []
    for readme in readme_files:
        text = _read_text(readme)
        if text and text.strip():
            nonempty_readmes.append(readme)
    if nonempty_readmes:
        readme_quality += 70
    if docs_files:
        readme_quality += 20
    if supporting_docs:
        readme_quality += 10
    category_scores["documentation"] = min(100, readme_quality)
    if nonempty_readmes or docs_files or supporting_docs:
        findings.append(
            _category_finding(
                code="documentation.detected",
                category="documentation",
                severity="info",
                title="Project documentation detected",
                description="The repository includes a README, documentation directory, or supporting project guidance.",
                remediation=None,
                evidence=_evidence([*nonempty_readmes, *docs_files, *supporting_docs], "Documentation file"),
            )
        )
    else:
        findings.append(
            _category_finding(
                code="documentation.missing",
                category="documentation",
                severity="medium",
                title="Project documentation not detected",
                description="No non-empty README, documentation directory, or supporting project guidance was found.",
                remediation="Add setup, run, test, deployment, and configuration instructions to a README.",
                evidence=(Evidence(path=".", detail="No supported documentation found"),),
            )
        )

    languages = sorted(
        {
            language
            for file in files
            if (language := LANGUAGE_BY_SUFFIX.get(Path(file.path).suffix.lower())) is not None
        }
    )
    weighted_score = round(
        sum(category_scores[name] * weight for name, weight in CATEGORY_WEIGHTS.items())
        / sum(CATEGORY_WEIGHTS.values())
    )
    findings.sort(key=lambda finding: (finding.category, finding.code))
    return ScanReport(
        repository_fingerprint=_fingerprint(files),
        file_count=len(files),
        ignored_file_count=ignored_count,
        languages=tuple(languages),
        category_scores=category_scores,
        score=weighted_score,
        grade=_grade(weighted_score),
        findings=tuple(findings),
    )
