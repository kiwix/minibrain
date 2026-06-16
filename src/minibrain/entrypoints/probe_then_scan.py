import argparse
import sys
from pathlib import Path

from minibrain.__about__ import __version__
from minibrain.context import (
    DEFAULT_ALERTS,
    DEFAULT_CONFIG_PATH,
    AlertDestination,
    Context,
)
from minibrain.utils.misc import register_exit_signals

logger = Context.logger


def prepare_context(raw_args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="probe-then-scan", description="Probe a mirror then scan it if online"
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
        "--alert",
        help=(
            "Comma-separated list of alert `proto:address` destination. "
            "Only `slack` and `email` proto supported"
        ),
        action="append",
        dest="alerts",
        default=DEFAULT_ALERTS,
    )

    parser.add_argument(
        "--allow-insert",
        help="Trust this mirror's scanned files listing and insert File entry for each",
        action="store_true",
        dest="trusted_mirror",
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

    parser.add_argument(help="Mirror to scan", dest="mirror")

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

        from minibrain.db import database  # noqa: PLC0415
        from minibrain.tools.probe import mirrorprobe  # noqa: PLC0415
        from minibrain.tools.scan import mirrorscan  # noqa: PLC0415

        alerts: list[str] = args.alerts or []
        try:
            database.connect()
            mp = mirrorprobe(
                mirror_id=args.mirror,
                dry_run=False,
                enable_revived=False,
                alerts=[AlertDestination.parse(alert) for alert in alerts],
            )
            if mp != 0:
                return mp
            # probe succeeded, run scan
            return mirrorscan(
                mirror_id=args.mirror,
                dry_run=False,
                only_scan=False,
                trusted_mirror=args.trusted_mirror,
                enable=False,
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
