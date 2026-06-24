import argparse
import sys
from pathlib import Path

from minibrain.__about__ import __version__
from minibrain.context import DEFAULT_CONFIG_PATH, Context
from minibrain.utils.fs import resolve_path
from minibrain.utils.misc import register_exit_signals

logger = Context.logger


def prepare_context(raw_args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="genlist", description="Kiwix Minibrain Mirrors listing (json)"
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
        "--to",
        help="File to write JSON to (otherwise printed on stdout)",
        type=resolve_path,
        default=None,
        dest="to_path",
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
    debug = Context.debug
    try:
        args = prepare_context(sys.argv[1:])
        context = Context.get()
        debug = context.debug
        register_exit_signals()

        from minibrain.db import database
        from minibrain.tools.genlist import gen_json_mirrorlist

        try:
            database.connect()
            return gen_json_mirrorlist(
                to_path=None
                if args.to_path and args.to_path.name == "-"
                else (args.to_path or None)
            )

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
