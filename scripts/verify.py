from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import payload_digests
from kit import (
    DIST_ROOT,
    LOCKFILE,
    PLUGINS_ROOT,
    REPO_ROOT,
    file_digests,
    load_sources,
    read_version,
)

VERSIONED_MANIFESTS = (
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "plugins/opencode/package.json",
)


def report(failures: list[str], message: str) -> None:
    failures.append(message)


def verify_manifest_versions(failures: list[str]) -> None:
    expected = read_version()
    for relative in VERSIONED_MANIFESTS:
        manifest = REPO_ROOT / relative
        if not manifest.is_file():
            report(failures, f"{relative} is missing")
            continue
        declared = json.loads(manifest.read_text(encoding="utf-8")).get("version")
        if declared != expected:
            report(failures, f"{relative} declares version {declared!r}, VERSION says {expected!r}")


def verify_lockfile_version(failures: list[str], lock: dict) -> None:
    if lock["version"] != read_version():
        report(failures, f"agent-kit.lock.json version {lock['version']!r} does not match VERSION")


def verify_distribution(failures: list[str], lock: dict) -> None:
    if not DIST_ROOT.is_dir():
        report(failures, "dist/ does not exist; run `just build` first")
        return
    expected = lock["distribution"]
    actual = payload_digests(DIST_ROOT)

    for missing in sorted(set(expected) - set(actual)):
        report(failures, f"dist/{missing} is missing")
    for unexpected in sorted(set(actual) - set(expected)):
        report(failures, f"dist/{unexpected} is not in the lockfile")
    for shared in sorted(set(expected) & set(actual)):
        if expected[shared] != actual[shared]:
            report(failures, f"dist/{shared} does not match its locked sha256")


def verify_skill_payload_is_identical_everywhere(failures: list[str], lock: dict) -> None:
    if not DIST_ROOT.is_dir():
        return
    digests = payload_digests(DIST_ROOT)
    for skill in lock["skills"]:
        for relative, expected in skill["files"].items():
            placements = [f"skills/{skill['name']}/{relative}"] + [
                f"plugins/{harness}/skills/{skill['name']}/{relative}" for harness in lock["harnesses"]
            ]
            for placement in placements:
                actual = digests.get(placement)
                if actual is None:
                    report(failures, f"dist/{placement} is missing")
                elif actual != expected:
                    report(failures, f"dist/{placement} differs from the canonical skill file")


def verify_canonical_matches_vendor(failures: list[str]) -> None:
    for source in load_sources():
        if not source.vendored_skill_tree.is_dir():
            report(failures, f"{source.name}: vendored tree {source.vendored_skill_tree} is missing")
            continue
        vendored = file_digests(source.vendored_skill_tree)
        canonical = file_digests(source.canonical_tree)
        for relative in sorted(set(vendored) | set(canonical)):
            if vendored.get(relative) != canonical.get(relative):
                report(
                    failures,
                    f"{source.name}: skills/{source.name}/{relative} is not byte-identical to "
                    "its vendored upstream copy, so the comment-policy exemption on skills/ "
                    "no longer holds",
                )


def verify_opencode_shim_resolves(failures: list[str]) -> None:
    shim = PLUGINS_ROOT / "opencode" / "index.js"
    if not shim.is_file():
        report(failures, "plugins/opencode/index.js is missing")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check dist/ against agent-kit.lock.json and the declared batch version"
    )
    parser.parse_args()

    if not LOCKFILE.is_file():
        print("agent-kit.lock.json is missing; run `just lock`", file=sys.stderr)
        return 1
    lock = json.loads(LOCKFILE.read_text(encoding="utf-8"))

    failures: list[str] = []
    verify_manifest_versions(failures)
    verify_lockfile_version(failures, lock)
    verify_opencode_shim_resolves(failures)
    verify_canonical_matches_vendor(failures)
    verify_distribution(failures, lock)
    verify_skill_payload_is_identical_everywhere(failures, lock)

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print(f"{len(failures)} verification failure(s)", file=sys.stderr)
        return 1

    print(
        f"verified {len(lock['skills'])} skills and {len(lock['distribution'])} "
        f"distribution files at version {lock['version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
