# pyright: strict, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import argparse
import sys
from pathlib import Path

from peewee import DoesNotExist
from rich.console import Console
from rich.status import Status
from rich.table import Table
from rich.text import Text

from minibrain.__about__ import __version__
from minibrain.context import DEFAULT_CONFIG_PATH, DEFAULT_NB_MATCHING_FILES, Context
from minibrain.utils.misc import (
    format_dt,
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
        "-n",
        help=(
            f"Nb. of files to show in fuzzy mode. "
            f"Defaults to {DEFAULT_NB_MATCHING_FILES}"
        ),
        dest="nb_files",
        type=int,
        default=DEFAULT_NB_MATCHING_FILES,
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
            database.connect()
            if args.fuzzy:
                return print_search_results(path=args.path, max_results=args.nb_files)
            return print_fileinfo(path=args.path)
        finally:
            database.close()
    except Exception as exc:
        logger.error(f"General failure: {exc!r}")
        logger.exception(exc)
        return 1


def print_search_results(
    *, path: str, max_results: int = DEFAULT_NB_MATCHING_FILES
) -> int:
    from minibrain.db import Filearr, Hash
    from minibrain.utils.db import get_mirrors_summaries

    with Status(status="Querying database…"):
        nb_results = Filearr.select().where(Filearr.path**path).count()

    if not nb_results:
        logger.error(f"No results found for {path=}")
        return 1
    if nb_results == 1:
        return print_fileinfo(
            path=Filearr.select().where(Filearr.path**path).get().path
        )

    table = Table(title=f"{nb_results:,} DB results for {path} fuzzy=True")
    table.add_column("ID", justify="left", style="cyan", no_wrap=True)
    table.add_column("Size")
    table.add_column("Modified")
    table.add_column("Nb. mirrors")
    table.add_column("Path")

    with Status(status="Querying database…"):
        mirrors = get_mirrors_summaries()
        for file in Filearr.select().where(Filearr.path**path).limit(max_results):
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

    if nb_results > max_results:
        logger.info(
            f"There are {nb_results:,} results for this pattern. "
            f"Only showed {max_results:,}"
        )

    return 0


def print_fileinfo(*, path: str) -> int:

    from minibrain.utils.fileinfo import FileInfo, get_fileinfo

    with Status(status="Querying database…"):
        try:
            file: FileInfo = get_fileinfo(path=path)
        except DoesNotExist:
            logger.error(f"No file found with {path=}")
            return 1

    table = Table(title=f"DB results for {path} fuzzy=False")
    table.add_column("Meta", justify="left", style="cyan", no_wrap=True)
    table.add_column(f"{file.path}")

    mirrors_cell = Text(f"{len(file.mirrors)}")
    for mirror in file.mirrors:
        # mirror = mirrors[mirror_id]
        style = ""
        if not mirror.enabled:
            style = "dim"
        elif not mirror.online:
            style = "red"
        else:
            style = "green"
        mirrors_cell.append(f"\n{mirror.ident} ", style=style)
        mirrors_cell.append(f"({mirror.serving})")
        mirrors_cell.append("\n")
        mirrors_cell.append(f"{mirror.url}\n")

    table.add_row("File ID", f"{file.fileid}")
    table.add_row("Filename", f"{file.filename}")
    table.add_row("Folder", f"{file.folder}")
    table.add_row("Modified Time", f"{file.mtime} ({format_dt(file.mtime)})")
    table.add_row("Size", f"{format_size_long(file.size)}")
    table.add_row("Mirrors", mirrors_cell)
    table.add_row("md5", f"{file.md5}" if file.md5 else "-")
    table.add_row(
        "sha1",
        f"{file.sha1} {format_size_long(file.sha1_piecesize)}"
        if file.sha1 and file.sha1_piecesize
        else "-",
    )
    table.add_row("sha256", f"{file.sha256}" if file.sha256 else "-")
    table.add_row("btih", f"{file.btih}" if file.btih else "-")

    console = Console()
    console.print("")
    console.print(table)

    return 0


def entrypoint():
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
