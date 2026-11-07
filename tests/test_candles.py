from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from data.candles import CandleBuildError, build_regular_session_candles


def _bar(
    timestamp: str | pd.Timestamp,
    *,
    open_price: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    close: float = 100.5,
    volume: float = 10.0,
) -> dict[str, object]:
    return {
        "symbol": "NFLX",
        "timestamp": pd.Timestamp(timestamp),
        "open": open_price,
        "high": max(open_price, close) + 1 if high is None else high,
        "low": min(open_price, close) - 1 if low is None else low,
        "close": close,
        "volume": volume,
        "trade_count": 1.0,
        "vwap": close,
    }


def test_builder_uses_real_bar_ohlcv_and_fills_only_empty_grid_candles() -> None:
    bars = pd.DataFrame(
        [
            _bar("2026-11-02T14:30:00Z", open_price=100, high=102, low=99, close=101, volume=5),
            _bar("2026-11-02T14:31:00Z", open_price=101, high=104, low=100, close=103, volume=7),
            _bar("2026-11-02T14:34:00Z", open_price=103, high=105, low=101, close=104, volume=11),
        ]
    )

    candles = build_regular_session_candles(
        bars,
        start="2026-11-02T00:00:00Z",
        end="2026-11-03T00:00:00Z",
    )

    assert len(candles) == 78
    first = candles.iloc[0]
    assert first["n_minutes"] == 3
    assert not first["is_filled"]
    assert first["open"] == 100
    assert first["high"] == 105
    assert first["low"] == 99
    assert first["close"] == 104
    assert first["volume"] == 23
    assert first["prediction_eligible"]

    second = candles.iloc[1]
    assert second["n_minutes"] == 0
    assert second["is_filled"]
    assert second[["open", "high", "low", "close"]].tolist() == [104, 104, 104, 104]
    assert second["volume"] == 0
    assert second["prediction_gate_reason"] == "thin_data_n_minutes_0"


def test_builder_carries_prior_session_close_and_drops_only_initial_leading_empties() -> None:
    bars = pd.DataFrame(
        [
            _bar("2026-11-02T20:59:00Z", close=100, open_price=100, high=100, low=100),
            _bar("2026-11-03T14:35:00Z", close=102, open_price=101, high=103, low=101),
        ]
    )

    candles = build_regular_session_candles(
        bars,
        start="2026-11-02T00:00:00Z",
        end="2026-11-04T00:00:00Z",
    )

    assert len(candles) == 79
    assert candles.iloc[0]["candle_start"] == pd.Timestamp("2026-11-02T20:55:00Z")
    next_session_open = candles.loc[
        candles["candle_start"].eq(pd.Timestamp("2026-11-03T14:30:00Z"))
    ].iloc[0]
    assert next_session_open["n_minutes"] == 0
    assert next_session_open["close"] == 100
    assert next_session_open["is_filled"]


def test_builder_handles_dst_and_early_close_with_nyse_grid() -> None:
    dst_bars = pd.DataFrame([_bar("2026-11-02T14:30:00Z")])
    dst_candles = build_regular_session_candles(
        dst_bars,
        start="2026-11-02T00:00:00Z",
        end="2026-11-03T00:00:00Z",
    )
    assert len(dst_candles) == 78
    assert dst_candles.iloc[0]["candle_start"] == pd.Timestamp("2026-11-02T14:30:00Z")
    assert dst_candles.iloc[0]["candle_start"].tz_convert("America/New_York").hour == 9

    early_close_bars = pd.DataFrame([_bar("2026-11-27T14:30:00Z")])
    early_close_candles = build_regular_session_candles(
        early_close_bars,
        start="2026-11-27T00:00:00Z",
        end="2026-11-28T00:00:00Z",
    )
    assert len(early_close_candles) == 42
    assert early_close_candles.iloc[-1]["candle_start"] == pd.Timestamp("2026-11-27T17:55:00Z")


def test_builder_is_deterministic_for_unsorted_duplicate_and_extended_bars() -> None:
    real_bars = [
        _bar("2026-11-02T14:30:00Z", close=101),
        _bar("2026-11-02T14:31:00Z", close=102),
        _bar("2026-11-02T14:32:00Z", close=103),
    ]
    with_duplicate_and_extended = pd.DataFrame(
        [
            _bar("2026-11-02T13:00:00Z", close=1),
            real_bars[2],
            real_bars[0],
            real_bars[1],
            real_bars[1],
        ]
    )
    expected = build_regular_session_candles(
        pd.DataFrame(real_bars),
        start="2026-11-02T00:00:00Z",
        end="2026-11-03T00:00:00Z",
    )
    actual = build_regular_session_candles(
        with_duplicate_and_extended,
        start="2026-11-02T00:00:00Z",
        end="2026-11-03T00:00:00Z",
    )
    pd.testing.assert_frame_equal(actual, expected)

    conflicting = pd.DataFrame([real_bars[0], _bar("2026-11-02T14:30:00Z", close=999)])
    with pytest.raises(CandleBuildError, match="conflicting duplicate"):
        build_regular_session_candles(
            conflicting,
            start="2026-11-02T00:00:00Z",
            end="2026-11-03T00:00:00Z",
        )


def test_builder_counts_low_activity_candles_for_the_prediction_gate() -> None:
    open_et = pd.Timestamp("2026-11-02 09:30", tz="America/New_York")
    rows = []
    for candle_index, count in enumerate((1, 2, 3)):
        for minute in range(count):
            rows.append(_bar(open_et + timedelta(minutes=candle_index * 5 + minute)))
    candles = build_regular_session_candles(
        pd.DataFrame(rows),
        start="2026-11-02T00:00:00Z",
        end="2026-11-03T00:00:00Z",
        min_minutes=3,
    )

    assert candles.loc[:2, "n_minutes"].tolist() == [1, 2, 3]
    assert candles.loc[:2, "prediction_eligible"].tolist() == [False, False, True]
