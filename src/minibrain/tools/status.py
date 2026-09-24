# pyright: strict, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from peewee import PostgresqlDatabase
from rich.console import Console
from rich.status import Status
from rich.table import Table
from rich.text import Text

from minibrain.context import Context
from minibrain.utils.db import get_mb_version
from minibrain.utils.misc import format_bandwidth, format_dt, format_size
from minibrain.utils.status import Status as LBStatus
from minibrain.utils.status import get_status

context = Context.get()
logger = context.logger


def get_single_int(db: PostgresqlDatabase, query: str, args: tuple[str | int]) -> int:
    return get_single(db, query, args)  # pyright:  ignore


def get_single(
    db: PostgresqlDatabase, query: str, args: tuple[str | int]
) -> str | int | bytes | list[int]:
    return next(db.execute_sql(query, args))[0]  # pyright: ignore


def mbstatus() -> int:

    context = Context.get()

    logger.info(f"Starting status for {context.dsn}")
    logger.warning(f"Connected to mirrorbrain DB version {get_mb_version()}")

    with Status(status="Querying database…"):
        status: LBStatus = get_status()

    table = Table(title="Minibrain Status")

    table.add_column("Mirror", justify="left", style="cyan", no_wrap=True)
    table.add_column("Status")
    table.add_column("Nb. files", justify="right", style="green")
    table.add_column("Last scan", justify="right", style="")
    table.add_column("Size", justify="right", style="")
    table.add_column("Score/speed", justify="left", style="")
    table.add_column("ID", justify="right", style="")
    table.add_column("Serving", justify="left", style="")

    for server in status.mirrors:
        style = "dim" if not server.enabled else ""
        table.add_row(
            Text(f"{server.ident}", style=style),
            Text("DISABLED", style=style)
            if not server.enabled
            else (
                Text("ONLINE", style="green")
                if server.online
                else Text("OFFLINE", style="red")
            ),
            Text(f"{server.nb_files:,}", style=style),
            Text(
                f"{format_dt(server.last_scan_on) if server.last_scan_on else 'n/a'}",
                style=style,
            ),
            Text(format_size(server.total_size)),
            Text(
                # score is median speed / 1024 unless a fixed (low) value
                f"{format_bandwidth(server.score * 1024)}"
                if server.score >= 1024  # noqa: PLR2004
                else f"{server.score:,}"
            ),
            Text(f"{server.dbid}"),
            Text(f"{server.serving}"),
        )

    console = Console()
    console.print("")
    console.print(table)

    return 0
