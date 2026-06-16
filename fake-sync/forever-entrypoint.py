#!/usr/bin/env python3

"""Loop forever running sync command at given interval while it works OK"""

import logging
import os
import signal
import subprocess
import sys
import time
from types import FrameType

from rich.logging import RichHandler

DEBUG: bool = bool(os.getenv("ENTRYPOINT_DEBUG", ""))
SLEEP_DURATION: int = int(os.getenv("SLEEP_DURATION", "60"))

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
)
logger = logging.getLogger("sync")
running: bool = True


def sleep_for(seconds: int | float):
    while seconds > 1:
        time.sleep(1)
        seconds -= 1


def exit_gracefully(signum: int, frame: FrameType | None):  # noqa: ARG001
    global running  # noqa: PLW0603
    running = False
    print("\n", flush=True)  # noqa: T201
    logger.info(f"Received {signal.Signals(signum).name}/{signum}. Exiting")
    sys.exit(4)


signal.signal(signal.SIGTERM, exit_gracefully)
signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGQUIT, exit_gracefully)


while running:
    sync = subprocess.run(["/usr/bin/env", *sys.argv[1:]], check=False)
    if sync.returncode != 0 or "--help" in sys.argv:
        sys.exit(sync.returncode)
    logger.debug(f"Awaiting {SLEEP_DURATION}s…")
    sleep_for(SLEEP_DURATION)
