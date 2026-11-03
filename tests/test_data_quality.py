from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from nflx_indicator.data_quality import regular_session_quality, split_adjustment_summary


def _regular_session_bars(day: datetime) -> pd.DataFrame:
    open_et = pd.Timestamp(day.date().isoformat() + " 09:30", tz="America/New_York")
    open_utc = open_et.tz_convert("UTC")
    timestamps = [open_utc + timedelta(minutes=minute) for minute in range(390) if minute >= 3]
    return pd.DataFrame(
        {
            "symbol": "NFLX",
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10,
        }
    )


def test_regular_session_quality_counts_missing_minutes_and_under_three_bins() -> None:
    start = pd.Timestamp("2026-11-02T00:00:00Z")
    end = pd.Timestamp("2026-11-03T00:00:00Z")
    frame = _regular_session_bars(datetime(2026, 11, 2, tzinfo=UTC))

    result = regular_session_quality(frame, start, end, min_minutes=3)

    assert result["expected_regular_minutes"] == 390
    assert result["missing_regular_minutes"] == 3
    assert result["regular_session_5m_candles"] == 78
    assert result["candles_below_min_minutes"] == 1
    assert result["candles_with_zero_minutes"] == 0
    assert result["off_grid_regular_timestamps"] == 0
    assert result["latest_complete_session"]["first_bar_et"].startswith("2026-11-02T09:33:00")


def test_split_adjustment_summary_checks_pre_and_post_split_factors() -> None:
    raw = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2025-11-14T14:30:00Z"),
                pd.Timestamp("2025-11-17T14:30:00Z"),
            ],
            "close": [1000.0, 100.0],
        }
    )
    adjusted = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2025-11-14T14:30:00Z"),
                pd.Timestamp("2025-11-17T14:30:00Z"),
            ],
            "close": [100.0, 100.0],
        }
    )

    result = split_adjustment_summary(raw, adjusted)

    assert result["status"] == "PASS"
    assert result["pre_split_adjusted_to_raw_close_factor"] == 0.1
    assert result["post_split_adjusted_to_raw_close_factor"] == 1.0
    assert result["no_approximately_10x_jump"]
