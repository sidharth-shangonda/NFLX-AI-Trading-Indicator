from __future__ import annotations

from datetime import UTC, datetime

from live.adapter import clock_offset_seconds, normalize_stream_bar


def test_stream_bar_normalizes_sdk_field_names_and_timezone() -> None:
    bar = normalize_stream_bar(
        {
            "timestamp": datetime(2026, 11, 2, 14, 30, tzinfo=UTC),
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100.5,
            "volume": 10,
            "trade_count": 2,
            "vwap": 100.25,
        },
        symbol="NFLX",
    )
    assert bar["symbol"] == "NFLX"
    assert bar["timestamp"] == "2026-11-02T14:30:00+00:00"


def test_clock_offset_uses_provider_http_date() -> None:
    local = datetime(2026, 11, 2, 14, 30, 2, tzinfo=UTC)
    offset = clock_offset_seconds("Mon, 02 Nov 2026 14:30:00 GMT", now=local)
    assert offset == 2.0
