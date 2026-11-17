"""Construct next-five-minute direction labels without crossing sessions."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


class LabelBuildError(ValueError):
    """Raised when final candles cannot safely receive labels."""


def attach_next_candle_labels(
    candles: pd.DataFrame,
    *,
    min_minutes: int = 3,
    event_session_dates: Iterable[str] = (),
) -> pd.DataFrame:
    """Attach causal prediction and next-candle training eligibility columns.

    A model prediction at t needs t to meet ``min_minutes``. A target at t uses
    only the immediate next candle in the same session and accepts that outcome
    whenever its ``n_minutes`` is at least one. Exact zero returns are retained
    as observations but excluded from supervised training.
    """
    if not 1 <= min_minutes <= 5:
        raise LabelBuildError("min_minutes must be between 1 and 5")
    required = {"candle_start", "session_date", "close", "n_minutes", "is_filled"}
    missing = required.difference(candles.columns)
    if missing:
        raise LabelBuildError(f"candles are missing required columns: {sorted(missing)}")

    result = candles.copy()
    result["candle_start"] = pd.to_datetime(result["candle_start"], utc=True, errors="coerce")
    if result["candle_start"].isna().any() or result["candle_start"].duplicated().any():
        raise LabelBuildError("candle_start values must be valid and unique")
    result = result.sort_values("candle_start", kind="mergesort").reset_index(drop=True)

    event_days = {str(day) for day in event_session_dates}
    result["is_event_session"] = result["session_date"].astype(str).isin(event_days)
    technical_prediction_eligible = result["n_minutes"].ge(min_minutes) & ~result[
        "is_filled"
    ].astype(bool)
    result["prediction_eligible"] = technical_prediction_eligible & ~result["is_event_session"]
    result["prediction_gate_reason"] = None
    result.loc[~technical_prediction_eligible, "prediction_gate_reason"] = (
        "thin_data_n_minutes_" + result.loc[~technical_prediction_eligible, "n_minutes"].astype(str)
    )
    result.loc[result["is_event_session"], "prediction_gate_reason"] = "event_session"

    grouped = result.groupby("session_date", sort=False)
    result["next_candle_start"] = grouped["candle_start"].shift(-1)
    result["next_close"] = grouped["close"].shift(-1)
    result["next_n_minutes"] = grouped["n_minutes"].shift(-1)
    result["next_return"] = result["next_close"] / result["close"] - 1.0
    has_next = result["next_candle_start"].notna()
    next_has_real_close = result["next_n_minutes"].ge(1)
    nonzero_return = result["next_return"].notna() & result["next_return"].ne(0.0)

    # This represents whether the outcome can supervise a technically eligible
    # t candle. Event-session exclusion is kept separately in training_eligible.
    result["label_eligible"] = (
        technical_prediction_eligible & has_next & next_has_real_close & nonzero_return
    )
    result["training_eligible"] = result["label_eligible"] & ~result["is_event_session"]
    result["target"] = pd.Series(pd.NA, index=result.index, dtype="string")
    result.loc[result["label_eligible"] & result["next_return"].gt(0), "target"] = "UP"
    result.loc[result["label_eligible"] & result["next_return"].lt(0), "target"] = "DOWN"
    result["target_up"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result.loc[result["target"].eq("UP"), "target_up"] = 1
    result.loc[result["target"].eq("DOWN"), "target_up"] = 0

    result["label_reason"] = None
    result.loc[~technical_prediction_eligible, "label_reason"] = "thin_data_at_t"
    result.loc[technical_prediction_eligible & ~has_next, "label_reason"] = "session_boundary"
    result.loc[technical_prediction_eligible & has_next & ~next_has_real_close, "label_reason"] = (
        "next_candle_no_real_close"
    )
    result.loc[
        technical_prediction_eligible & has_next & next_has_real_close & ~nonzero_return,
        "label_reason",
    ] = "zero_return"
    result.loc[result["label_eligible"], "label_reason"] = None
    return result
