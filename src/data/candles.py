"""Build final five-minute NFLX candles from real one-minute IEX bars.

This is the single candle construction path for historical training and live
finalization. It deliberately operates on a NYSE session grid so that missing
minutes are explicit rather than silently forward-filled as market bars.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars

UTC: Final = "UTC"
NEW_YORK: Final = "America/New_York"
MINUTE_BAR_COLUMNS: Final = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
)
CANDLE_COLUMNS: Final = (
    "symbol",
    "candle_start",
    "candle_end",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
    "n_minutes",
    "is_filled",
    "prediction_eligible",
    "prediction_gate_reason",
)


class CandleBuildError(ValueError):
    """Raised when one-minute bars cannot make a deterministic candle grid."""


def _empty_candles() -> pd.DataFrame:
    return pd.DataFrame(columns=CANDLE_COLUMNS)


def _as_utc(value: pd.Timestamp | str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise CandleBuildError("start and end timestamps must be timezone-aware")
    return timestamp.tz_convert(UTC)


def _normalize_minute_bars(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(bars.columns)
    if missing:
        raise CandleBuildError(f"minute bars are missing required columns: {sorted(missing)}")

    normalized = bars.copy()
    for column in ("trade_count", "vwap"):
        if column not in normalized:
            normalized[column] = np.nan

    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True, errors="coerce")
    if normalized["timestamp"].isna().any():
        raise CandleBuildError("minute bars contain an invalid timestamp")
    normalized["timestamp"] = pd.DatetimeIndex(normalized["timestamp"]).as_unit("ns")

    for column in ("open", "high", "low", "close", "volume", "trade_count", "vwap"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    invalid_ohlcv = (
        normalized[["open", "high", "low", "close", "volume"]].isna().any(axis=1)
        | normalized["open"].le(0)
        | normalized["high"].lt(normalized[["open", "close", "low"]].max(axis=1))
        | normalized["low"].gt(normalized[["open", "close", "high"]].min(axis=1))
        | normalized["volume"].lt(0)
    )
    if invalid_ohlcv.any():
        raise CandleBuildError("minute bars contain invalid OHLCV values")

    if not normalized["timestamp"].eq(normalized["timestamp"].dt.floor("min")).all():
        raise CandleBuildError("minute-bar timestamps must be exact minute starts")

    symbols = normalized["symbol"].dropna().astype(str).unique()
    if len(symbols) > 1:
        raise CandleBuildError("a candle build accepts one symbol at a time")
    if not len(symbols):
        raise CandleBuildError("minute bars have no symbol")
    normalized["symbol"] = str(symbols[0])

    normalized["_input_order"] = np.arange(len(normalized))
    normalized = normalized.sort_values(
        ["timestamp", "_input_order"], kind="mergesort"
    ).reset_index(drop=True)

    duplicate_columns = [column for column in MINUTE_BAR_COLUMNS if column != "timestamp"]
    duplicate_rows = normalized["timestamp"].duplicated(keep=False)
    if duplicate_rows.any():
        for _, duplicate_group in normalized.loc[duplicate_rows].groupby("timestamp", sort=False):
            if len(duplicate_group[duplicate_columns].drop_duplicates()) != 1:
                raise CandleBuildError(
                    "conflicting duplicate minute bars must be reconciled before candle building"
                )
        normalized = normalized.drop_duplicates(subset="timestamp", keep="last")

    return normalized.loc[:, MINUTE_BAR_COLUMNS].reset_index(drop=True)


def _inferred_bounds(bars: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    first_day = bars["timestamp"].min().tz_convert(NEW_YORK).normalize()
    day_after_last = bars["timestamp"].max().tz_convert(NEW_YORK).normalize() + pd.Timedelta(days=1)
    return first_day.tz_convert(UTC), day_after_last.tz_convert(UTC)


def _complete_sessions(
    start: pd.Timestamp,
    end: pd.Timestamp,
    calendar_name: str,
) -> pd.DataFrame:
    calendar = market_calendars.get_calendar(calendar_name)
    schedule = calendar.schedule(
        start_date=start.tz_convert(NEW_YORK).date().isoformat(),
        end_date=end.tz_convert(NEW_YORK).date().isoformat(),
    )
    return schedule.loc[(schedule["market_open"] >= start) & (schedule["market_close"] <= end)]


def build_regular_session_candles(
    minute_bars: pd.DataFrame,
    *,
    start: pd.Timestamp | str | None = None,
    end: pd.Timestamp | str | None = None,
    min_minutes: int = 3,
    calendar_name: str = "NYSE",
) -> pd.DataFrame:
    """Build a regular-session 5-minute grid from real one-minute bars.

    Filled candles have zero real minutes, carry the prior grid close, and have
    zero volume. Leading empty candles are omitted only until the first real
    close exists. A conflicting duplicate minute bar is rejected because a live
    caller must first choose the final revision for that minute.
    """
    if not 1 <= min_minutes <= 5:
        raise CandleBuildError("min_minutes must be between 1 and 5")
    if minute_bars.empty:
        return _empty_candles()

    bars = _normalize_minute_bars(minute_bars)
    inferred_start, inferred_end = _inferred_bounds(bars)
    start_utc = _as_utc(start) if start is not None else inferred_start
    end_utc = _as_utc(end) if end is not None else inferred_end
    if end_utc <= start_utc:
        raise CandleBuildError("end must be after start")

    sessions = _complete_sessions(start_utc, end_utc, calendar_name)
    if sessions.empty:
        return _empty_candles()

    timestamps = pd.DatetimeIndex(bars["timestamp"])
    symbol = str(bars["symbol"].iloc[0])
    records: list[dict[str, object]] = []
    previous_grid_close: float | None = None
    five_minutes = pd.Timedelta(minutes=5)

    for session_day, session in sessions.iterrows():
        market_open = pd.Timestamp(session["market_open"]).tz_convert(UTC)
        market_close = pd.Timestamp(session["market_close"]).tz_convert(UTC)
        lo = timestamps.searchsorted(market_open, side="left")
        hi = timestamps.searchsorted(market_close, side="left")
        session_bars = bars.iloc[lo:hi].copy()
        candle_starts = pd.date_range(market_open, market_close, freq="5min", inclusive="left")

        if session_bars.empty:
            grouped: dict[int, pd.DataFrame] = {}
        else:
            offsets = session_bars["timestamp"].array.asi8 - market_open.as_unit("ns").value
            session_bars["_candle_index"] = offsets // five_minutes.value
            grouped = {
                int(index): group.sort_values("timestamp", kind="mergesort")
                for index, group in session_bars.groupby("_candle_index", sort=True)
            }

        prior_close = previous_grid_close
        for candle_index, candle_start in enumerate(candle_starts):
            real_bars = grouped.get(candle_index)
            if real_bars is None or real_bars.empty:
                if prior_close is None:
                    # The only dropped empties are before any prior close exists.
                    continue
                open_price = high_price = low_price = close_price = prior_close
                volume = 0.0
                trade_count = 0.0
                vwap = prior_close
                n_minutes = 0
                is_filled = True
            else:
                first_bar = real_bars.iloc[0]
                last_bar = real_bars.iloc[-1]
                open_price = float(first_bar["open"])
                high_price = float(real_bars["high"].max())
                low_price = float(real_bars["low"].min())
                close_price = float(last_bar["close"])
                volume = float(real_bars["volume"].sum())
                trade_count = (
                    float(real_bars["trade_count"].sum(min_count=1))
                    if real_bars["trade_count"].notna().any()
                    else np.nan
                )
                vwap_rows = real_bars.loc[real_bars["vwap"].notna()]
                if not vwap_rows.empty and vwap_rows["volume"].sum() > 0:
                    vwap = float(np.average(vwap_rows["vwap"], weights=vwap_rows["volume"]))
                else:
                    vwap = np.nan
                n_minutes = int(real_bars["timestamp"].nunique())
                is_filled = False

            prediction_eligible = n_minutes >= min_minutes
            records.append(
                {
                    "symbol": symbol,
                    "candle_start": candle_start,
                    "candle_end": candle_start + five_minutes,
                    "session_date": session_day.date().isoformat(),
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                    "trade_count": trade_count,
                    "vwap": vwap,
                    "n_minutes": n_minutes,
                    "is_filled": is_filled,
                    "prediction_eligible": prediction_eligible,
                    "prediction_gate_reason": (
                        None if prediction_eligible else f"thin_data_n_minutes_{n_minutes}"
                    ),
                }
            )
            prior_close = close_price

        if prior_close is not None:
            previous_grid_close = prior_close

    if not records:
        return _empty_candles()
    result = pd.DataFrame.from_records(records, columns=CANDLE_COLUMNS)
    result["candle_start"] = pd.to_datetime(result["candle_start"], utc=True)
    result["candle_end"] = pd.to_datetime(result["candle_end"], utc=True)
    return result
