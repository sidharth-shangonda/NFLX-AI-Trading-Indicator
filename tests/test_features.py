from __future__ import annotations

import numpy as np
import pandas as pd

from features import FEATURE_COLUMNS, add_causal_features


def _candles_for_features() -> pd.DataFrame:
    first_starts = pd.date_range("2026-11-02T14:30:00Z", periods=78, freq="5min")
    second_starts = pd.date_range("2026-11-03T14:30:00Z", periods=40, freq="5min")
    starts = first_starts.append(second_starts)
    closes = pd.Series(np.arange(100.0, 100.0 + len(starts)))
    sessions = ["2026-11-02"] * len(first_starts) + ["2026-11-03"] * len(second_starts)
    frame = pd.DataFrame(
        {
            "candle_start": starts,
            "session_date": sessions,
            "open": closes - 0.2,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": 100.0,
            "n_minutes": 5,
        }
    )
    frame.loc[82, ["n_minutes", "volume"]] = [0, 0]
    frame.loc[82, ["open", "high", "low", "close"]] = frame.loc[81, "close"]
    return frame


def test_features_are_causal_and_prefix_equals_historical_at_same_candle() -> None:
    candles = _candles_for_features()
    historical = add_causal_features(candles)
    position = 110
    prefix = add_causal_features(candles.iloc[: position + 1])

    pd.testing.assert_series_equal(
        historical.loc[position, list(FEATURE_COLUMNS)],
        prefix.loc[position, list(FEATURE_COLUMNS)],
        check_names=False,
    )

    future_changed = candles.copy()
    future_changed.loc[position + 1 :, ["open", "high", "low", "close"]] *= 10
    future_changed.loc[position + 1 :, "volume"] *= 100
    altered = add_causal_features(future_changed)
    pd.testing.assert_series_equal(
        historical.loc[position, list(FEATURE_COLUMNS)],
        altered.loc[position, list(FEATURE_COLUMNS)],
        check_names=False,
    )


def test_features_have_expected_basic_values_and_are_ready_only_after_warmup() -> None:
    featured = add_causal_features(_candles_for_features())

    assert pd.isna(featured.loc[0, "return_1"])
    assert np.isclose(featured.loc[1, "return_1"], 1 / 100)
    assert featured.loc[0, "time_of_day_sin"] == 0
    assert featured.loc[0, "time_of_day_cos"] == 1
    assert pd.isna(featured.loc[0, "gap_from_previous_session"])
    assert np.isclose(
        featured.loc[78, "gap_from_previous_session"],
        featured.loc[78, "open"] / featured.loc[77, "close"] - 1,
    )
    assert featured.loc[110, "features_ready"]
    assert all(not column.startswith("next_") for column in FEATURE_COLUMNS)
