import argparse
import sys

import humanfriendly

from minibrain.__about__ import __version__
from minibrain.context import Context
from minibrain.utils.fs import resolve_path
from minibrain.utils.misc import (
    format_size,
    format_size_long,
    format_timespan,
    format_ts,
    register_exit_signals,
)

logger = Context.logger


def prepare_context(raw_args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="test-hash", description="Print hashes hex for a single file"
    )

    parser.add_argument(
        help="File to hash",
        type=resolve_path,
        dest="fpath",
    )

    parser.add_argument(
        "--version",
        help="Display version and exit",
        action="version",
        version=__version__,
    )

    args = parser.parse_args(raw_args)
    Context.setup(debug=True)
    return args


def main() -> int:
    debug = Context.debug
    try:
        args = prepare_context(sys.argv[1:])
        context = Context.get()
        debug = context.debug
        register_exit_signals()

        from minibrain.tools.hashes import HashBag

        fpath = args.fpath
        filesize = fpath.stat().st_size
        mtime = fpath.stat().st_mtime

        logger.info(f"Hashing {fpath} ({format_size(filesize)}…")
        bag = HashBag(
            fpath=args.fpath,
            filesize=filesize,
            chunk_size=humanfriendly.parse_size("4MiB"),
        )
        bag.compute()
        logger.info(f"""
md5           ={bag.md5.hex()}
sha1          ={bag.sha1.hex()}
sha1_piecesize={format_size_long(bag.sha1_piecesize)}
sha256        ={bag.sha256.hex()}
btih          ={bag.btih.hex()}

filename      ={fpath.name}
filesize      ={format_size_long(filesize)}
mtime         ={mtime} ({format_ts(mtime)})
duration      ={format_timespan(bag.duration)} at {format_size(bag.speed)}/s
""")

        return 0

    except Exception as exc:
        logger.error(f"General failure: {exc!r}")
        if debug:
            logger.exception(exc)
        return 1


def entrypoint():
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
