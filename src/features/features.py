"""Causal technical features for final five-minute candles."""

from __future__ import annotations

import numpy as np
import pandas as pd

NEW_YORK = "America/New_York"
FEATURE_COLUMNS = (
    "return_1",
    "return_3",
    "return_12",
    "realized_vol_12",
    "range_mean_12",
    "atr_14",
    "ema_fast_distance",
    "ema_slow_distance",
    "rsi_14",
    "macd",
    "macd_signal",
    "bollinger_position_20",
    "bollinger_width_20",
    "relative_volume_20",
    "time_of_day_sin",
    "time_of_day_cos",
    "gap_from_previous_session",
)


class FeatureBuildError(ValueError):
    """Raised when candles cannot safely produce the shared feature schema."""


def _sorted_candles(candles: pd.DataFrame) -> pd.DataFrame:
    required = {
        "candle_start",
        "session_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "n_minutes",
    }
    missing = required.difference(candles.columns)
    if missing:
        raise FeatureBuildError(f"candles are missing required columns: {sorted(missing)}")
    result = candles.copy()
    result["candle_start"] = pd.to_datetime(result["candle_start"], utc=True, errors="coerce")
    if result["candle_start"].isna().any():
        raise FeatureBuildError("candles contain an invalid candle_start")
    if result["candle_start"].duplicated().any():
        raise FeatureBuildError("candles contain duplicate candle_start values")
    return result.sort_values("candle_start", kind="mergesort").reset_index(drop=True)


def _gap_from_previous_session(result: pd.DataFrame) -> pd.Series:
    real_candle = result["n_minutes"].gt(0)
    first_real = real_candle & real_candle.groupby(
        result["session_date"], sort=False
    ).cumsum().eq(1)
    first_real_open = result["open"].where(first_real).groupby(
        result["session_date"], sort=False
    ).ffill()
    session_last_close = result.groupby("session_date", sort=False)["close"].last()
    prior_session_close = session_last_close.shift(1)
    prior_by_row = result["session_date"].map(prior_session_close)
    return first_real_open / prior_by_row - 1.0


def add_causal_features(candles: pd.DataFrame) -> pd.DataFrame:
    """Append features that use only the current candle and prior candles.

    Leading warm-up values remain missing. The function never backward-fills or
    otherwise uses future candles, so it can be called identically in historical
    runs and on a live finalized-candle prefix.
    """
    result = _sorted_candles(candles)
    if result.empty:
        for column in FEATURE_COLUMNS:
            result[column] = pd.Series(dtype=float)
        result["features_ready"] = pd.Series(dtype=bool)
        return result

    close = result["close"].astype(float)
    high = result["high"].astype(float)
    low = result["low"].astype(float)
    volume = result["volume"].astype(float)
    previous_close = close.shift(1)
    returns = close.pct_change(fill_method=None)

    result["return_1"] = returns
    result["return_3"] = close.pct_change(3, fill_method=None)
    result["return_12"] = close.pct_change(12, fill_method=None)
    result["realized_vol_12"] = returns.rolling(12, min_periods=12).std(ddof=0)
    result["range_mean_12"] = ((high - low) / close).rolling(12, min_periods=12).mean()

    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    result["atr_14"] = true_range.rolling(14, min_periods=14).mean() / close

    ema_fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
    result["ema_fast_distance"] = close / ema_fast - 1.0
    result["ema_slow_distance"] = close / ema_slow - 1.0
    macd_raw = ema_fast - ema_slow
    result["macd"] = macd_raw / close
    result["macd_signal"] = (
        macd_raw.ewm(span=9, adjust=False, min_periods=9).mean() / close
    )

    gains = returns.clip(lower=0)
    losses = (-returns.clip(upper=0))
    average_gain = gains.rolling(14, min_periods=14).mean()
    average_loss = losses.rolling(14, min_periods=14).mean()
    relative_strength = average_gain / average_loss
    rsi = 100.0 - 100.0 / (1.0 + relative_strength)
    rsi = rsi.mask(average_loss.eq(0) & average_gain.gt(0), 100.0)
    rsi = rsi.mask(average_loss.eq(0) & average_gain.eq(0), 50.0)
    result["rsi_14"] = rsi

    rolling_mean = close.rolling(20, min_periods=20).mean()
    rolling_std = close.rolling(20, min_periods=20).std(ddof=0)
    upper_band = rolling_mean + 2.0 * rolling_std
    lower_band = rolling_mean - 2.0 * rolling_std
    result["bollinger_position_20"] = (close - lower_band) / (upper_band - lower_band)
    result["bollinger_width_20"] = (upper_band - lower_band) / rolling_mean
    result["relative_volume_20"] = volume / volume.rolling(20, min_periods=20).mean()

    local_time = result["candle_start"].dt.tz_convert(NEW_YORK)
    minutes_since_open = local_time.dt.hour * 60 + local_time.dt.minute - (9 * 60 + 30)
    time_angle = 2.0 * np.pi * minutes_since_open / 390.0
    result["time_of_day_sin"] = np.sin(time_angle)
    result["time_of_day_cos"] = np.cos(time_angle)
    result["gap_from_previous_session"] = _gap_from_previous_session(result)
    result["features_ready"] = result.loc[:, FEATURE_COLUMNS].notna().all(axis=1)
    return result
