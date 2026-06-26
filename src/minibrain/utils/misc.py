import datetime
import signal
import sys
from types import FrameType

import humanfriendly


def format_bandwidth(bps: int) -> str:
    return f"{humanfriendly.format_size(bps * 8, binary=False).replace('B', 'b')}ps"


def format_size(size: int, *, binary: bool = True) -> str:
    return humanfriendly.format_size(size, binary=binary)


def format_size_long(size: int, *, binary: bool = True) -> str:
    return f"{size!s} ({format_size(size=size, binary=binary)})"


def format_dt(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%d @ %H:%M:%S")  # noqa: RUF001


def format_ts(ts: int | float) -> str:
    return format_dt(datetime.datetime.fromtimestamp(ts, tz=datetime.UTC))


def format_timespan(seconds: int | float) -> str:
    return humanfriendly.format_timespan(seconds)


def exit_gracefully(signum: int, frame: FrameType | None):  # noqa: ARG001
    print("\n", flush=True)  # noqa: T201
    print(f"Received {signal.Signals(signum).name}/{signum}. Exiting")  # noqa: T201
    sys.exit(4)


def register_exit_signals():
    signal.signal(signal.SIGTERM, exit_gracefully)
    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGQUIT, exit_gracefully)
