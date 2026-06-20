"""AvianVisitors - keep the illustration cutouts as a single tar in git.

The collage ships hundreds of transparent AVIF cutouts. Tracking them loose
bloats the repo with one file per species, so git holds a single
assets/illustrations.tar instead. photos.py unpacks it before a run and repacks
it after, build_masks.py unpacks it before reading, and the Docker build
extracts it into the image. The tar is written deterministically (sorted names,
zeroed mtime and ownership) so an unchanged set produces a byte-identical
archive and no spurious git diff.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ILLUS_DIR = REPO / "assets" / "illustrations"
TAR_PATH = REPO / "assets" / "illustrations.tar"


def tar_for(illus_dir: Path) -> Path:
    return illus_dir.parent / (illus_dir.name + ".tar")


def unpack(illus_dir: Path = ILLUS_DIR, tar_path: Path | None = None) -> int:
    """Extract any cutouts missing from illus_dir out of the tar, leaving
    existing files untouched. Returns the number restored."""
    tar_path = tar_path or tar_for(illus_dir)
    if not tar_path.exists():
        return 0
    illus_dir.mkdir(parents=True, exist_ok=True)
    restored = 0
    with tarfile.open(tar_path, "r") as tar:
        for member in tar.getmembers():
            if not member.isfile() or "/" in member.name or not member.name.endswith(".avif"):
                continue
            dest = illus_dir / member.name
            if dest.exists():
                continue
            src = tar.extractfile(member)
            if src is None:
                continue
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            try:
                with src, tmp.open("wb") as out:
                    out.write(src.read())
                tmp.replace(dest)
            finally:
                tmp.unlink(missing_ok=True)
            restored += 1
    return restored


def pack(illus_dir: Path = ILLUS_DIR, tar_path: Path | None = None) -> int:
    """Repack every cutout in illus_dir into the tar, atomically and
    deterministically. Returns the number packed."""
    tar_path = tar_path or tar_for(illus_dir)
    cutouts = sorted(p for p in illus_dir.glob("*.avif"))
    tmp = tar_path.with_suffix(tar_path.suffix + ".tmp")
    try:
        with tarfile.open(tmp, "w") as tar:
            for p in cutouts:
                info = tarfile.TarInfo(name=p.name)
                info.size = p.stat().st_size
                info.mtime = 0
                info.mode = 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                with p.open("rb") as fh:
                    tar.addfile(info, fh)
        tmp.replace(tar_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return len(cutouts)
