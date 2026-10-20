"""Deterministic repository inventory, evidence, and score calculation."""

from __future__ import annotations

import hashlib
import json
import os
import re
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

SEVERITY_PENALTIES = {
    "critical": 45,
    "high": 30,
    "medium": 15,
    "low": 5,
    "info": 0,
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
                for severity in ("info", "low", "medium", "high", "critical")
            },
            "checks": {
                "passed": sum(1 for finding in self.findings if finding.severity == "info"),
                "warnings": sum(1 for finding in self.findings if finding.severity in {"low", "medium"}),
                "failed": sum(1 for finding in self.findings if finding.severity in {"high", "critical"}),
                "not_run": 2,
            },
            "execution": {
                "tests": "not_run",
                "docker_build": "not_run",
            },
            "limitations": [
                "Static analysis does not execute repository tests or build scripts.",
                "Heuristic findings should be reviewed against project-specific conventions.",
            ],
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


def _line_number(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    return text.count("\n", 0, match.start()) + 1


def _template_variables(files: Iterable[RepositoryFile]) -> dict[str, set[str]]:
    variables: dict[str, set[str]] = {}
    for file in files:
        text = _read_text(file)
        if text is None:
            continue
        names: set[str] = set()
        for line in text.splitlines():
            match = re.match(r"^\s*([A-Z][A-Z0-9_]+)\s*=", line)
            if match:
                names.add(match.group(1))
        if names:
            variables[file.path] = names
    return variables


def _environment_findings(
    files: list[RepositoryFile], env_templates: list[RepositoryFile]
) -> list[Finding]:
    findings: list[Finding] = []
    templates = _template_variables(env_templates)
    template_names = set().union(*templates.values()) if templates else set()
    references: dict[str, list[Evidence]] = {}
    reference_patterns = (
        r"(?:process\.env|import\.meta\.env)\.([A-Z][A-Z0-9_]*)",
        r"(?:os\.environ(?:\.get)?|os\.getenv)\s*\(\s*['\"]([A-Z][A-Z0-9_]*)",
        r"(?:ENV|System\.getenv)\s*\[?\s*['\"]([A-Z][A-Z0-9_]*)",
    )
    secret_pattern = re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|secret|password|private[_-]?key)"
        r"\s*[:=]\s*(['\"])(?!\$|<|your_|change_|example|placeholder)[^'\"]{8,}\2"
    )
    template_paths = set(templates)
    for file in files:
        if file.path in template_paths or file.path.lower().startswith(".env"):
            continue
        text = _read_text(file)
        if text is None:
            continue
        for pattern in reference_patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                name = match.group(1).upper()
                line = text.count("\n", 0, match.start()) + 1
                references.setdefault(name, []).append(
                    Evidence(path=file.path, detail=f"Environment variable {name} is referenced", line=line)
                )
        secret_match = secret_pattern.search(text)
        if secret_match:
            line = text.count("\n", 0, secret_match.start()) + 1
            findings.append(
                _category_finding(
                    code=f"environment.secret_like_{hashlib.sha1(file.path.encode()).hexdigest()[:10]}",
                    category="environment",
                    severity="critical",
                    title="Secret-like value detected in source",
                    description="A credential-shaped assignment was detected. The value is intentionally redacted from RepoReady evidence.",
                    remediation="Rotate the value if it is real, remove it from repository history, and load it from a secret store or environment variable.",
                    evidence=(Evidence(path=file.path, detail="Potential secret-like assignment detected; value redacted", line=line),),
                )
            )
    missing = sorted(set(references) - template_names)
    if missing:
        evidence = [item for name in missing for item in references[name]][:8]
        template_detail = ", ".join(sorted(templates)) if templates else "no environment template"
        findings.append(
            _category_finding(
                code="environment.referenced_variables_missing_from_template",
                category="environment",
                severity="medium",
                title="Referenced environment variables are undocumented",
                description=f"The source references {', '.join(missing[:8])}, but those names are absent from {template_detail}.",
                remediation="Add the required variable names to a redacted .env.example or equivalent template without committing secret values.",
                evidence=evidence,
            )
        )
    return findings


def _dependency_findings(
    files: list[RepositoryFile], primary_dependency_files: list[RepositoryFile], lock_files: list[RepositoryFile]
) -> list[Finding]:
    findings: list[Finding] = []
    by_name = {Path(file.path).name.lower(): file for file in files}
    manifest_names = {Path(file.path).name.lower() for file in primary_dependency_files}
    lock_names = {Path(file.path).name.lower() for file in lock_files}
    if "package.json" in manifest_names and not lock_names.intersection({"package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml"}):
        package_file = by_name["package.json"]
        findings.append(
            _category_finding(
                code="dependencies.javascript_lockfile_missing",
                category="dependencies",
                severity="high",
                title="JavaScript lockfile is missing",
                description="package.json is present, but no npm, pnpm, or Yarn lockfile was found.",
                remediation="Commit the lockfile produced by the package manager used by the project.",
                evidence=(Evidence(path=package_file.path, detail="package.json detected without a supported lockfile", line=1),),
            )
        )
    if {"go.mod"}.intersection(manifest_names) and "go.sum" not in lock_names:
        file = by_name["go.mod"]
        findings.append(
            _category_finding(
                code="dependencies.go_checksum_file_missing",
                category="dependencies",
                severity="medium",
                title="Go checksum file is missing",
                description="go.mod is present without go.sum, so resolved module checksums are not recorded.",
                remediation="Run the project’s Go dependency workflow and commit go.sum.",
                evidence=(Evidence(path=file.path, detail="go.mod detected without go.sum", line=1),),
            )
        )
    if "cargo.toml" in manifest_names and "cargo.lock" not in lock_names:
        file = by_name["cargo.toml"]
        findings.append(
            _category_finding(
                code="dependencies.rust_lockfile_missing",
                category="dependencies",
                severity="medium",
                title="Rust lockfile is missing",
                description="Cargo.toml is present without Cargo.lock. Application crates normally commit the lockfile for reproducible builds.",
                remediation="Generate and commit Cargo.lock when this is an application rather than a published library.",
                evidence=(Evidence(path=file.path, detail="Cargo.toml detected without Cargo.lock", line=1),),
            )
        )
    manifests_by_family = {
        "javascript": {"package.json"},
        "python": {"requirements.txt", "requirements.in", "pyproject.toml", "pipfile"},
        "rust": {"cargo.toml"},
        "go": {"go.mod"},
        "java": {"pom.xml", "build.gradle", "build.gradle.kts"},
    }
    for family, names in manifests_by_family.items():
        present = sorted(manifest_names.intersection(names))
        if len(present) > 1:
            evidence = tuple(Evidence(path=by_name[name].path, detail=f"{family.title()} dependency manifest") for name in present)
            findings.append(
                _category_finding(
                    code=f"dependencies.multiple_{family}_manifests",
                    category="dependencies",
                    severity="medium",
                    title=f"Multiple {family} dependency manifests detected",
                    description="Multiple manifests for the same ecosystem can drift unless the project documents which one is authoritative.",
                    remediation="Choose one authoritative manifest or document the relationship and keep generated files synchronized.",
                    evidence=evidence,
                )
            )
    package_file = by_name.get("package.json")
    if package_file:
        text = _read_text(package_file) or ""
        try:
            package = json.loads(text)
        except json.JSONDecodeError:
            package = {}
        dependency_sections = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
        suspicious: list[str] = []
        for section in dependency_sections:
            values = package.get(section, {}) if isinstance(package, dict) else {}
            if isinstance(values, dict):
                suspicious.extend(
                    f"{section}.{name}={value}"
                    for name, value in values.items()
                    if isinstance(value, str) and (value in {"*", "latest"} or value.startswith(("^", "~", ">", "<")))
                )
        if suspicious:
            findings.append(
                _category_finding(
                    code="dependencies.javascript_range_versions",
                    category="dependencies",
                    severity="medium",
                    title="JavaScript dependencies use ranges or floating tags",
                    description="At least one dependency is declared with a range or floating tag instead of an exact version.",
                    remediation="Use the project’s lockfile as the reproducible resolution and review broad ranges intentionally.",
                    evidence=(Evidence(path=package_file.path, detail=f"{len(suspicious)} dependency declaration(s) use a range or floating tag", line=1),),
                )
            )
    for file in files:
        if Path(file.path).name.lower() not in {"requirements.txt", "requirements.in"}:
            continue
        text = _read_text(file) or ""
        unpinned = [index for index, line in enumerate(text.splitlines(), 1) if line.strip() and not line.lstrip().startswith("#") and re.match(r"^[A-Za-z0-9_.-]+\s*$", line.strip())]
        if unpinned:
            findings.append(
                _category_finding(
                    code="dependencies.python_unpinned_requirements",
                    category="dependencies",
                    severity="medium",
                    title="Python requirements include unpinned entries",
                    description="At least one requirements entry has no version constraint, so resolution can change between installs.",
                    remediation="Pin direct dependencies or document why an unconstrained entry is intentional, then commit a resolver lockfile where appropriate.",
                    evidence=(Evidence(path=file.path, detail=f"Unpinned requirement found at line {unpinned[0]}", line=unpinned[0]),),
                )
            )
    return findings


def _docker_findings(files: list[RepositoryFile], dockerfiles: list[RepositoryFile], dockerignore_files: list[RepositoryFile]) -> list[Finding]:
    findings: list[Finding] = []
    if dockerfiles and not dockerignore_files:
        findings.append(
            _category_finding(
                code="docker.dockerignore_missing",
                category="docker",
                severity="low",
                title=".dockerignore is missing",
                description="A Dockerfile is present without a .dockerignore, which can send unnecessary or sensitive files into the build context.",
                remediation="Add a .dockerignore covering VCS metadata, dependencies, local secrets, and generated output.",
                evidence=(Evidence(path=dockerfiles[0].path, detail="Dockerfile detected without .dockerignore", line=1),),
            )
        )
    known_paths = {file.path for file in files}
    for dockerfile in dockerfiles:
        text = _read_text(dockerfile) or ""
        for line_number, line in enumerate(text.splitlines(), 1):
            match = re.match(r"\s*FROM\s+([^\s]+)", line, flags=re.IGNORECASE)
            if match:
                image = match.group(1)
                if "@sha256:" not in image and ":" not in image.rsplit("/", 1)[-1]:
                    findings.append(
                        _category_finding(
                            code="docker.base_image_tag_missing",
                            category="docker",
                            severity="medium",
                            title="Docker base image is not versioned",
                            description="A Docker FROM instruction uses an image without an explicit tag or digest.",
                            remediation="Pin the base image to a reviewed version or immutable digest.",
                            evidence=(Evidence(path=dockerfile.path, detail=f"Unpinned base image: {image}", line=line_number),),
                        )
                    )
                elif "@sha256:" not in image and re.search(r":\d+-(?:slim|alpine|bookworm|bullseye|buster)$", image) and not re.search(r":\d+\.\d+\.\d+", image):
                    findings.append(
                        _category_finding(
                            code="docker.base_image_tag_broad",
                            category="docker",
                            severity="low",
                            title="Docker base image tag is broad",
                            description="The base image has a major/minor family tag but not a patch-level version or digest.",
                            remediation="Prefer a patch-level tag or digest when deterministic rebuilds matter.",
                            evidence=(Evidence(path=dockerfile.path, detail=f"Broad base image tag: {image}", line=line_number),),
                        )
                    )
            copy_match = re.match(r"\s*(?:COPY|ADD)\s+(.+?)\s+[^\s]+\s*$", line, flags=re.IGNORECASE)
            if copy_match:
                sources = copy_match.group(1).split()
                for source in sources:
                    if source.startswith("--") or source.startswith(("http://", "https://")) or source in {".", "./"}:
                        continue
                    source_path = source.lstrip("./")
                    if source_path not in known_paths and not any(path.startswith(f"{source_path}/") for path in known_paths):
                        findings.append(
                            _category_finding(
                                code=f"docker.referenced_file_missing_{hashlib.sha1(source_path.encode()).hexdigest()[:10]}",
                                category="docker",
                                severity="high",
                                title="Dockerfile references a missing file",
                                description="A COPY or ADD instruction names a path that was not found in the scanned repository.",
                                remediation="Add the referenced file, correct the path, or remove the stale Docker instruction.",
                                evidence=(Evidence(path=dockerfile.path, detail=f"Missing build-context path: {source_path}", line=line_number),),
                            )
                        )
    return findings


def _documentation_findings(files: list[RepositoryFile], readme_files: list[RepositoryFile]) -> list[Finding]:
    findings: list[Finding] = []
    readme_text = "\n".join((_read_text(file) or "") for file in readme_files)
    if readme_files and readme_text and not re.search(r"\b(npm|pnpm|yarn|pip|pytest|cargo|go\s+test|make|docker|uvicorn|python)\b", readme_text, flags=re.IGNORECASE):
        findings.append(
            _category_finding(
                code="documentation.setup_commands_missing",
                category="documentation",
                severity="medium",
                title="README does not show setup or test commands",
                description="A README exists, but no recognizable install, test, runtime, or container command was found.",
                remediation="Document exact setup, run, test, and deployment commands for a clean checkout.",
                evidence=(Evidence(path=readme_files[0].path, detail="README text contains no recognized project commands", line=1),),
            )
        )
    for file in files:
        text = _read_text(file) or ""
        todo_match = re.search(r"\b(TODO|FIXME)\b", text, flags=re.IGNORECASE)
        if todo_match:
            line = text.count("\n", 0, todo_match.start()) + 1
            marker = todo_match.group(1).upper()
            findings.append(
                _category_finding(
                    code=f"documentation.maintenance_{marker.lower()}_{hashlib.sha1(file.path.encode()).hexdigest()[:10]}",
                    category="documentation",
                    severity="low",
                    title=f"{marker} maintenance note detected",
                    description="A TODO or FIXME marker is present. RepoReady treats this as a maintenance observation, not a verified failure.",
                    remediation="Track the work in the project issue system or remove the marker when the task is complete.",
                    evidence=(Evidence(path=file.path, detail=f"{marker} marker detected; content not expanded", line=line),),
                )
            )
    return findings


def _apply_score_penalties(category_scores: dict[str, int], findings: Iterable[Finding]) -> dict[str, int]:
    adjusted = dict(category_scores)
    for finding in findings:
        penalty = SEVERITY_PENALTIES.get(finding.severity, 0)
        if penalty:
            adjusted[finding.category] = max(0, adjusted.get(finding.category, 0) - penalty)
    return adjusted


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

    findings.extend(_dependency_findings(files, primary_dependency_files, lock_files))
    findings.extend(_environment_findings(files, env_templates))
    findings.extend(_docker_findings(files, dockerfiles, dockerignore_files))
    findings.extend(_documentation_findings(files, readme_files))
    category_scores = _apply_score_penalties(category_scores, findings)

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
