from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import materialise, payload_digests
from kit import (
    HARNESSES,
    LOCKFILE,
    REPO_ROOT,
    SkillSource,
    assert_portable_skill,
    file_digests,
    invocation_mode,
    load_sources,
    read_version,
    write_json,
)

LOCKFILE_FORMAT = 1
CLAUDE_ONLY_AGENT_SUFFIX = ".md"
AGENTS_SUBDIRECTORY = "agents"


def claude_only_agent_files(source: SkillSource) -> list[str]:
    agents = source.canonical_tree / AGENTS_SUBDIRECTORY
    if not agents.is_dir():
        return []
    return sorted(
        path.relative_to(source.canonical_tree).as_posix()
        for path in agents.iterdir()
        if path.is_file() and path.suffix == CLAUDE_ONLY_AGENT_SUFFIX
    )


def skill_entry(source: SkillSource, batch: set[str]) -> dict:
    metadata = assert_portable_skill(source.canonical_tree)
    unsatisfied = sorted(set(source.requires) - batch)
    entry = {
        "name": source.name,
        "description": metadata["description"],
        "upstream": {
            "repository": source.upstream.repository,
            "commit": source.upstream.commit,
            "path": source.upstream_path,
            "license": source.upstream.license,
            "licenseFiles": list(source.upstream.license_files),
        },
        "vendored": source.vendored_root.relative_to(REPO_ROOT).as_posix(),
        "canonical": source.canonical_tree.relative_to(REPO_ROOT).as_posix(),
        "requires": list(source.requires),
        "invocation": invocation_mode(source.canonical_tree),
        "files": file_digests(source.canonical_tree),
    }
    degradations = []
    if unsatisfied:
        degradations.append(
            {
                "kind": "unsatisfied-skill-reference",
                "detail": (
                    f"SKILL.md calls the Skill tool for {', '.join(unsatisfied)}, "
                    "which this batch does not ship; those steps degrade in every harness"
                ),
                "affects": list(HARNESSES),
            }
        )
    claude_only = claude_only_agent_files(source)
    if claude_only:
        degradations.append(
            {
                "kind": "claude-only-subagent",
                "detail": (
                    f"{', '.join(claude_only)} is a Claude subagent format that Codex "
                    "and OpenCode do not read"
                ),
                "affects": ["codex", "opencode"],
            }
        )
    entry["degradations"] = degradations
    return entry



def distribution_digests() -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="agent-kit-lock-") as scratch:
        return payload_digests(materialise(Path(scratch) / "dist", include_lockfile=False))


def build_lock_document() -> dict:
    sources = load_sources()
    batch = {source.name for source in sources}
    skills = [skill_entry(source, batch) for source in sources]
    return {
        "lockfileVersion": LOCKFILE_FORMAT,
        "version": read_version(),
        "harnesses": list(HARNESSES),
        "skills": skills,
        "distribution": distribution_digests(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate agent-kit.lock.json from sources.json, vendor/ and skills/"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the lockfile is out of date",
    )
    arguments = parser.parse_args()

    document = build_lock_document()
    serialised = json.dumps(document, indent=2) + "\n"

    if arguments.check:
        if not LOCKFILE.exists():
            print("agent-kit.lock.json is missing", file=sys.stderr)
            return 1
        if LOCKFILE.read_text(encoding="utf-8") != serialised:
            print("agent-kit.lock.json is out of date; run `just lock`", file=sys.stderr)
            return 1
        print("agent-kit.lock.json is up to date")
        return 0

    write_json(LOCKFILE, document)
    tracked = sum(len(skill["files"]) for skill in document["skills"])
    flagged = sum(len(skill["degradations"]) for skill in document["skills"])
    print(
        f"locked {len(document['skills'])} skills, {tracked} canonical files, "
        f"{len(document['distribution'])} distribution files, "
        f"{flagged} recorded degradations at version {document['version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
