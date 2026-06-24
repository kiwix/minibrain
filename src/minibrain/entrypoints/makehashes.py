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
        prog="makehashes", description="Kiwix Minibrain hashes maker"
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
        "-b",
        "--base-dir",
        help="Base directory (allows working off a subdirectory)",
        type=resolve_path,
        dest="base_path",
    )

    parser.add_argument(
        help="Target directory (where to store hashes tree)",
        type=resolve_path,
        dest="target_path",
    )

    parser.add_argument(
        help="Source directory (where to find files to hash)",
        type=resolve_path,
        dest="source_path",
    )

    parser.add_argument(
        "--include",
        help=(
            "Pattern (regex) of path (from base) to include. "
            "Can be used multiple times. "
            "If set, skips every file not matched"
        ),
        action="append",
        dest="includes",
        type=str,
        default=[],
    )

    parser.add_argument(
        "--exclude",
        help=(
            "Pattern (regex) of path (from base) to exclude. "
            "Can be used multiple times."
        ),
        action="append",
        dest="excludes",
        type=str,
        default=[],
    )

    parser.add_argument(
        "--force",
        help="Force refreshing all cached hashes",
        action="store_true",
        default=False,
        dest="force",
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
        from minibrain.tools.hashes import makehashes

        try:
            database.connect()
            return makehashes(
                source_path=args.source_path,
                target_path=args.target_path,
                base_path=args.base_path or args.source_path,
                includes=args.includes,
                excludes=args.excludes,
                dry_run=args.dry_run,
                force=args.force,
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
