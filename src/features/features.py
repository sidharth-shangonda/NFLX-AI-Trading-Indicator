"""Causal technical features for final five-minute candles."""

from __future__ import annotations

import numpy as np
import pandas as pd

NEW_YORK = "America/New_York"
FEATURE_COLUMNS = (
    "return_1",
    "return_2",
    "return_3",
    "return_5",
    "return_8",
    "return_12",
    "return_24",
    "ret_accel_1_2",
    "ret_accel_1_3",
    "body_ratio",
    "upper_shadow_ratio",
    "lower_shadow_ratio",
    "clv",
    "bar_range_pct",
    "realized_vol_6",
    "realized_vol_12",
    "realized_vol_20",
    "vol_ratio_6_20",
    "range_mean_12",
    "atr_14",
    "range_to_atr",
    "dist_ema_5",
    "ema_5_slope",
    "dist_ema_10",
    "ema_10_slope",
    "ema_fast_distance",
    "ema_slow_distance",
    "dist_ema_50",
    "ema_50_slope",
    "ema_5_20_spread",
    "rsi_7",
    "rsi_7_slope",
    "rsi_14",
    "rsi_14_slope",
    "stoch_k",
    "stoch_d",
    "macd",
    "macd_signal",
    "macd_hist",
    "macd_hist_slope",
    "bollinger_position_20",
    "bollinger_width_20",
    "relative_volume_20",
    "clv_vol",
    "vol_direction",
    "vwap_dist",
    "time_of_day_sin",
    "time_of_day_cos",
    "is_morning",
    "is_power_hour",
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
    first_real = real_candle & real_candle.groupby(result["session_date"], sort=False).cumsum().eq(
        1
    )
    first_real_open = (
        result["open"].where(first_real).groupby(result["session_date"], sort=False).ffill()
    )
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
    open_p = result["open"].astype(float)
    high = result["high"].astype(float)
    low = result["low"].astype(float)
    volume = result["volume"].astype(float)
    previous_close = close.shift(1)
    returns = close.pct_change(fill_method=None)

    # 1. Multi-horizon returns & acceleration
    result["return_1"] = returns
    result["return_2"] = close.pct_change(2, fill_method=None)
    result["return_3"] = close.pct_change(3, fill_method=None)
    result["return_5"] = close.pct_change(5, fill_method=None)
    result["return_8"] = close.pct_change(8, fill_method=None)
    result["return_12"] = close.pct_change(12, fill_method=None)
    result["return_24"] = close.pct_change(24, fill_method=None)
    result["ret_accel_1_2"] = result["return_1"] - (result["return_2"] - result["return_1"])
    result["ret_accel_1_3"] = result["return_1"] - (result["return_3"] / 3.0)

    # 2. Candlestick microstructure & shapes
    bar_range = (high - low).clip(lower=1e-5)
    result["body_ratio"] = (close - open_p) / bar_range
    result["upper_shadow_ratio"] = (high - np.maximum(open_p, close)) / bar_range
    result["lower_shadow_ratio"] = (np.minimum(open_p, close) - low) / bar_range
    result["clv"] = ((close - low) - (high - close)) / bar_range
    result["bar_range_pct"] = bar_range / close

    # 3. Volatility, ATR and ranges
    result["realized_vol_6"] = returns.rolling(6, min_periods=6).std(ddof=0)
    result["realized_vol_12"] = returns.rolling(12, min_periods=12).std(ddof=0)
    result["realized_vol_20"] = returns.rolling(20, min_periods=20).std(ddof=0)
    result["vol_ratio_6_20"] = result["realized_vol_6"] / (result["realized_vol_20"] + 1e-5)
    result["range_mean_12"] = ((high - low) / close).rolling(12, min_periods=12).mean()

    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    rolling_tr_14 = true_range.rolling(14, min_periods=14).mean()
    result["atr_14"] = rolling_tr_14 / close
    result["range_to_atr"] = (high - low) / (rolling_tr_14 + 1e-5)

    # 4. Moving averages & trend
    ema_5 = close.ewm(span=5, adjust=False, min_periods=5).mean()
    ema_10 = close.ewm(span=10, adjust=False, min_periods=10).mean()
    ema_fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema_slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
    ema_50 = close.ewm(span=50, adjust=False, min_periods=50).mean()

    result["dist_ema_5"] = close / ema_5 - 1.0
    result["ema_5_slope"] = ema_5.pct_change(3, fill_method=None)
    result["dist_ema_10"] = close / ema_10 - 1.0
    result["ema_10_slope"] = ema_10.pct_change(3, fill_method=None)
    result["ema_fast_distance"] = close / ema_fast - 1.0
    result["ema_slow_distance"] = close / ema_slow - 1.0
    result["dist_ema_50"] = close / ema_50 - 1.0
    result["ema_50_slope"] = ema_50.pct_change(3, fill_method=None)
    result["ema_5_20_spread"] = result["dist_ema_5"] - (close / ema_10 - 1.0)

    # 5. Oscillators (RSI, Stochastic, Bollinger, MACD)
    # RSI 7 and 14
    gains = returns.clip(lower=0)
    losses = -returns.clip(upper=0)

    avg_gain_7 = gains.rolling(7, min_periods=7).mean()
    avg_loss_7 = losses.rolling(7, min_periods=7).mean()
    rs_7 = avg_gain_7 / (avg_loss_7 + 1e-6)
    rsi_7 = 100.0 - 100.0 / (1.0 + rs_7)
    rsi_7 = rsi_7.mask(avg_loss_7.eq(0) & avg_gain_7.gt(0), 100.0)
    rsi_7 = rsi_7.mask(avg_loss_7.eq(0) & avg_gain_7.eq(0), 50.0)
    result["rsi_7"] = rsi_7
    result["rsi_7_slope"] = rsi_7.diff(2)

    avg_gain_14 = gains.rolling(14, min_periods=14).mean()
    avg_loss_14 = losses.rolling(14, min_periods=14).mean()
    rs_14 = avg_gain_14 / (avg_loss_14 + 1e-6)
    rsi_14 = 100.0 - 100.0 / (1.0 + rs_14)
    rsi_14 = rsi_14.mask(avg_loss_14.eq(0) & avg_gain_14.gt(0), 100.0)
    rsi_14 = rsi_14.mask(avg_loss_14.eq(0) & avg_gain_14.eq(0), 50.0)
    result["rsi_14"] = rsi_14
    result["rsi_14_slope"] = rsi_14.diff(2)

    # Stochastic Oscillator
    rolling_low_14 = low.rolling(14, min_periods=14).min()
    rolling_high_14 = high.rolling(14, min_periods=14).max()
    stoch_k = (close - rolling_low_14) / (rolling_high_14 - rolling_low_14 + 1e-6)
    result["stoch_k"] = stoch_k
    result["stoch_d"] = stoch_k.rolling(3, min_periods=3).mean()

    # MACD
    macd_raw = ema_fast - ema_slow
    macd_sig_raw = macd_raw.ewm(span=9, adjust=False, min_periods=9).mean()
    result["macd"] = macd_raw / close
    result["macd_signal"] = macd_sig_raw / close
    macd_hist = (macd_raw - macd_sig_raw) / close
    result["macd_hist"] = macd_hist
    result["macd_hist_slope"] = macd_hist.diff(2)

    # Bollinger Bands
    rolling_mean = close.rolling(20, min_periods=20).mean()
    rolling_std = close.rolling(20, min_periods=20).std(ddof=0)
    upper_band = rolling_mean + 2.0 * rolling_std
    lower_band = rolling_mean - 2.0 * rolling_std
    result["bollinger_position_20"] = (close - lower_band) / (upper_band - lower_band + 1e-6)
    result["bollinger_width_20"] = (upper_band - lower_band) / rolling_mean

    # 6. Volume & Order Flow proxies
    vol_mean_20 = volume.rolling(20, min_periods=20).mean()
    rel_vol_20 = volume / (vol_mean_20 + 1e-5)
    result["relative_volume_20"] = rel_vol_20
    result["clv_vol"] = result["clv"] * rel_vol_20
    result["vol_direction"] = np.sign(returns) * rel_vol_20

    # Intraday VWAP distance (purely causal session cumsum)
    cum_pv = (close * volume).groupby(result["session_date"], sort=False).cumsum()
    cum_vol = volume.groupby(result["session_date"], sort=False).cumsum()
    session_vwap = cum_pv / (cum_vol + 1e-5)
    result["vwap_dist"] = (close - session_vwap) / session_vwap

    # 7. Time and Calendar Features
    local_time = result["candle_start"].dt.tz_convert(NEW_YORK)
    minutes_since_open = local_time.dt.hour * 60 + local_time.dt.minute - (9 * 60 + 30)
    time_angle = 2.0 * np.pi * minutes_since_open / 390.0
    result["time_of_day_sin"] = np.sin(time_angle)
    result["time_of_day_cos"] = np.cos(time_angle)
    result["is_morning"] = (minutes_since_open <= 60).astype(float)
    result["is_power_hour"] = (minutes_since_open >= 330).astype(float)
    result["gap_from_previous_session"] = _gap_from_previous_session(result)

    result["features_ready"] = result.loc[:, FEATURE_COLUMNS].notna().all(axis=1)
    return result
