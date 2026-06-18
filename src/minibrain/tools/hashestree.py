from collections.abc import Iterable
from pathlib import Path

from minibrain.context import Context
from minibrain.db import database
from minibrain.utils.db import get_mb_version
from minibrain.utils.fs import create_sparse
from minibrain.utils.misc import format_size_long, format_ts

context = Context.get()
logger = context.logger


def pullhashestree(*, source_path: Path, target_path: Path, dry_run: bool) -> int:
    context = Context.get()

    logger.info(f"Starting mirrorprobe for {context.dsn}")
    logger.info(f"Connected to mirrorbrain DB version {get_mb_version()}")

    target_path.mkdir(parents=True, exist_ok=True)

    source_files: set[Path] = {
        file for file in target_path.rglob("*") if file.is_file(follow_symlinks=False)
    }

    nb_rows: int = next(  # pyright: ignore[reportUnknownVariableType]
        database.execute_sql(  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType]
            "SELECT COUNT(*) FROM hash INNER JOIN filearr ON hash.file_id = filearr.id;"
        )
    )[0]

    logger.info(
        f"Found {nb_rows:,} rows in DB and {len(source_files):,} files in source"
    )

    cursor: Iterable[tuple[int, str, int, int]] = database.execute_sql(  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        "SELECT file_id, filearr.path, size, mtime "
        "FROM hash INNER JOIN filearr ON hash.file_id = filearr.id;",
        (),
    )
    for file_id, path, size, mtime in cursor:  # pyright: ignore
        logger.debug(
            f"fid={file_id}: {path}, {format_size_long(size)}, {format_ts(mtime)}" # pyright: ignore[reportUnknownArgumentType]
        )  # pyright: ignore[reportUnknownArgumentType]
        source_file = source_path.joinpath(path)  # pyright: ignore[reportUnknownArgumentType]
        target_file = target_path.joinpath(path)  # pyright: ignore[reportUnknownArgumentType]

        # not in source anymore: ignore
        if not source_file.exists():
            logger.debug("> not in source, skipping")
            continue

        if not dry_run:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            create_sparse(fpath=target_file, size=size, mtime=mtime)  # pyright: ignore[reportUnknownArgumentType]

    return 0
