from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit import (
    DIST_ROOT,
    HARNESSES,
    LOCKFILE,
    PLUGINS_ROOT,
    REPO_ROOT,
    SKILLS_ROOT,
    VERSION_FILE,
    assert_portable_skill,
    file_digests,
    load_sources,
    read_version,
    write_json,
)

CLAUDE_PLUGIN_DIR = ".claude-plugin"
CODEX_PLUGIN_DIR = ".codex-plugin"
CODEX_MARKETPLACE_DIR = ".agents/plugins"
MARKETPLACE_FILE = "marketplace.json"
PLUGIN_FILE = "plugin.json"
SKILLS_DIR = "skills"
LICENSES_DIR = "licenses"
OPENCODE_SHIM_FILES = ("package.json", "index.js")

PLUGIN_SOURCE_IN_DIST = {
    "claude": "./plugins/claude",
    "codex": "./plugins/codex",
}


def copy_skill_batch(destination: Path) -> None:
    for source in load_sources():
        assert_portable_skill(source.canonical_tree)
        shutil.copytree(source.canonical_tree, destination / source.name, symlinks=False)


def build_claude_plugin(destination: Path) -> None:
    shutil.copytree(REPO_ROOT / CLAUDE_PLUGIN_DIR, destination / CLAUDE_PLUGIN_DIR)
    copy_skill_batch(destination / SKILLS_DIR)
    (destination / CLAUDE_PLUGIN_DIR / MARKETPLACE_FILE).unlink(missing_ok=True)


def build_codex_plugin(destination: Path) -> None:
    shutil.copytree(REPO_ROOT / CODEX_PLUGIN_DIR, destination / CODEX_PLUGIN_DIR)
    copy_skill_batch(destination / SKILLS_DIR)


def build_opencode_plugin(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in OPENCODE_SHIM_FILES:
        shutil.copy2(PLUGINS_ROOT / "opencode" / name, destination / name)
    copy_skill_batch(destination / SKILLS_DIR)


def build_marketplaces(destination: Path) -> None:
    claude = json.loads((REPO_ROOT / CLAUDE_PLUGIN_DIR / MARKETPLACE_FILE).read_text(encoding="utf-8"))
    for entry in claude["plugins"]:
        entry["source"] = PLUGIN_SOURCE_IN_DIST["claude"]
    write_json(destination / CLAUDE_PLUGIN_DIR / MARKETPLACE_FILE, claude)

    codex = json.loads((REPO_ROOT / CODEX_MARKETPLACE_DIR / MARKETPLACE_FILE).read_text(encoding="utf-8"))
    for entry in codex["plugins"]:
        entry["source"] = {"source": "local", "path": PLUGIN_SOURCE_IN_DIST["codex"]}
    write_json(destination / CODEX_MARKETPLACE_DIR / MARKETPLACE_FILE, codex)


def build_licenses(destination: Path) -> None:
    for source in load_sources():
        for license_file in source.upstream.license_files:
            origin = source.vendored_root / license_file
            if not origin.is_file():
                raise SystemExit(f"{source.name}: vendored license {license_file} is missing")
            target = destination / source.upstream.key / license_file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, target)


def materialise(destination: Path, include_lockfile: bool) -> Path:
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True)

    copy_skill_batch(destination / SKILLS_DIR)
    build_claude_plugin(destination / "plugins" / "claude")
    build_codex_plugin(destination / "plugins" / "codex")
    build_opencode_plugin(destination / "plugins" / "opencode")
    build_marketplaces(destination)
    build_licenses(destination / LICENSES_DIR)
    shutil.copy2(VERSION_FILE, destination / VERSION_FILE.name)

    if include_lockfile:
        shutil.copy2(LOCKFILE, destination / LOCKFILE.name)

    return destination


def payload_digests(destination: Path) -> dict[str, str]:
    digests = file_digests(destination)
    digests.pop(LOCKFILE.name, None)
    return digests


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialise dist/ from skills/ and the plugin manifests")
    parser.add_argument("--destination", default=str(DIST_ROOT))
    arguments = parser.parse_args()

    destination = Path(arguments.destination).resolve()
    materialise(destination, include_lockfile=LOCKFILE.exists())
    digests = payload_digests(destination)
    print(f"built {destination.relative_to(REPO_ROOT) if destination.is_relative_to(REPO_ROOT) else destination}"
          f" at version {read_version()}: {len(digests)} payload files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
