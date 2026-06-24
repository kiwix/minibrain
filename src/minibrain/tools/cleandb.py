# pyright: strict, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import datetime
import logging

from peewee import PostgresqlDatabase
from rich.console import Console
from rich.status import Status
from rich.table import Table

from minibrain.context import Context
from minibrain.db import database
from minibrain.utils.db import get_mb_version
from minibrain.utils.misc import format_size, format_timespan

context = Context.get()
logger = context.logger
logging.getLogger("filelock").setLevel(logging.INFO)


def get_single_int(
    db: PostgresqlDatabase, query: str, args: tuple[str | int] | None
) -> int:
    return get_single(db, query, args)  # pyright:  ignore


def get_single(
    db: PostgresqlDatabase, query: str, args: tuple[str | int]
) -> str | int | bytes | list[int]:
    return next(db.execute_sql(query, args))[0]  # pyright: ignore


def dbinfo(*, dry_run: bool) -> int:  # noqa: ARG001
    context = Context.get()

    logger.info(f"Starting mirrorprobe for {context.dsn}")
    logger.debug(f"Connected to mirrorbrain DB version {get_mb_version()}")

    autovacuum_enabled = (
        next(
            database.execute_sql(
                "SELECT setting FROM pg_settings WHERE name='autovacuum';"
            )
        )[0]
        == "on"
    )

    table = Table(title="Minibrain DB stats")

    table.add_column("Table", justify="left", style="cyan", no_wrap=True)
    table.add_column("Size", justify="right")
    table.add_column("nb_dead_tup", justify="right")
    table.add_column("last_vacuum", justify="right")
    table.add_column(f"last_autovacuum (enabled={autovacuum_enabled})", justify="right")

    with Status("Querying DB…"):
        table_size_map: dict[str, int] = {}
        cursor = database.execute_sql(
            "SELECT relname, pg_table_size(C.oid) "
            "FROM pg_class C "
            "LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace) "
            "WHERE nspname NOT IN ('pg_catalog', 'information_schema') "
            "AND nspname !~ '^pg_toast' AND relkind IN ('r');"
        )

        for name, size in cursor:
            table_size_map[name] = size

        cursor = database.execute_sql(
            "SELECT relname, n_dead_tup, last_vacuum, last_autovacuum "
            "FROM pg_stat_user_tables;"
        )
        for name, nb_dead_tup, last_vacuum, last_auto_vacuum in cursor:
            table.add_row(
                name,
                f"{format_size(table_size_map[name])}",
                f"{nb_dead_tup:,}",
                f"{last_vacuum}",
                f"{last_auto_vacuum}",
            )

    console = Console()
    console.print("")
    console.print(table)

    return 0


def vacuum(*, dry_run: bool, full: bool = False) -> int:
    context = Context.get()

    logger.info(f"Starting mirrorprobe for {context.dsn}")
    logger.debug(f"Connected to mirrorbrain DB version {get_mb_version()}")
    query = "VACUUM FULL;" if full else "VACUUM;"

    if dry_run:
        logger.error(f"[{dry_run=}] Unable to {query} with --dry-run")

    started_on = datetime.datetime.now(tz=datetime.UTC)

    with Status(status="Querying database…"):
        database.execute_sql(query)

    duration = (datetime.datetime.now(tz=datetime.UTC) - started_on).total_seconds()

    logger.info(f"{query} completed in {format_timespan(duration)}")

    return 0


def syncmaster(*, master: str, dry_run: bool) -> int:
    context = Context.get()

    logger.info(f"Starting mirrorprobe for {context.dsn}")
    logger.debug(f"Connected to mirrorbrain DB version {get_mb_version()}")

    nb_files_master = get_single_int(
        db=database, query="SELECT mirr_get_nfiles(%s);", args=(master,)
    )
    nb_files_total = get_single_int(
        db=database, query="SELECT COUNT(*) FROM filearr;", args=None
    )
    nb_hash_total = get_single_int(
        db=database, query="SELECT COUNT(*) FROM hash;", args=None
    )
    nb_to_delete_files = get_single_int(
        db=database,
        query=(
            "SELECT COUNT(*) FROM filearr "
            "WHERE NOT (SELECT id from server where identifier = %s) = ANY(mirrors);"
        ),
        args=(master,),
    )

    table = Table(title="Minibrain DB files")

    table.add_column("Entries", justify="left", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right")

    table.add_row("filearr table", f"{nb_files_total:,}")
    table.add_row("hash table", f"{nb_hash_total:,}")
    table.add_row(f"on {master}", f"{nb_files_master:,}")

    console = Console()
    console.print("")
    console.print(table)

    if dry_run:
        logger.error(f"[{dry_run=}] There are {nb_to_delete_files:,} files to delete")
        return 0

    started_on = datetime.datetime.now(tz=datetime.UTC)

    with Status(status="Querying database…"):
        database.execute_sql(
            "DELETE FROM filearr "
            "WHERE NOT (SELECT id from server where identifier = %s) = ANY(mirrors);",
            (master,),
        )

    duration = (datetime.datetime.now(tz=datetime.UTC) - started_on).total_seconds()

    logger.info(f"Clean up completed in {format_timespan(duration)}")

    return 0
