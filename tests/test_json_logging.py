from __future__ import annotations

import json
import logging

from nflx_indicator.json_logging import JsonLogFormatter


def test_json_log_redacts_known_credentials_and_keeps_safe_fields() -> None:
    record = logging.LogRecord(
        name="market_data",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="connected with %s",
        args=("private-secret",),
        exc_info=None,
    )
    record.component = "alpaca"
    record.symbol = "NFLX"
    record.api_key = "private-secret"

    output = JsonLogFormatter(("private-secret",)).format(record)
    payload = json.loads(output)

    assert payload["event"] == "connected with [REDACTED]"
    assert payload["component"] == "alpaca"
    assert payload["symbol"] == "NFLX"
    assert "private-secret" not in output
    assert "api_key" not in output
