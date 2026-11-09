"""
Thread-safe way to keep yfinance quiet.

yfinance reports 404s / "possibly delisted" through the logging module. Silencing those loggers once is safe
with any number of threads. (The previous approach, contextlib.redirect_stderr, swaps the process-wide
sys.stderr; with several fetch threads one thread restores a /dev/null handle another thread already closed,
which crashes the process with "lost sys.stderr".)
"""

import logging

_NOISY_LOGGERS = ("yfinance", "peewee", "urllib3.connectionpool")


def silence_yfinance_logging() -> None:
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.CRITICAL)
