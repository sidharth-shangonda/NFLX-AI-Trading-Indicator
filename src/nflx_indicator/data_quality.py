"""Historical-data quality checks against the NYSE regular-session calendar."""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars

from data.candles import build_regular_session_candles

NEW_YORK = "America/New_York"
UTC = "UTC"


def regular_session_quality(
    frame: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    min_minutes: int = 3,
) -> dict[str, Any]:
    """Count expected minutes and five-minute grid coverage for completed sessions."""
    start_utc = pd.Timestamp(start).tz_convert(UTC)
    end_utc = pd.Timestamp(end).tz_convert(UTC)
    timestamp_series = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    invalid_timestamp_rows = int(timestamp_series.isna().sum())
    timestamps = pd.DatetimeIndex(timestamp_series.dropna().sort_values()).as_unit("ns")
    first_day = start_utc.tz_convert(NEW_YORK).date().isoformat()
    last_day = end_utc.tz_convert(NEW_YORK).date().isoformat()
    schedule = market_calendars.get_calendar("NYSE").schedule(
        start_date=first_day, end_date=last_day
    )

    expected_minutes = 0
    missing_minutes = 0
    regular_rows = 0
    total_grid_candles = 0
    below_minute_candles = 0
    empty_candles = 0
    off_grid_rows = 0
    session_results = []
    latest_session = None

    for session_day, session in schedule.iterrows():
        market_open = pd.Timestamp(session["market_open"]).tz_convert(UTC)
        market_close = pd.Timestamp(session["market_close"]).tz_convert(UTC)
        if market_open < start_utc or market_close > end_utc:
            continue

        lo = timestamps.searchsorted(market_open, side="left")
        hi = timestamps.searchsorted(market_close, side="left")
        observed = timestamps[lo:hi]
        unique_observed = observed.unique().as_unit("ns")
        regular_rows += int(hi - lo)

        minute_grid = pd.date_range(market_open, market_close, freq="min", inclusive="left")
        missing = int(len(minute_grid.difference(unique_observed)))
        expected_minutes += len(minute_grid)
        missing_minutes += missing

        candle_grid = pd.date_range(market_open, market_close, freq="5min", inclusive="left")
        offsets_ns = unique_observed.asi8 - market_open.as_unit("ns").value
        minute_ns = pd.Timedelta(minutes=1).value
        on_minute = (
            (offsets_ns % minute_ns == 0)
            & (offsets_ns >= 0)
            & (offsets_ns < len(minute_grid) * minute_ns)
        )
        off_grid_rows += int(len(unique_observed) - np.count_nonzero(on_minute))
        minute_indices = offsets_ns[on_minute] // minute_ns
        buckets = minute_indices // 5
        counts = np.bincount(buckets.astype(int), minlength=len(candle_grid))
        low_count = int(np.count_nonzero(counts < min_minutes))
        empty_count = int(np.count_nonzero(counts == 0))
        total_grid_candles += len(candle_grid)
        below_minute_candles += low_count
        empty_candles += empty_count

        first_observed = unique_observed[0] if len(unique_observed) else None
        result = {
            "session_date": str(session_day.date()),
            "market_open_utc": market_open.isoformat(),
            "market_close_utc": market_close.isoformat(),
            "expected_minutes": len(minute_grid),
            "missing_minutes": missing,
            "five_minute_candles": len(candle_grid),
            "candles_below_minimum": low_count,
            "candles_empty": empty_count,
            "first_bar_utc": first_observed.isoformat() if first_observed is not None else None,
            "first_bar_et": (
                first_observed.tz_convert(NEW_YORK).isoformat()
                if first_observed is not None
                else None
            ),
            "first_bar_at_open": bool(first_observed is not None and first_observed == market_open),
            "off_grid_timestamps": int(len(unique_observed) - np.count_nonzero(on_minute)),
        }
        session_results.append(result)
        latest_session = result

    total_rows = len(frame)
    duplicate_rows = int(frame["timestamp"].duplicated(keep="first").sum())
    required_ohlc = frame[["open", "high", "low", "close", "volume"]]
    invalid_mask = (
        required_ohlc.isna().any(axis=1)
        | (frame["open"] <= 0)
        | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame["volume"] < 0)
    )
    share_below = below_minute_candles / total_grid_candles if total_grid_candles else None
    return {
        "row_count": total_rows,
        "regular_session_rows": regular_rows,
        "extended_or_outside_rows": total_rows - regular_rows,
        "duplicate_timestamp_rows": duplicate_rows,
        "invalid_ohlc_rows": int(invalid_mask.sum()),
        "invalid_timestamp_rows": invalid_timestamp_rows,
        "off_grid_regular_timestamps": off_grid_rows,
        "expected_regular_minutes": expected_minutes,
        "missing_regular_minutes": missing_minutes,
        "missing_minute_share": missing_minutes / expected_minutes if expected_minutes else None,
        "regular_session_5m_candles": total_grid_candles,
        "candles_below_min_minutes": below_minute_candles,
        "candles_below_min_minutes_share": share_below,
        "candles_with_zero_minutes": empty_candles,
        "min_minutes": min_minutes,
        "complete_sessions": session_results,
        "latest_complete_session": latest_session,
        "calendar_name": "NYSE",
        "timezone": NEW_YORK,
    }


def candle_diagnostics(
    frame: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    min_minutes: int = 3,
    split_cutoff: date = date(2025, 11, 17),
) -> dict[str, Any]:
    """Summarize the same shared 5-minute candle grid used by the project."""
    candle_frame = build_regular_session_candles(
        frame,
        start=start,
        end=end,
        min_minutes=min_minutes,
    )
    if candle_frame.empty:
        return {
            "candle_count": 0,
            "min_minutes": min_minutes,
            "split_cutoff": split_cutoff.isoformat(),
            "n_minutes_distribution": {
                str(n_minutes): {"candles": 0, "share": None} for n_minutes in range(6)
            },
            "filled_candles": 0,
            "filled_share": None,
            "below_min_minutes_by_month": {},
            "below_min_minutes_by_split_period": {},
            "below_min_minutes_by_time_bucket": {},
            "below_min_minutes_by_weekday": {},
            "nonfilled_close_to_close_pairs": 0,
            "zero_return_pairs": 0,
            "zero_return_rate": None,
            "return_and_volume_by_n_minutes": {},
        }

    candle_et = candle_frame["candle_start"].dt.tz_convert(NEW_YORK)
    candle_frame["month"] = candle_et.dt.strftime("%Y-%m")
    candle_frame["weekday"] = candle_et.dt.day_name()
    local_minutes = candle_et.dt.hour * 60 + candle_et.dt.minute
    candle_frame["time_bucket"] = np.select(
        [
            local_minutes.lt(10 * 60),
            local_minutes.ge(15 * 60 + 30),
        ],
        ["open_09:30-10:00", "close_15:30-16:00"],
        default="midday",
    )
    session_dates = pd.to_datetime(candle_frame["session_date"])
    candle_frame["split_period"] = np.where(
        session_dates.dt.date < split_cutoff,
        "before_2025-11-17",
        "on_or_after_2025-11-17",
    )
    candle_frame["close_to_close_return"] = candle_frame.groupby("session_date", sort=False)[
        "close"
    ].pct_change(fill_method=None)
    total = len(candle_frame)

    def summarize(group: pd.DataFrame) -> dict[str, Any]:
        count = len(group)
        below = int((group["n_minutes"] < min_minutes).sum()) if count else 0
        return {
            "candles": count,
            "below_min_minutes": below,
            "below_min_minutes_share": below / count if count else None,
        }

    def grouped_summaries(column: str) -> dict[str, Any]:
        return {
            str(key): summarize(group) for key, group in candle_frame.groupby(column, sort=True)
        }

    distribution = {}
    returns_by_count = {}
    for n_minutes in range(6):
        subset = candle_frame.loc[candle_frame["n_minutes"] == n_minutes]
        valid_returns = subset["close_to_close_return"].dropna().abs()
        distribution[str(n_minutes)] = {
            "candles": len(subset),
            "share": len(subset) / total if total else None,
        }
        returns_by_count[str(n_minutes)] = {
            "candles": len(subset),
            "return_observations": len(valid_returns),
            "mean_absolute_return_pct": (
                float(valid_returns.mean() * 100) if len(valid_returns) else None
            ),
            "mean_volume": float(subset["volume"].mean()) if len(subset) else None,
        }

    nonfilled_return_observations = candle_frame.loc[
        candle_frame["n_minutes"].gt(0) & candle_frame["close_to_close_return"].notna()
    ]
    zero_returns = int(nonfilled_return_observations["close_to_close_return"].eq(0).sum())
    filled_candles = int(candle_frame["is_filled"].sum()) if total else 0
    return {
        "candle_count": total,
        "min_minutes": min_minutes,
        "split_cutoff": split_cutoff.isoformat(),
        "n_minutes_distribution": distribution,
        "filled_candles": filled_candles,
        "filled_share": filled_candles / total if total else None,
        "below_min_minutes_by_month": grouped_summaries("month"),
        "below_min_minutes_by_split_period": grouped_summaries("split_period"),
        "below_min_minutes_by_time_bucket": grouped_summaries("time_bucket"),
        "below_min_minutes_by_weekday": grouped_summaries("weekday"),
        "nonfilled_close_to_close_pairs": len(nonfilled_return_observations),
        "zero_return_pairs": zero_returns,
        "zero_return_rate": (
            zero_returns / len(nonfilled_return_observations)
            if len(nonfilled_return_observations)
            else None
        ),
        "return_and_volume_by_n_minutes": returns_by_count,
    }


def compare_feed_candle_closes(
    iex_bars: pd.DataFrame,
    sip_bars: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    """Compare IEX and SIP real five-minute closes on the same NYSE session grid."""
    start_utc = pd.Timestamp(start).tz_convert(UTC)
    end_utc = pd.Timestamp(end).tz_convert(UTC)

    def prepare(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="coerce")
        result = result.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        result["timestamp"] = pd.DatetimeIndex(result["timestamp"]).as_unit("ns")
        return result

    iex = prepare(iex_bars)
    sip = prepare(sip_bars)
    schedule = market_calendars.get_calendar("NYSE").schedule(
        start_date=start_utc.tz_convert(NEW_YORK).date().isoformat(),
        end_date=end_utc.tz_convert(NEW_YORK).date().isoformat(),
    )
    comparison_frames = []
    five_minutes_ns = pd.Timedelta(minutes=5).value

    for session_day, session in schedule.iterrows():
        market_open = pd.Timestamp(session["market_open"]).tz_convert(UTC)
        market_close = pd.Timestamp(session["market_close"]).tz_convert(UTC)
        if market_open < start_utc or market_close > end_utc:
            continue
        candle_grid = pd.date_range(market_open, market_close, freq="5min", inclusive="left")

        feed_groups = []
        for feed_name, bars in (("iex", iex), ("sip", sip)):
            timestamps = pd.DatetimeIndex(bars["timestamp"])
            lo = timestamps.searchsorted(market_open, side="left")
            hi = timestamps.searchsorted(market_close, side="left")
            session_bars = bars.iloc[lo:hi].copy()
            if session_bars.empty:
                closes = pd.DataFrame(
                    columns=[
                        "candle_index",
                        f"{feed_name}_count",
                        f"{feed_name}_close",
                    ]
                )
            else:
                offsets = session_bars["timestamp"].array.asi8 - market_open.as_unit("ns").value
                session_bars["candle_index"] = offsets // five_minutes_ns
                closes = (
                    session_bars.groupby("candle_index", sort=True)
                    .agg(
                        **{
                            f"{feed_name}_count": ("timestamp", "nunique"),
                            f"{feed_name}_close": ("close", "last"),
                        }
                    )
                    .reset_index()
                )
            feed_groups.append(closes)

        combined = feed_groups[0].merge(feed_groups[1], on="candle_index", how="outer")
        combined = combined.set_index("candle_index").reindex(range(len(candle_grid)))
        combined["session_date"] = str(session_day.date())
        comparison_frames.append(combined.reset_index(names="candle_index"))

    if not comparison_frames:
        return {"sessions_compared": 0, "both_real_candles": 0, "different_close_count": 0}

    comparisons = pd.concat(comparison_frames, ignore_index=True)
    paired = comparisons.loc[comparisons["iex_count"].gt(0) & comparisons["sip_count"].gt(0)].copy()
    differences_bps = (
        (paired["iex_close"] / paired["sip_close"] - 1).abs() * 10_000
        if len(paired)
        else pd.Series(dtype=float)
    )
    different = paired["iex_close"].ne(paired["sip_close"])
    return {
        "sessions_compared": int(comparisons["session_date"].nunique()),
        "regular_grid_candles": len(comparisons),
        "iex_real_candles": int(comparisons["iex_count"].fillna(0).gt(0).sum()),
        "sip_real_candles": int(comparisons["sip_count"].fillna(0).gt(0).sum()),
        "both_real_candles": len(paired),
        "different_close_count": int(different.sum()),
        "different_close_share": float(different.mean()) if len(paired) else None,
        "exact_match_count": int((~different).sum()),
        "mean_absolute_close_difference_bps": (
            float(differences_bps.mean()) if len(differences_bps) else None
        ),
        "median_absolute_close_difference_bps": (
            float(differences_bps.median()) if len(differences_bps) else None
        ),
        "max_absolute_close_difference_bps": (
            float(differences_bps.max()) if len(differences_bps) else None
        ),
    }


def split_adjustment_summary(raw: pd.DataFrame, split_adjusted: pd.DataFrame) -> dict[str, Any]:
    """Compare raw and split-adjusted minute bars around the 2025 NFLX split."""
    split_day = date(2025, 11, 17)

    def by_day(frame: pd.DataFrame) -> dict[str, float]:
        local = frame.copy()
        local["timestamp"] = pd.to_datetime(local["timestamp"], utc=True)
        local["local_time"] = local["timestamp"].dt.tz_convert(NEW_YORK)
        local = local.loc[
            (local["local_time"].dt.time >= pd.Timestamp("09:30").time())
            & (local["local_time"].dt.time < pd.Timestamp("16:00").time())
        ]
        closes = local.sort_values("timestamp").groupby(local["local_time"].dt.date)["close"].last()
        return {day.isoformat(): float(close) for day, close in closes.items()}

    raw_close = by_day(raw)
    adjusted_close = by_day(split_adjusted)
    pre_day = date(2025, 11, 14).isoformat()
    post_day = split_day.isoformat()
    has_required_days = all(
        day in closes for closes in (raw_close, adjusted_close) for day in (pre_day, post_day)
    )
    if not has_required_days:
        return {
            "status": "UNVERIFIED",
            "reason": "one or more expected regular-session daily closes were not returned",
        }

    pre_factor = adjusted_close[pre_day] / raw_close[pre_day]
    post_factor = adjusted_close[post_day] / raw_close[post_day]
    adjusted_close_ratio = adjusted_close[post_day] / adjusted_close[pre_day]
    factor_ok = 0.095 <= pre_factor <= 0.105 and 0.99 <= post_factor <= 1.01
    no_jump = 0.5 <= adjusted_close_ratio <= 2.0
    return {
        "status": "PASS" if factor_ok and no_jump else "FAIL",
        "pre_split_adjusted_to_raw_close_factor": pre_factor,
        "post_split_adjusted_to_raw_close_factor": post_factor,
        "split_adjusted_nov17_to_nov14_close_ratio": adjusted_close_ratio,
        "no_approximately_10x_jump": no_jump,
    }
