# pyright: strict, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from peewee import DoesNotExist
from rich.console import Console
from rich.table import Table
from rich.text import Text

from minibrain.__about__ import __version__
from minibrain.context import DEFAULT_CONFIG_PATH, Context
from minibrain.utils.misc import (
    format_size,
    format_size_long,
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
        help="Path of the file in the DB",
        dest="path",
    )

    parser.add_argument(
        "--fuzzy",
        help="Consider the path fuzzy (not an exact match). Use `%%` for wildcards",
        action="store_true",
        dest="fuzzy",
        default=False,
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

        from minibrain.db import database  # noqa: PLC0415

        try:
            database.connect()
            if args.fuzzy:
                return print_search_results(path=args.path)
            return print_fileinfo(path=args.path)
        finally:
            database.close()
    except Exception as exc:
        logger.error(f"General failure: {exc!r}")
        logger.exception(exc)
        return 1


@dataclass
class MirrorSummary:
    ident: str
    baseurl: str
    status: bool
    enabled: bool


def get_mirrors() -> dict[int, MirrorSummary]:
    from minibrain.db import Server  # noqa: PLC0415

    return {
        server.id: MirrorSummary(
            ident=server.identifier,
            baseurl=server.baseurl,
            status=server.status_baseurl,
            enabled=server.enabled,
        )
        for server in Server.select()
    }


def print_search_results(*, path: str) -> int:
    from minibrain.db import Filearr, Hash  # noqa: PLC0415

    nb_results = Filearr.select().where(Filearr.path**path).count()

    if not nb_results:
        logger.error(f"No results found for {path=}")
        return 1
    if nb_results == 1:
        return print_fileinfo(
            path=Filearr.select().where(Filearr.path**path).get().path
        )
    mirrors = get_mirrors()

    max_results = 20
    has_more_results = nb_results > max_results

    table = Table(title=f"{nb_results:,} DB results for {path} fuzzy=True")
    table.add_column("ID", justify="left", style="cyan", no_wrap=True)
    table.add_column("Size")
    table.add_column("Modified")
    table.add_column("Nb. mirrors")
    table.add_column("Path")

    for file in Filearr.select().where(Filearr.path**path).limit(max_results):
        nbm = len(file.mirrors)
        nbm_disabled = len([1 for mid in file.mirrors if not mirrors[mid].enabled])
        nbm_online = len(
            [1 for mid in file.mirrors if mirrors[mid].status and mirrors[mid].enabled]
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

    if has_more_results:
        logger.info(
            f"There are {nb_results:,} results for this pattern. "
            f"Only showed {max_results:,}"
        )

    return 0


def print_fileinfo(*, path: str) -> int:
    from minibrain.db import Filearr, Hash  # noqa: PLC0415

    # list of mirror with metadata
    mirrors = get_mirrors()

    try:
        file = Filearr.get(Filearr.path == path)
        hashes = Hash.get(Hash.file == file)
    except DoesNotExist:
        logger.error(f"No file found with {path=}")
        return 1

    fpath = Path(file.path)

    table = Table(title=f"DB results for {path} fuzzy=False")

    table.add_column("Meta", justify="left", style="cyan", no_wrap=True)
    table.add_column(f"{fpath}")

    mirrors_cell = Text(f"{len(file.mirrors)}")
    for mirror_id in file.mirrors:
        mirror = mirrors[mirror_id]
        style = ""
        if not mirror.enabled:
            style = "dim"
        elif not mirror.status:
            style = "red"
        else:
            style = "green"
        url = f"{mirror.baseurl}{path}"
        mirrors_cell.append(f"\n{mirror.ident}", style=style)
        mirrors_cell.append("\n")
        mirrors_cell.append(f"{url}\n")

    table.add_row("File ID", f"{file.id}")
    table.add_row("Filename", f"{fpath.name}")
    table.add_row("Folder", f"{fpath.parent!s}")
    table.add_row("Modified Time", f"{hashes.mtime} ({format_ts(hashes.mtime)})")
    table.add_row("Size", f"{format_size_long(hashes.size)}")
    table.add_row("Mirrors", mirrors_cell)
    table.add_row("md5", f"{hashes.md5.hex()}")
    table.add_row(
        "sha1", f"{hashes.sha1.hex()} {format_size_long(hashes.sha1piecesize)}"
    )
    table.add_row("sha256", f"{hashes.sha256.hex()}")
    table.add_row("btih", f"{hashes.btih.hex()}")

    console = Console()
    console.print("")
    console.print(table)

    return 0


def entrypoint():
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
