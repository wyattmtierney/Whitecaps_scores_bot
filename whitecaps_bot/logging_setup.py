"""Logging configuration.

Railway marks everything written to stderr as an error, which is why every
line used to show up red. Logs now go to stdout as one JSON object per line,
which Railway parses so the ``level`` field sets the real severity and a
traceback stays in a single entry instead of 30 separate lines.

Set ``LOG_FORMAT=text`` for plain, human-readable logs when running locally.
"""
from __future__ import annotations

import json
import logging
import os
import sys

# Railway recognises: debug, info, warn, error.
_RAILWAY_LEVELS = {
    logging.DEBUG: "debug",
    logging.INFO: "info",
    logging.WARNING: "warn",
    logging.ERROR: "error",
    logging.CRITICAL: "error",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        return json.dumps(
            {
                "level": _RAILWAY_LEVELS.get(record.levelno, "info"),
                "message": message,
                "logger": record.name,
            },
            ensure_ascii=False,
        )


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if os.getenv("LOG_FORMAT", "json").lower() == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
