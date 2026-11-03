"""Small JSON logging setup with credential redaction."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

SAFE_FIELDS = (
    "component",
    "symbol",
    "candle_ts",
    "prediction_id",
    "model_version",
    "latency_ms",
    "error_code",
)
SECRET_ENV_NAMES = ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY")


class JsonLogFormatter(logging.Formatter):
    """Emit concise JSON records and redact configured credential values."""

    def __init__(self, secret_values: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secret_values = tuple(value for value in secret_values if value)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            for secret in self._secret_values:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {key: self._redact(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._redact(item) for item in value]
        return value

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat(
            timespec="milliseconds"
        )
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "severity": record.levelname,
            "component": record.name,
            "event": self._redact(record.getMessage()),
        }
        for field_name in SAFE_FIELDS:
            if hasattr(record, field_name):
                payload[field_name] = self._redact(getattr(record, field_name))
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_json_logging(level: str | None = None) -> None:
    """Configure root logging for concise JSON events, never including raw tracebacks."""
    secret_values = tuple(os.environ.get(name, "") for name in SECRET_ENV_NAMES)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter(secret_values))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel((level or os.environ.get("LOG_LEVEL", "INFO")).upper())
