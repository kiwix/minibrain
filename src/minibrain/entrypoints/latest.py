# pyright: strict, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.status import Status
from rich.table import Table
from rich.text import Text

from minibrain.__about__ import __version__
from minibrain.context import DEFAULT_CONFIG_PATH, DEFAULT_NB_LATEST_FILES, Context
from minibrain.utils.misc import (
    format_size,
    format_ts,
    register_exit_signals,
)

logger = Context.logger


def prepare_context(raw_args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fileinfo", description="Print details about a File entry"
    )

    parser.add_argument(
        "-c",
        "--config",
        help="Config file to use",
        dest="fpath",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )

    parser.add_argument(
        "-i",
        "--instance",
        help="Config file to use",
        dest="instance_name",
        default="",
    )

    parser.add_argument(
        "-n",
        help=f"Nb. of files to query. Defaults to {DEFAULT_NB_LATEST_FILES}",
        dest="nb_files",
        type=int,
        default=DEFAULT_NB_LATEST_FILES,
    )

    parser.add_argument(
        "--debug",
        help="Enable verbose output",
        action="store_true",
        default=Context.debug,
    )

    parser.add_argument(
        "--version",
        help="Display version and exit",
        action="version",
        version=__version__,
    )

    args = parser.parse_args(raw_args)
    Context.from_file(
        fpath=args.fpath, instance_name=args.instance_name, debug=args.debug
    )
    return args


def main() -> int:
    try:
        args = prepare_context(sys.argv[1:])
        register_exit_signals()

        from minibrain.db import database

        try:
            return print_latest_files(nb_files=args.nb_files)
        finally:
            database.close()
    except Exception as exc:
        logger.error(f"General failure: {exc!r}")
        logger.exception(exc)
        return 1


def print_latest_files(*, nb_files: int) -> int:
    from minibrain.db import Filearr, Hash
    from minibrain.utils.db import get_mirrors_summaries

    table = Table(title=f"{nb_files:,} latest filearr entries")
    table.add_column("ID", justify="left", style="cyan", no_wrap=True)
    table.add_column("Size")
    table.add_column("Modified")
    table.add_column("Nb. mirrors")
    table.add_column("Path")

    with Status(status="Querying database…"):
        mirrors = get_mirrors_summaries()
        for file in Filearr.select().order_by(Filearr.id.desc()).limit(nb_files):  # pyright: ignore[reportAttributeAccessIssue]
            nbm = len(file.mirrors)
            nbm_disabled = len([1 for mid in file.mirrors if not mirrors[mid].enabled])
            nbm_online = len(
                [
                    1
                    for mid in file.mirrors
                    if mirrors[mid].status and mirrors[mid].enabled
                ]
            )
            hashes = Hash.get(Hash.file == file)
            mirrors_cell = Text(f"{nbm:,}")
            mirrors_cell.append("/")
            mirrors_cell.append(f"{nbm_disabled:,}", style="dim")
            mirrors_cell.append("/")
            mirrors_cell.append(f"{nbm_online:,}", style="green")
            table.add_row(
                f"{file.id}",
                f"{format_size(hashes.size)}",
                f"{format_ts(hashes.mtime)}",
                mirrors_cell,
                f"{file.path}",
            )

    console = Console()
    console.print("")
    console.print(table)

    return 0


def entrypoint():
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
