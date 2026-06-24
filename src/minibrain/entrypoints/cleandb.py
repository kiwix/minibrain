import argparse
import sys
from pathlib import Path

from minibrain.__about__ import __version__
from minibrain.context import DEFAULT_CONFIG_PATH, Context
from minibrain.utils.misc import register_exit_signals

logger = Context.logger
ACTIONS = ("info", "vacuum", "vacuum-full", "sync-master")


def prepare_context(raw_args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cleandb", description="Kiwix Minibrain DB cleaner"
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
        "--dry-run",
        help="Don't make any change to DB",
        action="store_true",
        dest="dry_run",
    )

    parser.add_argument(
        "--debug",
        help="Enable verbose output",
        action="store_true",
        default=Context.debug,
    )

    parser.add_argument(
        help="What to do",
        choices=ACTIONS,
        dest="action",
    )

    parser.add_argument(
        "--master",
        help="Mirror ID of master mirror for sync-master",
        dest="master_mirror",
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
    debug = Context.debug
    try:
        args = prepare_context(sys.argv[1:])
        context = Context.get()
        debug = context.debug
        register_exit_signals()

        from minibrain.db import database
        from minibrain.tools.cleandb import (
            dbinfo,
            syncmaster,
            vacuum,
        )

        try:
            database.connect()

            match args.action:
                case "info":
                    return dbinfo(dry_run=args.dry_run)
                case "vacuum":
                    return vacuum(dry_run=args.dry_run, full=False)
                case "vacuum-full":
                    return vacuum(dry_run=args.dry_run, full=True)
                case "sync-master":
                    if not args.master_mirror:
                        raise OSError("--master required for sync-master")
                    return syncmaster(master=args.master_mirror, dry_run=args.dry_run)
                case _:
                    return dbinfo(dry_run=True)

        finally:
            database.close()
    except Exception as exc:
        logger.error(f"General failure: {exc!r}")
        if debug:
            logger.exception(exc)
        return 1


def entrypoint():
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
