from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MINIMUM_PYTHON = (3, 9)

if sys.version_info < MINIMUM_PYTHON:
    raise SystemExit(
        f"agent-kit build tooling needs Python >= {'.'.join(map(str, MINIMUM_PYTHON))}, "
        f"found {'.'.join(map(str, sys.version_info[:3]))}"
    )

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = REPO_ROOT / "sources.json"
LOCKFILE = REPO_ROOT / "agent-kit.lock.json"
VERSION_FILE = REPO_ROOT / "VERSION"
VENDOR_ROOT = REPO_ROOT / "vendor"
SKILLS_ROOT = REPO_ROOT / "skills"
PLUGINS_ROOT = REPO_ROOT / "plugins"
DIST_ROOT = REPO_ROOT / "dist"

SKILL_ENTRYPOINT = "SKILL.md"
PORTABLE_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_LENGTH_LIMIT = 64
DESCRIPTION_LENGTH_LIMIT = 1024
FRONTMATTER_FENCE = "---"

HARNESSES = ("claude", "codex", "opencode")

CODEX_INTERFACE_FILE = "agents/openai.yaml"
CLAUDE_IMPLICIT_INVOCATION_KEY = "disable-model-invocation"
CODEX_IMPLICIT_INVOCATION_PATTERN = re.compile(r"^\s*allow_implicit_invocation:\s*false\s*$", re.M)
IMPLICIT = "implicit"
EXPLICIT_ONLY = "explicit-only"


class PortabilityError(Exception):
    pass


@dataclass(frozen=True)
class Upstream:
    key: str
    repository: str
    commit: str
    license: str
    license_files: tuple[str, ...]


@dataclass(frozen=True)
class SkillSource:
    name: str
    upstream: Upstream
    upstream_path: str
    requires: tuple[str, ...]

    @property
    def vendored_root(self) -> Path:
        return VENDOR_ROOT / self.name / self.upstream.commit

    @property
    def vendored_skill_tree(self) -> Path:
        return self.vendored_root / self.upstream_path

    @property
    def canonical_tree(self) -> Path:
        return SKILLS_ROOT / self.name


def load_sources() -> list[SkillSource]:
    document = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    upstreams = {
        key: Upstream(
            key=key,
            repository=value["repository"],
            commit=value["commit"],
            license=value["license"],
            license_files=tuple(value.get("licenseFiles", ())),
        )
        for key, value in document["upstreams"].items()
    }
    return [
        SkillSource(
            name=entry["name"],
            upstream=upstreams[entry["upstream"]],
            upstream_path=entry["path"],
            requires=tuple(entry.get("requires", ())),
        )
        for entry in document["skills"]
    ]


def read_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tracked_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def file_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_of(path)
        for path in tracked_files(root)
    }


def split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        raise PortabilityError("SKILL.md must open with a YAML frontmatter fence")
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_FENCE:
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    raise PortabilityError("SKILL.md frontmatter is never closed")


def top_level_scalars(frontmatter: str) -> dict[str, str]:
    scalars: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if not line.strip() or line.startswith((" ", "\t", "-", "#")):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        scalars[key.strip()] = unquote(value.strip())
    return scalars


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_skill_metadata(skill_tree: Path) -> dict[str, str]:
    entrypoint = skill_tree / SKILL_ENTRYPOINT
    if not entrypoint.is_file():
        raise PortabilityError(f"{skill_tree} has no {SKILL_ENTRYPOINT}")
    frontmatter, _ = split_frontmatter(entrypoint.read_text(encoding="utf-8"))
    return top_level_scalars(frontmatter)


def assert_portable_skill(skill_tree: Path) -> dict[str, str]:
    metadata = read_skill_metadata(skill_tree)
    directory = skill_tree.name

    name = metadata.get("name", "")
    if not name:
        raise PortabilityError(f"{directory}: frontmatter has no name")
    if not PORTABLE_NAME_PATTERN.fullmatch(name):
        raise PortabilityError(
            f"{directory}: name {name!r} does not match {PORTABLE_NAME_PATTERN.pattern}"
        )
    if len(name) > NAME_LENGTH_LIMIT:
        raise PortabilityError(f"{directory}: name exceeds {NAME_LENGTH_LIMIT} characters")
    if name != directory:
        raise PortabilityError(f"{directory}: name {name!r} must equal the directory name")

    description = metadata.get("description", "")
    if not description:
        raise PortabilityError(f"{directory}: frontmatter has no description")
    if len(description) > DESCRIPTION_LENGTH_LIMIT:
        raise PortabilityError(
            f"{directory}: description exceeds {DESCRIPTION_LENGTH_LIMIT} characters"
        )

    nested = [
        path
        for path in skill_tree.rglob(SKILL_ENTRYPOINT)
        if path != skill_tree / SKILL_ENTRYPOINT
    ]
    if nested:
        offenders = ", ".join(path.relative_to(skill_tree).as_posix() for path in nested)
        raise PortabilityError(
            f"{directory}: nested {SKILL_ENTRYPOINT} loads as a separate skill in OpenCode: {offenders}"
        )

    symlinks = [path for path in skill_tree.rglob("*") if path.is_symlink()]
    if symlinks:
        offenders = ", ".join(path.relative_to(skill_tree).as_posix() for path in symlinks)
        raise PortabilityError(f"{directory}: symlinks do not survive distribution: {offenders}")

    return metadata


def invocation_mode(skill_tree: Path) -> dict[str, str]:
    metadata = read_skill_metadata(skill_tree)
    claude = (
        EXPLICIT_ONLY
        if metadata.get(CLAUDE_IMPLICIT_INVOCATION_KEY, "").strip().lower() == "true"
        else IMPLICIT
    )
    interface = skill_tree / CODEX_INTERFACE_FILE
    codex = (
        EXPLICIT_ONLY
        if interface.is_file()
        and CODEX_IMPLICIT_INVOCATION_PATTERN.search(interface.read_text(encoding="utf-8"))
        else IMPLICIT
    )
    return {"claude": claude, "codex": codex, "opencode": IMPLICIT}


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")
