#!/usr/bin/env python3

import argparse
import logging
import re
import sys
import tempfile
from pathlib import Path

from rich.logging import RichHandler

PATTERN = re.compile(r"^(?P<ident>.+)_(?P<date>\d{4}-\d{2}).zim$")

logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
)
logger = logging.getLogger("zim-map")


def run(root: Path, map_path: Path, prefix: str, *, dry_run: bool) -> int:
    logger.info(
        f"Creating ZIM redirects map from {root!s} to {map_path!s} with {dry_run=}"
    )

    # build sorted list of all files
    zim_files: list[Path] = sorted(
        {
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file() and PATTERN.match(path.name)
        },
        reverse=True,
    )

    # create the map using ident and first found version (sorted means first is last)
    zim_map: dict[str, str] = {}
    for path in zim_files:
        ident = path.stem.rsplit("_", 1)[0]
        if ident not in zim_map:
            zim_map[ident] = str(path)

    logger.debug(f"> {len(zim_map):,} entries in map.")

    tmp_file = Path(
        tempfile.NamedTemporaryFile(
            prefix=f"{map_path.stem}_",
            suffix=map_path.suffix,
            dir=map_path.parent,
            delete=False,
        ).name
    )
    try:
        with open(tmp_file, "w") as fh:
            for ident, path in zim_map.items():
                for suffix in (
                    "",
                    ".torrent",
                    ".meta4",
                    ".metalink",
                    ".magnet",
                    ".md5",
                    ".sha256",
                    ".sha1",
                    ".btih",
                ):
                    line = f"{prefix}/{ident}.zim{suffix} {prefix}/{path}{suffix}\n"
                    logger.debug(line.strip())
                    fh.write(line)

        if dry_run:
            logger.info("DRY-RUN, no change to map file.")
            return 0

        tmp_file.chmod(0o644)
        tmp_file.rename(map_path)
    finally:
        tmp_file.unlink(missing_ok=True)

    logger.info(f"Updated {map_path!s} with {len(zim_map):,} entries.")
    return 0


def entrypoint() -> int:
    parser = argparse.ArgumentParser(
        description="Create an apache map of version-less ZIM filename to last path"
    )

    parser.add_argument(
        "--prefix",
        default="/zim",
        help="On-server prefix for ZIM URLs",
        dest="prefix",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Only list version folders to be deleted, dont actually delete.",
        dest="dry_run",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Debug output",
        dest="debug",
    )

    parser.add_argument(help="ZIM data folder", dest="zim_dir", type=Path)
    parser.add_argument(help="Path to the target folder", dest="map_path", type=Path)

    args = parser.parse_args()
    if args.debug:
        logger.setLevel(logging.DEBUG)
    return run(
        root=args.zim_dir.expanduser().resolve(),
        map_path=args.map_path.expanduser().resolve(),
        prefix=args.prefix,
        dry_run=args.dry_run,
    )


if __name__ == "__entrypoint__":
    sys.exit(entrypoint())
