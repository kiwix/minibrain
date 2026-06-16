#!/usr/bin/env python3

"""Maintain an copy of a file tree with only sparse file.

Goal is only to allow mod_mirrorbrain to think it's tied to an actual filetree
and do its load-balancing job."""

# /// script
# dependencies = [
#   "rich==15.0.0",
#   "humanfriendly==10.0"
# ]
# ///

import argparse
import logging
import os
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType

from humanfriendly import format_size
from rich.logging import RichHandler

__version__ = "1.0"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
)
logger = logging.getLogger("sync")


def perms_to_mode(perms: str) -> int:
    """Unix file mode from human-readable string"""
    mode = 0

    ftype_mode = {
        "l": stat.S_IFLNK,
        "s": stat.S_IFSOCK,
        "-": stat.S_IFREG,
        "b": stat.S_IFBLK,
        "d": stat.S_IFDIR,
        "c": stat.S_IFCHR,
        "p": stat.S_IFIFO,
    }.get(perms[0])
    if ftype_mode:
        mode |= ftype_mode

    # owner
    for index, perm in enumerate(("r", "w", "x")):
        if perms[1 + index] == perm:
            mode |= getattr(stat, f"S_I{perm.upper()}USR")
    # setuid
    if perms[3] == "s":
        mode |= stat.S_ISUID
    # setuid AND +x
    elif perms[3] == "S":
        mode |= stat.S_ISUID | stat.S_IXUSR

    # group
    for index, perm in enumerate(("r", "w", "x")):
        if perms[4 + index] == perm:
            mode |= getattr(stat, f"S_I{perm.upper()}GRP")

    # setgid
    if perms[6] == "S":
        mode |= stat.S_ISGID
    # setgid AND +x
    elif perms[6] == "s":
        mode |= stat.S_ISGID | stat.S_IXGRP

    # other
    for index, perm in enumerate(("r", "w", "x")):
        if perms[7 + index] == perm:
            mode |= getattr(stat, f"S_I{perm.upper()}OTH")

    # sticky bit
    if perms[9] == "T":
        mode |= stat.S_ISVTX
    # sticky bit AND +x
    elif perms[9] == "t":
        mode |= stat.S_ISVTX | stat.S_IXOTH

    return mode


def is_world_readable(mode: int) -> bool:
    """whether mode reflects a world-readable file"""
    return mode | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH == mode


def parse_args(raw_args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sparse-sync", description="Minibrain sparse-sync"
    )

    parser.add_argument(dest="remote_source", help="Rsync source")
    parser.add_argument(
        dest="local_dest", help="Path to store/maintain tree in", type=Path
    )

    parser.add_argument(
        "--exclude",
        help="rsync exclude pattern",
        action="append",
        dest="excludes",
        default=[],
    )

    parser.add_argument(
        "--dry-run",
        help="Don't make any change to DB",
        action="store_true",
        dest="dry_run",
        default=False,
    )

    parser.add_argument(
        "--debug",
        help="Enable verbose output",
        action="store_true",
        default=False,
    )

    parser.add_argument(
        "--debug-rsync",
        help="Print all rsync response lines",
        action="store_true",
        default=False,
        dest="debug_rsync",
    )

    parser.add_argument(
        "--version",
        help="Display version and exit",
        action="version",
        version=__version__,
    )

    return parser.parse_args(raw_args)


def main() -> int:
    try:
        args = parse_args(sys.argv[1:])
        logger.setLevel(logging.DEBUG if args.debug else logging.INFO)

        def exit_gracefully(signum: int, frame: FrameType | None):  # noqa: ARG001
            print("\n", flush=True)  # noqa: T201
            logger.info(f"Received {signal.Signals(signum).name}/{signum}. Exiting")
            sys.exit(4)

        signal.signal(signal.SIGTERM, exit_gracefully)
        signal.signal(signal.SIGINT, exit_gracefully)
        signal.signal(signal.SIGQUIT, exit_gracefully)

        return sync_tree(
            remote_source=args.remote_source,
            local_dest=args.local_dest,
            excludes=args.excludes,
            dry_run=args.dry_run,
            debug=args.debug,
            debug_rsync=args.debug_rsync,
        )
    except Exception as exc:
        logger.error(f"General failure: {exc!r}")
        logger.exception(exc)
        return 1


def create_sparse(fpath: Path, size: int):
    """ creates a sparse file of provided size"""
    # only write a single byte at end of file.
    # supported by most modern filesystems
    with open(fpath, "wb") as fp:
        if size == 0:
            fp.truncate()
            return
        fp.seek(size - 1)
        fp.write(b"\0")


class RsyncChange:
    def __init__(self, text: str, operation: str) -> None:
        (
            self.action,
            self.ftype,  # ignoring D (device) and S (special)
            self.checksum,
            self.size,
            self.time,
            self.perms,
            # we don't care about following owner, group, acl
        ) = text[:6]

        # fix the action char based on operation
        # as `<` is supposed to be ~sent~ and `>` ~received~
        # but is the opposite on current rsync client/server.
        if operation == "sent":
            self.action = "<"
        if operation == "recv":
            self.action = ">"

    def __str__(self) -> str:
        return "".join(
            [self.action, self.ftype, self.checksum, self.size, self.time, self.perms]
        )

    @property
    def is_sent(self) -> bool:
        return self.action == "<"

    @property
    def is_received(self) -> bool:
        return self.action == ">"

    @property
    def needs_local(self) -> bool:
        return self.action == "c"

    @property
    def is_hardlink(self) -> bool:
        return self.action == "h"

    @property
    def is_not_updated(self) -> bool:
        return self.action == "."

    @property
    def is_file(self) -> bool:
        return self.ftype == "f"

    @property
    def is_dir(self) -> bool:
        return self.ftype == "d"

    @property
    def is_symlink(self) -> bool:
        return self.ftype == "L"

    def has_changed_for(self, attr: str) -> bool:
        return getattr(self, attr) != "."

    @property
    def is_new(self) -> bool:
        return all(
            field == "+" for field in [self.checksum, self.size, self.time, self.perms]
        )

    @property
    def has_changed(self) -> bool:
        return any(
            [
                self.checksum_changed,
                self.size_changed,
                self.time_changed,
                self.perms_changed,
            ]
        )

    @property
    def checksum_changed(self) -> bool:
        return self.has_changed_for("checksum")

    @property
    def size_changed(self) -> bool:
        return self.has_changed_for("size")

    @property
    def time_changed(self) -> bool:
        return self.has_changed_for("time")

    @property
    def perms_changed(self) -> bool:
        return self.has_changed_for("perms")


@dataclass(kw_only=True)
class SyncStat:
    created_dir: int = 0
    updated_dir: int = 0
    removed_dir: int = 0
    created_file: int = 0
    updated_file: int = 0
    removed_file: int = 0

    @classmethod
    def any_update(cls) -> bool:
        return sum([getattr(cls, key) for key in cls.__dataclass_fields__.keys()]) > 0

    @classmethod
    def summary(cls) -> str:
        parts: list[str] = []
        for key in cls.__dataclass_fields__.keys():
            if getattr(cls, key):
                parts.append(f"{key}: {getattr(cls, key):,}")
        return ", ".join(parts)


def sync_tree(
    remote_source: str,
    local_dest: Path,
    excludes: list[str],
    *,
    dry_run: bool,
    debug: bool,  # noqa: ARG001
    debug_rsync: bool,
) -> int:
    local_dest.mkdir(parents=True, exist_ok=True)

    command = [
        "rsync",
        "--no-motd",
        # not -a because we don't want --devices --specials --owner --group
        "--recursive",
        "--links",
        "--perms",
        "--times",
        # upstream may have world-writable files/directories, but that doesn't mean
        # that we want that locally
        "--chmod=o-w",
        "--out-format=%o %B %i %M %l %n%L",
        "--delete",
        "--ignore-errors",
        "--dry-run",
    ]
    for exclude in excludes:
        command += ["--exclude", exclude]

    command += [
        remote_source,
        str(local_dest).rstrip("/"),
    ]

    logger.debug(f"rsync command: {' '.join(command)}")
    rsync = subprocess.run(args=command, capture_output=True, text=True, check=False)
    if rsync.returncode != 0:
        logger.critical(f"rsync returned {rsync.returncode}")
        logger.error(rsync.stdout)
        rsync.check_returncode()

    # remember directories to set mtime afterwards
    dir_timestamp_map: dict[Path, int] = {}

    # recv -rw-r--r--  <f+++++++ 2024/08/13-00:20:22 4678 zimit/abc.zim -> xyz.zim
    for line in rsync.stdout.splitlines():
        if debug_rsync:
            logger.debug(line)

        if "->" in line:  # symlink
            line, symlink = line.split(" -> ", 1)  # noqa: PLW2901
        elif "=>" in line:  # hardlink
            line, _ = line.split(" => ", 1)  # noqa: PLW2901
            symlink = ""
        else:
            symlink = ""
        operation, perms, attrs_s, mtime_s, size_s, path = line.rsplit(maxsplit=5)

        # some servers can send perms as file-mode only
        perms = perms.strip()
        # file perms only
        if len(perms) <= 9:  # noqa: PLR2004
            ft = "-"
            if path.endswith("/"):
                ft = "d"
            elif symlink:
                ft = "l"
            perms = f"{ft}{perms}"
        mode = perms_to_mode(perms)

        size = int(size_s)
        timestamp = int(time.mktime(time.strptime(mtime_s, "%Y/%m/%d-%H:%M:%S")))
        fpath = local_dest.joinpath(path)
        fpath_to: Path | None = local_dest.joinpath(symlink) if symlink else None
        attrs = RsyncChange(attrs_s, operation=operation)

        # in case a previous symlink is now a directory
        if attrs.is_dir and fpath.is_symlink():
            logger.debug("removing link {fpath}, to be replaced by directory")
            fpath.unlink()

        # make sure we don't escape the target folder
        for p in (fpath, fpath_to):
            if p and not p.resolve().relative_to(local_dest):
                logger.error(f"Resolved path {p} ends up outside root {local_dest}")
                return 1

        match operation:  # send, recv, del.
            case "del.":
                if stat.S_ISDIR(mode):
                    logger.debug(f"[{dry_run=}] unlinking directory {path}")
                    fpath.rmdir()
                    SyncStat.removed_dir += 1
                else:
                    logger.debug(f"[{dry_run=}] unlinking file {path}")
                    fpath.unlink()
                    SyncStat.removed_file += 1

            case "recv":
                if attrs.is_sent:
                    logger.debug(f"ignoring {attrs!s} {fpath}")
                    continue

                if attrs.is_dir:
                    if attrs.is_new and attrs.is_received:
                        logger.debug(f"[{dry_run=}] creating directory {fpath}")
                        if not dry_run:
                            fpath.mkdir(parents=True, exist_ok=True, mode=mode)
                            SyncStat.created_dir += 1
                            dir_timestamp_map[fpath] = timestamp
                    elif attrs.time_changed:
                        dir_timestamp_map[fpath] = timestamp

                if attrs.needs_local and attrs.is_symlink:
                    if fpath_to:
                        logger.debug(
                            f"[{dry_run=}] creating symlink from {fpath} to {fpath_to}"
                        )
                        if not dry_run:
                            SyncStat.created_file += 1
                            fpath.symlink_to(fpath_to)
                    else:
                        logger.error(f"missing {fpath_to=} on symlink: {line}")
                        return 1

                if not attrs.is_new and attrs.has_changed:
                    # we dont want to pollute logs with mtime change on root
                    if attrs.is_dir and path != "./":
                        SyncStat.updated_dir += 1
                    elif attrs.is_file or attrs.is_symlink:
                        SyncStat.updated_file += 1

                if attrs.is_file and attrs.size_changed:
                    logger.debug(
                        f"[{dry_run=}] creating sparse file {fpath} "
                        f"with size={format_size(size)}"
                    )
                    if not dry_run:
                        create_sparse(fpath=fpath, size=size)
                        SyncStat.created_file += 1

                if attrs.perms_changed and not attrs.is_symlink:
                    logger.debug(f"[{dry_run=}] {fpath}: setting mode ({mode})")
                    if not dry_run:
                        fpath.chmod(mode)

                if attrs.is_file and (attrs.time_changed or attrs.size_changed):
                    logger.debug(f"[{dry_run=}] {fpath}: setting mtime ({mtime_s})")
                    if not dry_run:
                        os.utime(fpath, times=(timestamp, timestamp))

            case _:
                raise NotImplementedError(f"unknown operation {operation}. {line=}")

    if dir_timestamp_map:
        logger.debug("Setting mtime on changed directories after file updates")
        for fpath, timestamp in dir_timestamp_map.items():
            logger.debug(f"[{dry_run=}] setting mtime on {fpath}")
            if not dry_run:
                os.utime(fpath, times=(timestamp, timestamp))

    if SyncStat.any_update():
        logger.info(f"{SyncStat.summary()}")

    return 0


def entrypoint():
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
