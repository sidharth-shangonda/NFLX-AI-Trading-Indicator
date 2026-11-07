"""Alpaca IEX stream adapter isolated in a dedicated thread.

The SDK's ``StockDataStream.run()`` owns an asyncio event loop, so it must not
run inside FastAPI's active loop. This module never opens an order/trading API.
"""

from __future__ import annotations

import email.utils
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pandas as pd
import requests

from live.service import LiveIndicatorService

LOGGER = logging.getLogger("alpaca_ingestor")
TEST_STREAM_URL: Final = "wss://stream.data.alpaca.markets/v2/test"
TEST_SYMBOL: Final = "FAKEPACA"


class IngestorError(RuntimeError):
    """Raised when a requested stream mode or payload is unsafe."""


def normalize_stream_bar(payload: Any, *, symbol: str) -> dict[str, Any]:
    """Convert Alpaca object/dict bar payloads into the one shared bar schema."""
    source = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    aliases = {
        "timestamp": ("timestamp", "t"),
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c"),
        "volume": ("volume", "v"),
        "trade_count": ("trade_count", "n"),
        "vwap": ("vwap", "vw"),
    }
    result: dict[str, Any] = {"symbol": source.get("symbol", source.get("S", symbol))}
    for target, choices in aliases.items():
        value = next(
            (source.get(choice) for choice in choices if source.get(choice) is not None),
            None,
        )
        if target in {"trade_count", "vwap"}:
            result[target] = value
            continue
        if value is None:
            raise IngestorError(f"stream bar is missing {target}")
        result[target] = value
    result["symbol"] = str(result["symbol"])
    timestamp = pd.Timestamp(result["timestamp"])
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)
    result["timestamp"] = timestamp.isoformat()
    return result


def clock_offset_seconds(http_date: str, *, now: datetime | None = None) -> float:
    """Compute local-minus-provider clock offset from a standard HTTP Date header."""
    parsed = email.utils.parsedate_to_datetime(http_date)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    return float((reference.astimezone(UTC) - parsed.astimezone(UTC)).total_seconds())


def fetch_clock_offset(
    *,
    key_id: str,
    secret_key: str,
    request: Callable[..., Any] = requests.get,
) -> float | None:
    """Use a harmless data request Date header; return None if unavailable."""
    response = request(
        "https://data.alpaca.markets/v2/stocks/NFLX/bars",
        headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key},
        params={"timeframe": "1Min", "limit": 1, "feed": "iex"},
        timeout=10,
    )
    header = response.headers.get("Date")
    return clock_offset_seconds(header) if header else None


@dataclass
class AlpacaIEXIngestor:
    """Reconnectable one-connection data-only stream runner."""

    service: LiveIndicatorService
    key_id: str
    secret_key: str
    mode: str = "live"
    on_status: Callable[[str, dict[str, Any]], None] | None = None
    stream_factory: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"live", "test"}:
            raise IngestorError("stream mode must be live or test")
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._active_stream: Any | None = None

    def _status(self, state: str, **details: Any) -> None:
        LOGGER.info(state, extra={"component": "ingestor"})
        if self.on_status is not None:
            self.on_status(state, details)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise IngestorError("only one stream connection may run per ingestor")
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="alpaca-iex-stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._active_stream is not None:
            stop = getattr(self._active_stream, "stop", None)
            if callable(stop):
                stop()

    def _stream(self) -> Any:
        if self.stream_factory is not None:
            return self.stream_factory()
        from alpaca.data.enums import DataFeed
        from alpaca.data.live import StockDataStream

        kwargs: dict[str, Any] = {
            "api_key": self.key_id,
            "secret_key": self.secret_key,
            "feed": DataFeed.IEX,
        }
        if self.mode == "test":
            kwargs["url_override"] = TEST_STREAM_URL
        return StockDataStream(**kwargs)

    def _run(self) -> None:
        backoff_seconds = 1.0
        while not self._stopping.is_set():
            stream = self._stream()
            self._active_stream = stream
            symbol = TEST_SYMBOL if self.mode == "test" else self.service.symbol

            async def handle(payload: Any, selected_symbol: str = symbol) -> None:
                bar = normalize_stream_bar(payload, symbol=selected_symbol)
                source = "test_stream" if self.mode == "test" else "live_iex"
                self.service.ingest_bar(bar, source=source)
                self.service.finalize_due(now=pd.Timestamp.now(tz=UTC))

            try:
                stream.subscribe_bars(handle, symbol)
                stream.subscribe_updated_bars(handle, symbol)
                self._status("TEST STREAM" if self.mode == "test" else "LIVE-IEX")
                stream.run()
                if not self._stopping.is_set():
                    self._status("DISCONNECTED")
            except Exception as exc:  # pragma: no cover - network behavior is externally owned
                message = str(exc)
                status_code = getattr(exc, "status_code", None)
                if status_code == 429 or "rate limit" in message.lower():
                    state = "RATE LIMIT"
                elif "auth" in message.lower() or status_code in {401, 403}:
                    state = "AUTH ERROR"
                else:
                    state = "DISCONNECTED"
                self._status(state, error_type=type(exc).__name__)
            finally:
                self._active_stream = None
            if not self._stopping.is_set():
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2.0, 30.0)
