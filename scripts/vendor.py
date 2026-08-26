from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit import (
    REPO_ROOT,
    SKILLS_ROOT,
    VENDOR_ROOT,
    PortabilityError,
    SkillSource,
    Upstream,
    assert_portable_skill,
    load_sources,
)

MIRROR_ROOT = REPO_ROOT / ".vendor-cache"


def upstream_mirror(upstream: Upstream) -> Path:
    mirror = MIRROR_ROOT / f"{upstream.key}.git"
    if not mirror.exists():
        mirror.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "--bare", "--quiet", upstream.repository, str(mirror))
    if not has_commit(mirror, upstream.commit):
        run("git", "-C", str(mirror), "fetch", "--quiet", "origin", "+refs/heads/*:refs/heads/*")
    if not has_commit(mirror, upstream.commit):
        raise SystemExit(f"{upstream.repository} does not contain commit {upstream.commit}")
    return mirror


def has_commit(mirror: Path, commit: str) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(mirror), "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True,
    )
    return probe.returncode == 0


def upstream_paths_at(mirror: Path, commit: str, prefix: str) -> list[str]:
    listing = run_capture(
        "git", "-C", str(mirror), "ls-tree", "-r", "--name-only", commit, "--", prefix
    )
    return [line for line in listing.splitlines() if line]


def extract_verbatim(mirror: Path, commit: str, upstream_path: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    blob = subprocess.run(
        ["git", "-C", str(mirror), "show", f"{commit}:{upstream_path}"],
        capture_output=True,
        check=True,
    ).stdout
    destination.write_bytes(blob)


def vendor_skill(source: SkillSource) -> None:
    mirror = upstream_mirror(source.upstream)
    commit = source.upstream.commit

    skill_paths = upstream_paths_at(mirror, commit, source.upstream_path)
    if not skill_paths:
        raise SystemExit(f"{source.name}: {source.upstream_path} is empty at {commit}")

    license_paths = [
        path
        for name in source.upstream.license_files
        for path in upstream_paths_at(mirror, commit, name)
    ]

    shutil.rmtree(source.vendored_root, ignore_errors=True)
    for upstream_path in skill_paths + license_paths:
        extract_verbatim(mirror, commit, upstream_path, source.vendored_root / upstream_path)


def canonicalise_skill(source: SkillSource) -> None:
    shutil.rmtree(source.canonical_tree, ignore_errors=True)
    shutil.copytree(source.vendored_skill_tree, source.canonical_tree, symlinks=False)


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def run_capture(*command: str) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch every pinned upstream skill into vendor/ and canonicalise it into skills/"
    )
    parser.add_argument(
        "--only", action="append", default=[], help="restrict to one skill name (repeatable)"
    )
    arguments = parser.parse_args()

    sources = load_sources()
    if arguments.only:
        selected = set(arguments.only)
        sources = [source for source in sources if source.name in selected]
        missing = selected - {source.name for source in sources}
        if missing:
            raise SystemExit(f"unknown skill(s): {', '.join(sorted(missing))}")

    VENDOR_ROOT.mkdir(parents=True, exist_ok=True)
    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for source in sources:
        vendor_skill(source)
        canonicalise_skill(source)
        try:
            assert_portable_skill(source.canonical_tree)
        except PortabilityError as error:
            failures.append(str(error))
        print(f"vendored {source.name} at {source.upstream.commit[:12]}")

    if failures:
        for failure in failures:
            print(f"not portable: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
