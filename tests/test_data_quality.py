from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from nflx_indicator.data_quality import (
    candle_diagnostics,
    compare_feed_candle_closes,
    regular_session_quality,
    split_adjustment_summary,
)


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


def test_candle_diagnostics_counts_bars_returns_and_volume_by_minute_count() -> None:
    open_et = pd.Timestamp("2026-11-02 09:30", tz="America/New_York")
    counts = [3, 1, 2, 4, 5]
    closes = [100.0, 100.0, 101.0, 101.0, 102.0]
    rows = []
    for candle_index, (count, close) in enumerate(zip(counts, closes, strict=True)):
        for minute_index in range(count):
            timestamp = open_et + timedelta(minutes=candle_index * 5 + minute_index)
            rows.append(
                {
                    "symbol": "NFLX",
                    "timestamp": timestamp.tz_convert("UTC"),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 10,
                }
            )
    frame = pd.DataFrame(rows)

    result = candle_diagnostics(
        frame,
        pd.Timestamp("2026-11-02T00:00:00Z"),
        pd.Timestamp("2026-11-03T00:00:00Z"),
    )

    assert result["candle_count"] == 78
    assert [result["n_minutes_distribution"][str(n)]["candles"] for n in range(6)] == [
        73,
        1,
        1,
        1,
        1,
        1,
    ]
    assert result["filled_candles"] == 73
    assert result["nonfilled_close_to_close_pairs"] == 4
    assert result["zero_return_pairs"] == 2
    assert result["zero_return_rate"] == 0.5
    assert result["return_and_volume_by_n_minutes"]["0"]["mean_volume"] == 0.0
    assert result["return_and_volume_by_n_minutes"]["1"]["mean_volume"] == 10.0


def test_feed_close_comparison_counts_only_candles_with_real_bars_in_both_feeds() -> None:
    open_et = pd.Timestamp("2026-11-02 09:30", tz="America/New_York")
    timestamps = [open_et.tz_convert("UTC") + timedelta(minutes=n) for n in range(390)]
    sip = pd.DataFrame({"timestamp": timestamps, "close": 100.0})
    iex = sip.copy()
    iex.loc[4, "close"] = 100.1

    result = compare_feed_candle_closes(
        iex,
        sip,
        pd.Timestamp("2026-11-02T00:00:00Z"),
        pd.Timestamp("2026-11-03T00:00:00Z"),
    )

    assert result["sessions_compared"] == 1
    assert result["both_real_candles"] == 78
    assert result["different_close_count"] == 1
    assert result["exact_match_count"] == 77


def test_zero_return_rate_includes_nonfilled_candle_after_filled_candle() -> None:
    open_et = pd.Timestamp("2026-11-02 09:30", tz="America/New_York")
    rows = []
    for minute_index in (0, 10):
        rows.append(
            {
                "symbol": "NFLX",
                "timestamp": (open_et + timedelta(minutes=minute_index)).tz_convert("UTC"),
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
                "volume": 10,
            }
        )
    result = candle_diagnostics(
        pd.DataFrame(rows),
        pd.Timestamp("2026-11-02T00:00:00Z"),
        pd.Timestamp("2026-11-03T00:00:00Z"),
    )

    assert result["nonfilled_close_to_close_pairs"] == 1
    assert result["zero_return_pairs"] == 1
    assert result["zero_return_rate"] == 1.0
