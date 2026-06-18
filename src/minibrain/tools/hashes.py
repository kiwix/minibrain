import binascii
import datetime
import hashlib
import logging
import re
import shutil
from pathlib import Path

import psycopg
from filelock import FileLock
from peewee import PostgresqlDatabase
from rich.progress import track

from minibrain.context import Context
from minibrain.db import database
from minibrain.utils.db import get_mb_version
from minibrain.utils.fs import create_sparse
from minibrain.utils.misc import format_size, format_timespan, format_ts

context = Context.get()
logger = context.logger
logging.getLogger("filelock").setLevel(logging.INFO)


def get_single_int(db: PostgresqlDatabase, query: str, args: tuple[str | int]) -> int:
    try:
        return get_single(db, query, args)  # pyright:  ignore
    # no record returned
    except StopIteration:
        return 0


def get_single(
    db: PostgresqlDatabase, query: str, args: tuple[str | int]
) -> str | int | bytes | list[int]:
    return next(db.execute_sql(query, args))[0]  # pyright: ignore


def get_source_files(
    source_path: Path, base_path: Path, includes: list[str], excludes: list[str]
) -> set[Path]:
    """list of regular files in source folder,

    filtered on rel path (from base) using includes and excludes"""

    includes_re: list[re.Pattern[str]] = [re.compile(include) for include in includes]
    excludes_re: list[re.Pattern[str]] = [re.compile(exclude) for exclude in excludes]

    if not source_path.is_relative_to(base_path):
        raise OSError("Source path not with base path")

    files: set[Path] = set()
    for file in source_path.rglob("*"):
        # no folders, no symlinks
        if not file.is_file(follow_symlinks=False):
            continue

        relpath = str(file.relative_to(base_path))

        # if it matches an exclude, we discard it
        if any(exclude.search(relpath) for exclude in excludes_re):
            continue

        # if there is at least one include defined, we must discard any not matchin
        if includes_re and not any(include.search(relpath) for include in includes_re):
            continue

        files.add(file)

    return files


def get_target_files(target_path: Path) -> set[Path]:
    """list of regular file from target folder (recursive)"""
    return {
        file for file in target_path.rglob("*") if file.is_file(follow_symlinks=False)
    }


class HashBag:
    def __init__(self, fpath: Path, filesize: int, chunk_size: int) -> None:
        self.fpath = fpath
        self.filesize = filesize

        self.md5: bytes = b""

        self.sha1: bytes = b""
        self.sha1_piecesize: int = chunk_size
        self.sha1_pieces: list[bytes] = []

        self.sha256: bytes = b""
        self.btih: bytes = b""

        self.duration: int = 0

    @property
    def computed(self) -> bool:
        return bool(self.duration)

    @property
    def speed(self) -> int:
        """computation speed (in bps)"""
        return self.filesize // self.duration

    def compute(self):
        md5_digest = hashlib.new("md5", usedforsecurity=False)
        sha1_digest = hashlib.new("sha1", usedforsecurity=False)
        sha256_digest = hashlib.new("sha256", usedforsecurity=False)

        started_on = datetime.datetime.now(tz=datetime.UTC)

        with open(self.fpath, "rb") as fp:
            while True:
                buf = fp.read(self.sha1_piecesize)
                if not buf or len(buf) != self.sha1_piecesize:
                    break

                md5_digest.update(buf)
                sha1_digest.update(buf)
                sha256_digest.update(buf)

                self.sha1_pieces.append(
                    hashlib.sha1(buf, usedforsecurity=False).digest()
                )

        self.md5 = md5_digest.digest()
        self.sha1 = sha1_digest.digest()
        self.sha256 = sha256_digest.digest()
        self.btih = self.get_btih()
        self.duration = (
            int((datetime.datetime.now(tz=datetime.UTC) - started_on).total_seconds())
            or 1
        )

    def get_btih(self) -> bytes:
        parts: list[bytes] = [
            b"d",
            b"6:length",
            b"i",
            str(self.filesize).encode("ASCII"),
            b"e",
            b"6:md5sum",
            str(len(self.md5) * 2).encode("ASCII"),
            b":",
            binascii.hexlify(self.md5),
            b"4:name",
            str(len(self.fpath.name)).encode("ASCII"),
            b":",
            self.fpath.name.encode("UTF-8"),
            b"12:piece length",
            b"i",
            str(self.sha1_piecesize).encode("ASCII"),
            b"e",
            b"6:pieces",
            str(len(self.sha1_pieces) * len(self.sha1)).encode("ASCII"),
            b":",
            b"".join(self.sha1_pieces),
            b"4:sha1",
            str(len(self.sha1)).encode("ASCII"),
            b":",
            self.sha1,
            b"6:sha256",
            str(len(self.sha256)).encode("ASCII"),
            b":",
            self.sha256,
            b"e",
        ]
        return hashlib.sha1(b"".join(parts), usedforsecurity=False).digest()


def compute_hashes(fpath: Path, filesize: int | None = None) -> HashBag:
    """Collection of hashes for a file"""
    bag = HashBag(
        fpath=fpath,
        filesize=filesize if filesize is not None else fpath.stat().st_size,
        chunk_size=context.mb_chunk_size,
    )
    bag.compute()
    return bag


def record_hashes_in_db(
    db: PostgresqlDatabase, path: str, filesize: int, mtime: float, bag: HashBag
):
    """record in DB a file's hashes and metadata"""
    file_id: int = 0
    with db.atomic(isolation_level=psycopg.IsolationLevel.SERIALIZABLE):  # pyright: ignore
        file_id = get_single_int(
            db, "SELECT id FROM filearr WHERE path = %s LIMIT 1;", (path,)
        )

        # new file, we need to create it first
        if not file_id:
            file_id = get_single_int(
                db,
                "INSERT INTO filearr (path) VALUES (%s) RETURNING id;",
                (path,),
            )

        hash_exists = get_single_int(
            db, "SELECT COUNT(*) FROM hash WHERE file_id = %s LIMIT 1;", (file_id,)
        )

        hash_payload = (
            int(mtime),
            filesize,
            bag.md5,
            bag.sha1,
            bag.sha256,
            bag.sha1_piecesize,
            b"".join(bag.sha1_pieces),
            bag.btih,
            "",
            0,
            "",
            b"",
        )

        if not hash_exists:
            db.execute_sql(  # pyright: ignore[reportUnknownMemberType]
                "INSERT INTO hash "
                "(file_id, mtime, size, md5,"
                " sha1, sha256, sha1piecesize, sha1pieces, btih,"
                " pgp, zblocksize, zhashlens, zsums) "
                "VALUES (%s, %s, %s, %b, %b, %b, %s, %b, %b, %s, %s, %s, %b);",
                (file_id, *hash_payload),  # pyright: ignore
            )
        else:
            db.execute_sql(  # pyright: ignore[reportUnknownMemberType]
                "UPDATE hash SET "
                "mtime = %s, , size = %s, md5 = %b, sha1 = %b, sha256 = %b, "
                "sha1piecesize = %s, sha1pieces = %b, btih = %b, "
                "pgp = %s, zblocksize = %s, zhashlens = %s, zsums = %b) "
                "WHERE file_id = %s;",
                (*hash_payload, file_id),  # pyright: ignore
            )


def makehashes(
    *,
    source_path: Path,
    target_path: Path,
    base_path: Path,
    includes: list[str],
    excludes: list[str],
    dry_run: bool,
    force: bool,
) -> int:
    """get list of filepath, mtime and filesize from source (what's to mirror)

    find wich are not in DB
    compute and record"""

    context = Context.get()

    logger.info(f"Starting mirrorprobe for {context.dsn}")
    logger.info(f"Connected to mirrorbrain DB version {get_mb_version()}")

    # get list of source files
    source_files = get_source_files(
        source_path=source_path,
        base_path=base_path,
        includes=includes,
        excludes=excludes,
    )
    logger.info(f"Source contains {len(source_files):,} files")

    # get list of target files
    target_files = get_target_files(target_path=target_path)
    logger.info(f"Target contains {len(target_files):,} files")

    # remove from target fs if not in source
    for target_file in target_files:
        source_file = base_path.joinpath(target_file.relative_to(target_path))
        if not source_file.exists():
            logger.debug(f"Removing hash-file {target_file}: not in source anymore")
            if not dry_run:
                target_file.unlink()
    logger.info(f"Target now contains {len(target_files):,} files after cleanup")

    # stat() source and target and remove matching from list
    for source_file in set(source_files):
        target_file = target_path.joinpath(source_file.relative_to(base_path))

        # it's a new file, no need to query fs, we'll compute hashes
        if not target_file.exists():
            continue

        elif target_file.is_dir():
            # a previous folder is now a new file, we need to remove it
            logger.debug(f"Removing dir {target_file} in hash-tree: it's a file now")
            if not dry_run:
                shutil.rmtree(target_file)
            continue

        # keep file in to-compute regardless as requested
        if force:
            continue

        source_info = source_file.stat(follow_symlinks=False)
        target_info = target_file.stat(follow_symlinks=False)

        # source hasn't changed, discard this source file's ref, we wont compute
        # /!\ we compare mtime as ints because those are stored as int in DB
        if source_info.st_size == target_info.st_size and int(
            source_info.st_mtime
        ) == int(target_info.st_mtime):
            source_files.remove(source_file)

    logger.info(f"There are {len(source_files):,} files to compute hashes for")

    # remains list of new/updated files needing hashes
    for source_file in track(source_files, description="Making hashes…"):
        relpath = source_file.relative_to(base_path)
        target_file = target_path.joinpath(relpath)
        source_info = source_file.stat(follow_symlinks=False)
        logger.info(
            f"{relpath}, {format_size(source_info.st_size)} "
            f"{format_ts(source_info.st_mtime)}"
        )

        lock_file = target_file.with_suffix(f"{target_file.suffix}.lock")
        if lock_file.exists():
            logger.debug("Skipping {source_file} as there's a lock on disk")
            continue

        with FileLock(lock_file, timeout=0):
            logger.debug(f"Computing hashes for {source_file}")
            bag = compute_hashes(fpath=source_file, filesize=source_info.st_size)
            logger.debug(
                f"> {format_timespan(bag.duration)} at {format_size(bag.speed)}/s"
            )

            logger.debug(f"Recording hashes in DB for {relpath}")
            if not dry_run:
                record_hashes_in_db(
                    db=database,
                    path=str(source_file.relative_to(base_path)),
                    filesize=source_info.st_size,
                    mtime=source_info.st_mtime,
                    bag=bag,
                )

            logger.debug(f"Creating sparse {target_file}")
            if not dry_run:
                create_sparse(
                    fpath=target_file,
                    size=source_info.st_size,
                    mtime=source_info.st_mtime,
                )

    return 0
