"""Score persisted, on-time live or replay predictions against same-session outcomes."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from eval.metrics import probability_metrics, reliability_table, wilson_lower_bound
from features import add_causal_features
from nflx_indicator.events import configured_event_session_dates


class LiveScoreError(ValueError):
    """Raised when a recorded database cannot be scored safely."""


def _metric_row(
    frame: pd.DataFrame,
    *,
    probabilities: pd.Series,
    directions: pd.Series,
    signal_mask: pd.Series,
) -> dict[str, Any]:
    """Summarize one method on one fixed candle set."""
    if frame.empty:
        return {"observations": 0, "signals": 0, "coverage": None}
    returns = frame["realized_return"].astype(float)
    signals = signal_mask.reindex(frame.index).fillna(False).astype(bool)
    predicted = directions.reindex(frame.index)
    nonzero = returns.ne(0.0)
    scored_nonzero = nonzero & predicted.isin(["UP", "DOWN"])
    successes = int(
        (predicted[scored_nonzero] == frame.loc[scored_nonzero, "realized_direction"]).sum()
    )
    signal_count = int(signals.sum())
    output: dict[str, Any] = {
        "observations": int(len(frame)),
        "nonzero_labels": int(nonzero.sum()),
        "zero_return_observations": int((~nonzero).sum()),
        "signals": signal_count,
        "coverage": float(signal_count / len(frame)),
        "signal_accuracy": float(successes / signal_count) if signal_count else None,
        "signal_wilson_95_lower": wilson_lower_bound(successes, signal_count),
        "probability_observations": 0,
        "log_loss": None,
        "brier": None,
        "simulated_pnl_bp": {},
    }
    probability_mask = probabilities.notna() & nonzero
    if probability_mask.any():
        target = returns.loc[probability_mask].gt(0).astype(int)
        metrics = probability_metrics(target, probabilities.loc[probability_mask].astype(float))
        output.update(metrics)
        output["probability_observations"] = int(probability_mask.sum())
    signal_returns = returns.loc[signals].to_numpy(dtype=float)
    signal_directions = (
        predicted.loc[signals].map({"UP": 1.0, "DOWN": -1.0}).to_numpy(dtype=float)
    )
    for cost in (0, 1, 2, 3):
        net = signal_directions * signal_returns * 10_000.0 - (2.0 * cost)
        output["simulated_pnl_bp"][str(cost)] = {
            "total": float(net.sum()),
            "mean_per_signal": float(net.mean()) if len(net) else None,
        }
    return output


def score_database(
    database: Path,
    *,
    symbol: str = "NFLX",
    min_minutes: int = 3,
    delta: float = 0.05,
) -> dict[str, Any]:
    """Score recorded predictions without fitting or changing the frozen model."""
    database = Path(database)
    if not database.is_file():
        raise LiveScoreError(f"database does not exist: {database}")
    if not 1 <= min_minutes <= 5 or not 0 <= delta < 0.5:
        raise LiveScoreError("min_minutes or delta is outside its supported range")
    with sqlite3.connect(database) as connection:
        candles = pd.read_sql_query(
            "SELECT * FROM candles_5m WHERE symbol = ? ORDER BY candle_start",
            connection,
            params=(symbol,),
        )
        predictions = pd.read_sql_query(
            """SELECT p.*, o.realized_return, o.realized_direction,
                      o.status AS outcome_status, c.session_date, c.n_minutes,
                      c.is_filled
               FROM predictions p
               JOIN outcomes o ON o.prediction_id = p.id
               JOIN candles_5m c ON c.symbol = p.symbol AND c.candle_start = p.candle_start
               WHERE p.symbol = ? ORDER BY p.candle_start""",
            connection,
            params=(symbol,),
        )
        total_predictions = pd.read_sql_query(
            "SELECT COUNT(*) AS count FROM predictions WHERE symbol = ?",
            connection,
            params=(symbol,),
        ).iloc[0]["count"]
        model_rows = pd.read_sql_query(
            "SELECT model_version, artifact_sha256, metadata_json FROM model_registry "
            "ORDER BY registered_at DESC LIMIT 1",
            connection,
        )
        events = pd.read_sql_query(
            "SELECT severity, component, event FROM events", connection
        )
    if candles.empty or predictions.empty:
        raise LiveScoreError("database has no recorded candles with evaluated predictions")

    candles["candle_start"] = pd.to_datetime(candles["candle_start"], utc=True)
    predictions["candle_start"] = pd.to_datetime(predictions["candle_start"], utc=True)
    features = add_causal_features(candles)
    predictions = predictions.merge(
        features[["candle_start", "return_1", "rsi_14"]],
        on="candle_start",
        how="left",
        validate="many_to_one",
    )
    predictions["realized_return"] = pd.to_numeric(predictions["realized_return"])
    eligible = predictions.loc[
        predictions["outcome_status"].eq("scored")
        & predictions["generated_late"].eq(0)
        & predictions["n_minutes"].ge(min_minutes)
        & predictions["is_filled"].eq(0)
    ].copy()
    eligible["realized_direction"] = np.where(
        eligible["realized_return"].gt(0),
        "UP",
        np.where(eligible["realized_return"].lt(0), "DOWN", "ZERO"),
    )
    if eligible.empty:
        raise LiveScoreError("no on-time, eligible prediction outcomes are available")
    eligible["is_event_session"] = eligible["session_date"].astype(str).isin(
        configured_event_session_dates()
    )
    eligible["model_direction"] = eligible["direction"]
    eligible["model_probability"] = pd.to_numeric(eligible["calibrated_p"], errors="coerce")
    eligible["always_up_probability"] = 1.0
    eligible["always_down_probability"] = 0.0
    eligible["always_up_direction"] = "UP"
    eligible["always_down_direction"] = "DOWN"
    previous_return = pd.to_numeric(eligible["return_1"], errors="coerce")
    eligible["previous_probability"] = np.where(
        previous_return.gt(0), 1.0, np.where(previous_return.lt(0), 0.0, 0.5)
    )
    eligible["previous_direction"] = np.where(
        previous_return.gt(0), "UP", np.where(previous_return.lt(0), "DOWN", "NO_CLEAR_SIGNAL")
    )
    rsi = pd.to_numeric(eligible["rsi_14"], errors="coerce")
    eligible["rsi_probability"] = np.where(rsi.lt(30), 1.0, np.where(rsi.gt(70), 0.0, 0.5))
    eligible["rsi_direction"] = np.where(
        rsi.lt(30), "UP", np.where(rsi.gt(70), "DOWN", "NO_CLEAR_SIGNAL")
    )
    # Expanding majority uses only the outcomes preceding each candle. Zero returns do not
    # enter the binary history, matching the training-label convention.
    prior_targets = pd.Series(
        np.where(
            eligible["realized_return"].gt(0),
            1.0,
            np.where(eligible["realized_return"].lt(0), 0.0, np.nan),
        ),
        index=eligible.index,
    )
    prior_up_rate = prior_targets.shift(1).expanding(min_periods=1).mean()
    eligible["majority_probability"] = np.where(
        prior_up_rate.isna(), 0.5, (prior_up_rate >= 0.5).astype(float)
    )
    eligible["majority_direction"] = np.where(
        eligible["majority_probability"].gt(0.5),
        "UP",
        np.where(eligible["majority_probability"].lt(0.5), "DOWN", "NO_CLEAR_SIGNAL"),
    )

    methods: dict[str, tuple[str, str, str | None]] = {
        "model-v1": ("model_probability", "model_direction", None),
        "always_up": (
            "always_up_probability",
            "always_up_direction",
            "always_up_direction",
        ),
        "always_down": (
            "always_down_probability",
            "always_down_direction",
            "always_down_direction",
        ),
        "majority_class_expanding": (
            "majority_probability",
            "majority_direction",
            "majority_direction",
        ),
        "previous_candle_direction": (
            "previous_probability",
            "previous_direction",
            "previous_direction",
        ),
        "rsi14_rule": ("rsi_probability", "rsi_direction", "rsi_direction"),
    }
    breakdown: dict[str, Any] = {}
    calibration: dict[str, Any] = {}
    for subset_name, subset in (
        ("all", eligible),
        ("non_event", eligible.loc[~eligible["is_event_session"]]),
        ("event", eligible.loc[eligible["is_event_session"]]),
    ):
        breakdown[subset_name] = {}
        calibration_rows = subset.loc[
            subset["model_probability"].notna() & subset["realized_return"].ne(0)
        ]
        calibration[subset_name] = (
            reliability_table(
                calibration_rows["realized_return"].gt(0).astype(int),
                calibration_rows["model_probability"].astype(float),
            ).to_dict(orient="records")
            if not calibration_rows.empty
            else []
        )
        for method, (probability_col, direction_col, signal_col) in methods.items():
            direction = subset[direction_col]
            if signal_col is None:
                signals = direction.isin(["UP", "DOWN"])
                # The shipped model's no-signal band comes from its frozen delta.
                if subset["model_probability"].notna().any():
                    p = subset["model_probability"]
                    threshold_direction = np.where(
                        p.ge(0.5 + delta),
                        "UP",
                        np.where(p.le(0.5 - delta), "DOWN", "NO_CLEAR_SIGNAL"),
                    )
                    direction = pd.Series(threshold_direction, index=subset.index).where(
                        p.notna(), direction
                    )
                    signals = direction.isin(["UP", "DOWN"])
            else:
                signals = direction.isin(["UP", "DOWN"])
            breakdown[subset_name][method] = _metric_row(
                subset,
                probabilities=subset[probability_col],
                directions=direction,
                signal_mask=signals,
            )

    model_info: dict[str, Any] = {}
    if not model_rows.empty:
        metadata = json.loads(model_rows.iloc[0]["metadata_json"])
        model_info = {
            "model_version": model_rows.iloc[0]["model_version"],
            "artifact_sha256": model_rows.iloc[0]["artifact_sha256"],
            "snapshot_hash": metadata.get("snapshot_hash"),
        }
    outages = (
        int(events["severity"].isin(["ERROR", "CRITICAL"]).sum())
        if not events.empty
        else 0
    )
    reasons = (
        eligible["reason"].fillna("signal").value_counts().sort_index().to_dict()
    )
    return {
        "database": database.name,
        "feed_label": (
            "REPLAY (recorded IEX bars)"
            if "replay" in database.name.lower()
            else "LIVE DB (verify health log)"
        ),
        "symbol": symbol,
        "min_minutes": min_minutes,
        "delta": delta,
        "model": model_info,
        "sessions": int(eligible["session_date"].nunique()),
        "start_session": str(eligible["session_date"].min()),
        "end_session": str(eligible["session_date"].max()),
        "prediction_outcomes": int(len(eligible)),
        "late_or_ineligible_rows_excluded": int(total_predictions - len(eligible)),
        "zero_return_share": float(eligible["realized_return"].eq(0).mean()),
        "event_sessions_in_sample": sorted(
            eligible.loc[eligible["is_event_session"], "session_date"].astype(str).unique()
        ),
        "prediction_reasons": {str(key): int(value) for key, value in reasons.items()},
        "recorded_error_events": outages,
        "recorded_feed_state_transitions": (
            {
                str(key): int(value)
                for key, value in events.loc[
                    events["event"].eq("feed_state_changed"), "severity"
                ].value_counts().to_dict().items()
            }
            if not events.empty
            else {}
        ),
        "metrics": breakdown,
        "calibration_bins": calibration,
    }
