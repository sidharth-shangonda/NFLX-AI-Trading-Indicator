"""Phase 4 one-time model freeze and guarded final-holdout evaluation."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from eval.metrics import (
    directional_metrics,
    probability_metrics,
    reliability_table,
    select_delta,
)
from eval.walkforward import DEFAULT_HOLDOUT_ACCESS_LOG, partition_final_holdout
from features import FEATURE_COLUMNS
from models import (
    ARTIFACT_SCHEMA_VERSION,
    ModelArtifact,
    ProbabilityCalibrator,
    artifact_metadata,
    fit_classifier,
    save_model_artifact,
    write_artifact_metadata,
)
from models.prediction import BASELINE_NAMES, fit_predict
from nflx_indicator.training_data import (
    POST_SPLIT_START,
    build_labeled_feature_frame,
    load_frozen_snapshot,
    supervised_rows,
)

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
MODELS_DIR: Final = PROJECT_ROOT / "models"
MODEL_PATH: Final = MODELS_DIR / "model-v1.joblib"
MODEL_METADATA_PATH: Final = PROJECT_ROOT / "docs" / "model_metadata.json"
MODEL_CARD_PATH: Final = PROJECT_ROOT / "docs" / "model_card.md"
HOLDOUT_RESULTS_PATH: Final = PROJECT_ROOT / "docs" / "results_holdout.md"
DELTA_TABLE_PATH: Final = PROJECT_ROOT / "docs" / "model_delta_selection.csv"
RELIABILITY_PATH: Final = PROJECT_ROOT / "docs" / "model_reliability.csv"
PRODUCTION_WINDOW: Final = "post_split"
METHOD: Final = "logistic_regression"
MODEL_VERSION: Final = "model-v1"
HOLDOUT_DAYS: Final = 30
BASE_TRAIN_DAYS: Final = 140
CALIBRATION_GAP_DAYS: Final = 1
CALIBRATION_DAYS: Final = 30
THRESHOLD_GAP_DAYS: Final = 1
WIDE_FALLBACK_DELTA: Final = 0.05
SEED: Final = 20_261_107


class FreezeError(RuntimeError):
    """Raised when a model freeze would violate the single-touch protocol."""


@dataclass(frozen=True)
class FrozenEvaluation:
    """Immutable evidence from the one permitted final-holdout evaluation."""

    artifact: ModelArtifact
    artifact_hash: str
    holdout_metrics: dict[str, Any]
    baseline_metrics: dict[str, dict[str, Any]]
    holdout_first_session: str
    holdout_last_session: str
    calibration_metrics: dict[str, float]
    threshold_metrics: dict[str, float]
    delta_candidates: pd.DataFrame
    reliability: pd.DataFrame


def _git_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNVERIFIED"


def _access_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def _session_sets(sessions: pd.Series) -> tuple[tuple[str, ...], ...]:
    ordered = tuple(sorted(sessions.astype(str).unique().tolist()))
    required = (
        BASE_TRAIN_DAYS
        + CALIBRATION_GAP_DAYS
        + CALIBRATION_DAYS
        + THRESHOLD_GAP_DAYS
        + 1
    )
    if len(ordered) < required:
        raise FreezeError("not enough post-split development sessions for model/calibration split")
    calibration_start = BASE_TRAIN_DAYS + CALIBRATION_GAP_DAYS
    calibration_end = calibration_start + CALIBRATION_DAYS
    threshold_start = calibration_end + THRESHOLD_GAP_DAYS
    return (
        ordered[:BASE_TRAIN_DAYS],
        ordered[BASE_TRAIN_DAYS:calibration_start],
        ordered[calibration_start:calibration_end],
        ordered[calibration_end:threshold_start],
        ordered[threshold_start:],
    )


def _rows_for_sessions(rows: pd.DataFrame, sessions: tuple[str, ...]) -> pd.DataFrame:
    output = rows.loc[rows["session_date"].astype(str).isin(sessions)].copy()
    if output.empty:
        raise FreezeError("a required chronological segment has no supervised rows")
    return output.sort_values("candle_start", kind="mergesort").reset_index(drop=True)


def _baseline_metrics(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    *,
    delta: float,
) -> dict[str, dict[str, Any]]:
    """Score fixed baselines on the same locked rows after the one authorized load."""
    metrics: dict[str, dict[str, Any]] = {}
    for baseline in BASELINE_NAMES:
        output = fit_predict(
            baseline,
            train_features=train.loc[:, FEATURE_COLUMNS],
            train_target=train["target_up"].astype(int),
            test_features=holdout.loc[:, FEATURE_COLUMNS],
            seed=SEED,
        )
        probability = output.probabilities
        metrics[baseline] = {
            **probability_metrics(holdout["target_up"].astype(int), probability),
            **directional_metrics(
                holdout["target_up"].astype(int),
                probability,
                delta=delta,
                next_return=holdout["next_return"],
            ),
        }
    return metrics


def _time_bucket(candle_start: pd.Series) -> pd.Series:
    et = pd.to_datetime(candle_start, utc=True).dt.tz_convert("America/New_York")
    minutes = et.dt.hour * 60 + et.dt.minute
    return pd.Series(
        np.select(
            [minutes.lt(10 * 60), minutes.ge(15 * 60 + 30)],
            ["open_09:30-10:00", "close_15:30-16:00"],
            default="midday",
        ),
        index=candle_start.index,
    )


def _breakdowns(holdout: pd.DataFrame, probabilities: np.ndarray, delta: float) -> dict[str, Any]:
    working = holdout.copy()
    working["probability"] = probabilities
    working["time_bucket"] = _time_bucket(working["candle_start"])
    working["volatility_tercile"] = pd.qcut(
        working["realized_vol_12"], q=3, labels=["low", "middle", "high"], duplicates="drop"
    ).astype(str)
    output: dict[str, Any] = {}
    for column in ("time_bucket", "volatility_tercile"):
        output[column] = {}
        for value, group in working.groupby(column, sort=True, observed=True):
            output[column][str(value)] = directional_metrics(
                group["target_up"].astype(int),
                group["probability"],
                delta=delta,
                next_return=group["next_return"],
            )
    return output


def _markdown_metric_summary(metrics: dict[str, Any]) -> list[str]:
    accuracy = metrics["signal_accuracy"]
    accuracy_text = "n/a" if accuracy is None else f"{accuracy:.2%}"
    balanced = metrics["signal_balanced_accuracy"]
    balanced_text = "n/a" if balanced is None else f"{balanced:.2%}"
    mcc = metrics["signal_mcc"]
    mcc_text = "n/a" if mcc is None else f"{mcc:.4f}"
    lines = [
        f"- Confident signals: **{metrics['signal_count']:,}/{metrics['samples']:,}** "
        f"({metrics['coverage']:.2%})",
        f"- Confident-signal accuracy: **{accuracy_text}**; Wilson lower bound: "
        f"**{metrics['signal_wilson_lower_bound']:.2%}**",
        f"- Balanced accuracy: {balanced_text}; MCC: {mcc_text}",
        f"- Confusion matrix: `{json.dumps(metrics['confusion_matrix'], sort_keys=True)}`",
        "- Simulated P&L assumes a complete long/short entry and exit on every confident "
        "signal; results are not trading results:",
    ]
    for cost, result in metrics["simulated_pnl_bp"].items():
        lines.append(
            f"  - {float(cost):.0f} bp per side: total {result['total']:.2f} bp; "
            f"mean {result['mean_per_signal']:.4f} bp/signal"
        )
    return lines


def _write_model_card(evaluation: FrozenEvaluation) -> None:
    artifact = evaluation.artifact
    metadata = artifact_metadata(artifact, evaluation.artifact_hash)
    fallback = artifact.fallback_reason or "None"
    lines = [
        "# Model card: model-v1",
        "",
        "## Intended use",
        "",
        "A paper-only, next-five-minute NFLX direction indicator using IEX data. It is not "
        "investment advice, broker software, or an order-execution system.",
        "",
        "## Frozen artifact",
        "",
        f"- Artifact: `models/model-v1.joblib`, SHA-256 `{evaluation.artifact_hash}`",
        f"- Snapshot: `{artifact.snapshot_hash}`",
        f"- Code commit used for training: `{artifact.git_hash}`",
        f"- Window: `{artifact.production_window}`; method: `{artifact.method}`",
        f"- Trained through: `{artifact.trained_through_session}`",
        (
            f"- Calibrator: `{metadata['calibrator']}`; NO CLEAR SIGNAL band delta: "
            f"`{artifact.delta:.3f}`"
        ),
        f"- Fallback status: {fallback}",
        "",
        "## Inputs and target",
        "",
        "- Inputs: " + ", ".join(f"`{column}`" for column in artifact.feature_columns),
        "- Target: sign of the next finalized five-minute IEX candle's close-to-close return.",
        "- Predictions are gated when current `n_minutes < 3`, on configured event sessions, "
        "or during feature warm-up.",
        "",
        "## Honest evaluation",
        "",
        f"- One locked holdout: `{evaluation.holdout_first_session}` through "
        f"`{evaluation.holdout_last_session}`.",
        f"- Holdout probability log loss: `{evaluation.holdout_metrics['log_loss']:.5f}`; "
        f"Brier: `{evaluation.holdout_metrics['brier']:.5f}`.",
        *_markdown_metric_summary(evaluation.holdout_metrics),
        "",
        "## Limitations",
        "",
        "- Phase 3 found no model that beat the neutral 50/50 probability benchmark in "
        "development. This artifact is a logistic-regression fallback with a wide no-signal "
        "band, not evidence of a profitable edge.",
        "- Historical and live data are IEX-only, not consolidated-market data. Missing bars and "
        "thin IEX candles can suppress a signal.",
        "- The holdout is one period only; the future live evaluation is required before claims "
        "about operational performance.",
        "",
    ]
    MODEL_CARD_PATH.write_text("\n".join(lines))


def _write_holdout_results(evaluation: FrozenEvaluation) -> None:
    artifact = evaluation.artifact
    lines = [
        "# Final holdout results — immutable after Phase 4",
        "",
        "This file records the one owner-authorized `ALLOW_HOLDOUT=1` evaluation. Do not "
        "edit, rerun, tune, or retrain from it.",
        "",
        f"- Frozen snapshot: `{artifact.snapshot_hash}`",
        f"- Artifact SHA-256: `{evaluation.artifact_hash}`",
        f"- Training code commit: `{artifact.git_hash}`",
        f"- Holdout: `{evaluation.holdout_first_session}` through "
        f"`{evaluation.holdout_last_session}`",
        f"- Model: `{artifact.method}` on `{artifact.production_window}`; calibration `platt`; "
        f"delta `{artifact.delta:.3f}`",
        "",
        "## Calibration chronology",
        "",
        f"- Base model trained through `{artifact.trained_through_session}` only.",
        f"- Calibration fit sessions: `{artifact.calibration_sessions[0]}` through "
        f"`{artifact.calibration_sessions[-1]}`.",
        f"- Threshold selection sessions: `{artifact.threshold_sessions[0]}` through "
        f"`{artifact.threshold_sessions[-1]}`.",
        f"- Calibration-period log loss `{evaluation.calibration_metrics['log_loss']:.5f}`, "
        f"Brier `{evaluation.calibration_metrics['brier']:.5f}`; later threshold-period log "
        f"loss `{evaluation.threshold_metrics['log_loss']:.5f}`, Brier "
        f"`{evaluation.threshold_metrics['brier']:.5f}`.",
        "",
        "## Model metrics",
        "",
        f"- Log loss: **{evaluation.holdout_metrics['log_loss']:.5f}**",
        f"- Brier: **{evaluation.holdout_metrics['brier']:.5f}**",
        *_markdown_metric_summary(evaluation.holdout_metrics),
        "",
        "## Same-candle baseline probability metrics",
        "",
        "| Baseline | Log loss | Brier | Signal coverage | Signal accuracy |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, metrics in evaluation.baseline_metrics.items():
        signal = metrics["signal_accuracy"]
        signal_text = "n/a" if signal is None else f"{signal:.2%}"
        lines.append(
            f"| {name} | {metrics['log_loss']:.5f} | {metrics['brier']:.5f} | "
            f"{metrics['coverage']:.2%} | {signal_text} |"
        )
    lines.extend(
        [
            "",
            "## Breakdowns",
            "",
            "The JSON metadata records time-of-day and holdout-volatility-tercile breakdowns. "
            "They are descriptive, not tuning inputs.",
            "",
        ]
    )
    HOLDOUT_RESULTS_PATH.write_text("\n".join(lines))


def _write_holdout_metadata(evaluation: FrozenEvaluation, breakdowns: dict[str, Any]) -> None:
    metadata_path = PROJECT_ROOT / "docs" / "model_evaluation.json"
    payload = {
        "artifact": artifact_metadata(evaluation.artifact, evaluation.artifact_hash),
        "baseline_metrics": evaluation.baseline_metrics,
        "breakdowns": breakdowns,
        "calibration_metrics": evaluation.calibration_metrics,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "holdout_metrics": evaluation.holdout_metrics,
        "holdout_sessions": [evaluation.holdout_first_session, evaluation.holdout_last_session],
        "threshold_metrics": evaluation.threshold_metrics,
    }
    metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def freeze_model_once(
    *,
    holdout_log_path: Path = DEFAULT_HOLDOUT_ACCESS_LOG,
) -> FrozenEvaluation:
    """Train once, calibrate chronologically, then perform exactly one holdout read."""
    if os.environ.get("ALLOW_HOLDOUT") != "1":
        raise FreezeError("set ALLOW_HOLDOUT=1 for the one permitted Phase 4 holdout run")
    immutable_paths = (MODEL_PATH, HOLDOUT_RESULTS_PATH, MODEL_CARD_PATH)
    if any(path.exists() for path in immutable_paths):
        raise FreezeError("model-v1 artifact or holdout results already exist; refusing to rerun")
    if _access_count(holdout_log_path):
        raise FreezeError("final holdout was already accessed; refusing to rerun")
    snapshot = load_frozen_snapshot()
    all_candles = build_labeled_feature_frame(snapshot)
    all_rows = supervised_rows(all_candles, window="full_history")
    partition = partition_final_holdout(
        all_rows,
        holdout_days=HOLDOUT_DAYS,
        session_universe=all_candles["session_date"].astype(str),
        access_log_path=holdout_log_path,
    )
    development = partition.development_frame()
    post_split = development.loc[
        development["session_date"].astype(str) >= POST_SPLIT_START
    ].copy()
    dev_sessions = all_candles.loc[
        (all_candles["session_date"].astype(str) >= POST_SPLIT_START)
        & (all_candles["session_date"].astype(str) < partition.holdout_sessions[0]),
        "session_date",
    ]
    train_sessions, _, calibration_sessions, _, threshold_sessions = _session_sets(dev_sessions)
    train = _rows_for_sessions(post_split, train_sessions)
    calibration = _rows_for_sessions(post_split, calibration_sessions)
    threshold = _rows_for_sessions(post_split, threshold_sessions)

    # The base estimator never sees calibration or threshold sessions.
    estimator = fit_classifier(
        METHOD,
        train_features=train.loc[:, FEATURE_COLUMNS],
        train_target=train["target_up"].astype(int),
        seed=SEED,
    )
    calibration_raw = estimator.predict_proba(calibration.loc[:, FEATURE_COLUMNS])[:, 1]
    calibrator = ProbabilityCalibrator.fit(calibration_raw, calibration["target_up"].astype(int))
    calibration_probability = calibrator.predict(calibration_raw)
    threshold_raw = estimator.predict_proba(threshold.loc[:, FEATURE_COLUMNS])[:, 1]
    threshold_probability = calibrator.predict(threshold_raw)
    selected_delta, delta_candidates = select_delta(
        threshold["target_up"].astype(int), threshold_probability
    )
    # Phase 3 could not beat the neutral baseline. The written fallback policy
    # therefore enforces a wide band before—not after—the holdout is touched.
    delta = max(selected_delta, WIDE_FALLBACK_DELTA)
    artifact = ModelArtifact(
        schema_version=ARTIFACT_SCHEMA_VERSION,
        model_version=MODEL_VERSION,
        method=METHOD,
        estimator=estimator,
        calibrator=calibrator,
        feature_columns=FEATURE_COLUMNS,
        delta=delta,
        snapshot_hash=snapshot.snapshot_hash,
        git_hash=_git_hash(),
        trained_through_session=train_sessions[-1],
        calibration_sessions=calibration_sessions,
        threshold_sessions=threshold_sessions,
        production_window=PRODUCTION_WINDOW,
        fallback_reason=(
            "No Phase 3 candidate beat neutral_50_50 on pooled development log loss; "
            "logistic-regression fallback uses a 0.05 minimum no-signal band."
        ),
    )
    artifact_hash = save_model_artifact(artifact, MODEL_PATH)
    write_artifact_metadata(artifact, artifact_hash, MODEL_METADATA_PATH)

    # This is intentionally the first and only line that loads the holdout.
    holdout = partition.load_holdout(purpose="phase-4 one-time final evaluation")
    holdout_probability = artifact.predict_calibrated(holdout.loc[:, FEATURE_COLUMNS])
    holdout_metrics = {
        **probability_metrics(holdout["target_up"].astype(int), holdout_probability),
        **directional_metrics(
            holdout["target_up"].astype(int),
            holdout_probability,
            delta=artifact.delta,
            next_return=holdout["next_return"],
        ),
    }
    evaluation = FrozenEvaluation(
        artifact=artifact,
        artifact_hash=artifact_hash,
        holdout_metrics=holdout_metrics,
        baseline_metrics=_baseline_metrics(train, holdout, delta=artifact.delta),
        holdout_first_session=partition.holdout_sessions[0],
        holdout_last_session=partition.holdout_sessions[-1],
        calibration_metrics=probability_metrics(calibration["target_up"], calibration_probability),
        threshold_metrics=probability_metrics(threshold["target_up"], threshold_probability),
        delta_candidates=delta_candidates,
        reliability=reliability_table(threshold["target_up"], threshold_probability),
    )
    DELTA_TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    evaluation.delta_candidates.to_csv(DELTA_TABLE_PATH, index=False)
    evaluation.reliability.to_csv(RELIABILITY_PATH, index=False)
    _write_holdout_results(evaluation)
    _write_model_card(evaluation)
    _write_holdout_metadata(
        evaluation,
        _breakdowns(holdout, holdout_probability, artifact.delta),
    )
    return evaluation
