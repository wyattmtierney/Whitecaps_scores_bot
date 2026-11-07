import json
import logging

from whitecaps_bot.logging_setup import JsonFormatter


def _record(level, msg, exc_info=None):
    return logging.LogRecord("whitecaps_bot.test", level, __file__, 1, msg, None, exc_info)


def test_json_formatter_maps_levels_for_railway():
    fmt = JsonFormatter()
    assert json.loads(fmt.format(_record(logging.INFO, "hello")))["level"] == "info"
    assert json.loads(fmt.format(_record(logging.WARNING, "careful")))["level"] == "warn"
    assert json.loads(fmt.format(_record(logging.ERROR, "boom")))["level"] == "error"


def test_json_formatter_keeps_traceback_in_one_entry():
    try:
        raise ValueError("bad")
    except ValueError:
        import sys
        line = JsonFormatter().format(_record(logging.ERROR, "failed", sys.exc_info()))

    assert "\n" not in line  # one physical line per log entry
    payload = json.loads(line)
    assert payload["message"].startswith("failed\nTraceback")
    assert "ValueError: bad" in payload["message"]
    assert payload["logger"] == "whitecaps_bot.test"
