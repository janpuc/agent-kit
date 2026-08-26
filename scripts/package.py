from __future__ import annotations

import argparse
import gzip
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit import DIST_ROOT, REPO_ROOT, read_version, sha256_of, tracked_files

RELEASE_ROOT = REPO_ROOT / "release"
REPRODUCIBLE_MTIME = 315532800
FILE_MODE = 0o644
DIRECTORY_MODE = 0o755
OWNER_UID = 0
OWNER_GID = 0
OWNER_NAME = "root"


def archive_name(version: str) -> str:
    return f"agent-kit_v{version}.tar.gz"


def checksums_name(version: str) -> str:
    return f"agent-kit_{version}_checksums.txt"


def normalise(entry: tarfile.TarInfo) -> tarfile.TarInfo:
    entry.mtime = REPRODUCIBLE_MTIME
    entry.uid = OWNER_UID
    entry.gid = OWNER_GID
    entry.uname = OWNER_NAME
    entry.gname = OWNER_NAME
    entry.mode = DIRECTORY_MODE if entry.isdir() else FILE_MODE
    return entry


def pack(version: str) -> Path:
    if not DIST_ROOT.is_dir():
        raise SystemExit("dist/ does not exist; run `just build` first")

    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    archive = RELEASE_ROOT / archive_name(version)
    prefix = f"agent-kit_v{version}"

    with archive.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=REPRODUCIBLE_MTIME
        ) as compressed:
            with tarfile.open(fileobj=compressed, mode="w|", format=tarfile.GNU_FORMAT) as bundle:
                for path in tracked_files(DIST_ROOT):
                    entry = bundle.gettarinfo(
                        str(path), arcname=f"{prefix}/{path.relative_to(DIST_ROOT).as_posix()}"
                    )
                    with path.open("rb") as handle:
                        bundle.addfile(normalise(entry), handle)
    return archive


def write_checksums(version: str, archive: Path) -> Path:
    checksums = RELEASE_ROOT / checksums_name(version)
    checksums.write_text(f"{sha256_of(archive)}  {archive.name}\n", encoding="utf-8")
    return checksums


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pack dist/ into the release tarball and write its checksum file"
    )
    parser.parse_args()

    version = read_version()
    archive = pack(version)
    checksums = write_checksums(version, archive)
    print(f"packed {archive.relative_to(REPO_ROOT)} ({archive.stat().st_size} bytes)")
    print(f"wrote {checksums.relative_to(REPO_ROOT)}")
    print(checksums.read_text(encoding="utf-8").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
