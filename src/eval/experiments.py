"""Development-only walk-forward experiments for the NFLX indicator.

Nothing in this module calls ``HoldoutPartition.load_holdout``.  The last 30
NYSE sessions stay locked for Phase 4, and this phase only emits aggregate
development metrics plus local out-of-fold prediction records.
"""

from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from eval.walkforward import TradingDayWalkForward, partition_final_holdout
from features import FEATURE_COLUMNS
from models import BASELINE_NAMES, CLASSIFIER_NAMES, evaluate_probabilities, fit_predict
from models.prediction import method_parameters
from nflx_indicator.training_data import (
    POST_SPLIT_START,
    TRAINING_WINDOWS,
    build_labeled_feature_frame,
    load_frozen_snapshot,
    supervised_rows,
)

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_EXPERIMENTS_PATH: Final = PROJECT_ROOT / "experiments" / "experiments.csv"
DEFAULT_OOF_PATH: Final = PROJECT_ROOT / "data" / "derived" / "phase3_oof_predictions.parquet"
DEFAULT_RESULTS_PATH: Final = PROJECT_ROOT / "docs" / "results_dev.md"
DEFAULT_PLOT_PATH: Final = PROJECT_ROOT / "docs" / "plots" / "phase3_pooled_log_loss.svg"
DEFAULT_HOLDOUT_LOG: Final = PROJECT_ROOT / "experiments" / "holdout_access.log"
SEED: Final = 20_261_107
HOLDOUT_DAYS: Final = 30
MIN_TRAIN_DAYS: Final = 60
TEST_DAYS: Final = 20
GAP_DAYS: Final = 1

FEATURE_FAMILIES: Final = {
    "return_and_risk": (
        "return_1",
        "return_3",
        "return_12",
        "realized_vol_12",
        "range_mean_12",
        "atr_14",
        "gap_from_previous_session",
    ),
    "trend_and_momentum": (
        "ema_fast_distance",
        "ema_slow_distance",
        "rsi_14",
        "macd",
        "macd_signal",
        "bollinger_position_20",
        "bollinger_width_20",
    ),
    "activity_and_time": (
        "relative_volume_20",
        "time_of_day_sin",
        "time_of_day_cos",
    ),
}


class ExperimentError(RuntimeError):
    """Raised when development experiments cannot satisfy their safety contract."""


@dataclass(frozen=True)
class DevelopmentRun:
    """Aggregate records, local OOF predictions, and selection evidence."""

    records: pd.DataFrame
    oof_predictions: pd.DataFrame
    summaries: pd.DataFrame
    selections: pd.DataFrame
    snapshot_hash: str
    git_hash: str
    holdout_sessions: tuple[str, ...]
    development_sessions: tuple[str, ...]


def _git_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "UNVERIFIED"


def _holdout_access_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def _feature_columns(feature_set: str) -> tuple[str, ...]:
    if feature_set == "all_features":
        return FEATURE_COLUMNS
    prefix = "without_"
    if not feature_set.startswith(prefix):
        raise ExperimentError(f"unknown feature set: {feature_set}")
    family = feature_set.removeprefix(prefix)
    try:
        excluded = set(FEATURE_FAMILIES[family])
    except KeyError as exc:
        raise ExperimentError(f"unknown feature family: {family}") from exc
    selected = tuple(column for column in FEATURE_COLUMNS if column not in excluded)
    if not selected:
        raise ExperimentError("feature ablation removed every input")
    return selected


def _method_names() -> tuple[str, ...]:
    return BASELINE_NAMES + CLASSIFIER_NAMES


def _fold_records(
    rows: pd.DataFrame,
    *,
    session_universe: pd.Series,
    window: str,
    feature_set: str,
    methods: tuple[str, ...],
    snapshot_hash: str,
    git_hash: str,
    run_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Evaluate every method over expanding development folds without shuffling."""
    feature_columns = _feature_columns(feature_set)
    splitter = TradingDayWalkForward(
        min_train_days=MIN_TRAIN_DAYS,
        test_days=TEST_DAYS,
        gap_days=GAP_DAYS,
    )
    folds = splitter.split(session_universe)
    records: list[dict[str, Any]] = []
    oof_rows: list[dict[str, Any]] = []
    for fold in folds:
        train_mask, _, test_mask = fold.masks(rows["session_date"])
        train = rows.loc[train_mask].copy()
        test = rows.loc[test_mask].copy()
        if train.empty or test.empty:
            # The session universe can intentionally include an event day with
            # no eligible label. A 20-session test block must still contain
            # usable rows; otherwise the protocol is not meaningful.
            raise ExperimentError(f"fold {fold.number} has no eligible train or test rows")
        train_x = train.loc[:, feature_columns]
        test_x = test.loc[:, feature_columns]
        train_y = train["target_up"].astype(int)
        test_y = test["target_up"].astype(int)
        for method in methods:
            output = fit_predict(
                method,
                train_features=train_x,
                train_target=train_y,
                test_features=test_x,
                seed=SEED + fold.number,
            )
            metrics = evaluate_probabilities(
                test_y,
                output.probabilities,
                signal_mask=output.signal_mask,
            )
            records.append(
                {
                    "record_type": "fold",
                    "run_at_utc": run_at_utc,
                    "window": window,
                    "feature_set": feature_set,
                    "method": method,
                    "fold": fold.number,
                    "train_first_session": fold.train_sessions[0],
                    "train_last_session": fold.train_sessions[-1],
                    "gap_first_session": fold.gap_sessions[0] if fold.gap_sessions else "",
                    "gap_last_session": fold.gap_sessions[-1] if fold.gap_sessions else "",
                    "test_first_session": fold.test_sessions[0],
                    "test_last_session": fold.test_sessions[-1],
                    "train_sessions": len(fold.train_sessions),
                    "gap_sessions": len(fold.gap_sessions),
                    "test_sessions": len(fold.test_sessions),
                    "train_rows": len(train),
                    "test_rows": len(test),
                    "train_up_rate": float(train_y.mean()),
                    "parameters": json.dumps(method_parameters(method), sort_keys=True),
                    "seed": SEED + fold.number,
                    "snapshot_hash": snapshot_hash,
                    "git_hash": git_hash,
                    **metrics,
                }
            )
            for index, probability in enumerate(output.probabilities):
                oof_rows.append(
                    {
                        "window": window,
                        "feature_set": feature_set,
                        "method": method,
                        "fold": fold.number,
                        "candle_start": test.iloc[index]["candle_start"],
                        "session_date": test.iloc[index]["session_date"],
                        "target_up": int(test_y.iloc[index]),
                        "raw_probability_up": float(probability),
                        "signal": bool(output.signal_mask[index]),
                        "snapshot_hash": snapshot_hash,
                        "git_hash": git_hash,
                    }
                )
    return records, oof_rows


def _pooled_summaries(
    oof_predictions: pd.DataFrame,
    fold_records: pd.DataFrame,
    *,
    window: str,
    feature_set: str,
) -> pd.DataFrame:
    subset = oof_predictions.loc[
        (oof_predictions["window"] == window)
        & (oof_predictions["feature_set"] == feature_set)
    ]
    summaries: list[dict[str, Any]] = []
    for method, prediction_rows in subset.groupby("method", sort=True):
        metrics = evaluate_probabilities(
            prediction_rows["target_up"].astype(int),
            prediction_rows["raw_probability_up"].to_numpy(dtype=float),
            signal_mask=prediction_rows["signal"].to_numpy(dtype=bool),
        )
        method_folds = fold_records.loc[
            (fold_records["window"] == window)
            & (fold_records["feature_set"] == feature_set)
            & (fold_records["method"] == method)
        ]
        summaries.append(
            {
                "window": window,
                "feature_set": feature_set,
                "method": method,
                "folds": int(method_folds["fold"].nunique()),
                "mean_fold_log_loss": float(method_folds["log_loss"].mean()),
                **metrics,
            }
        )
    return pd.DataFrame.from_records(summaries).sort_values(
        ["log_loss", "method"], kind="mergesort"
    )


def _selection_summary(summaries: pd.DataFrame, fold_records: pd.DataFrame) -> pd.DataFrame:
    """Apply the documented pooled-loss plus majority-of-folds selection rule."""
    selection_rows: list[dict[str, Any]] = []
    main_summaries = summaries.loc[summaries["feature_set"] == "all_features"]
    for window, group in main_summaries.groupby("window", sort=True):
        baseline_loss = group.loc[group["method"].isin(BASELINE_NAMES)].set_index("method")[
            "log_loss"
        ]
        per_fold = fold_records.loc[
            (fold_records["window"] == window)
            & (fold_records["feature_set"] == "all_features")
        ]
        baseline_by_fold = (
            per_fold.loc[per_fold["method"].isin(BASELINE_NAMES)]
            .groupby("fold", sort=True)["log_loss"]
            .min()
        )
        eligible: list[tuple[float, str]] = []
        for _, summary in group.loc[group["method"].isin(CLASSIFIER_NAMES)].iterrows():
            method = str(summary["method"])
            candidate_folds = per_fold.loc[per_fold["method"] == method].set_index("fold")
            aligned = candidate_folds.join(baseline_by_fold.rename("best_baseline_log_loss"))
            fold_wins = int((aligned["log_loss"] < aligned["best_baseline_log_loss"]).sum())
            fold_count = int(len(aligned))
            beats_pooled_baselines = bool((summary["log_loss"] < baseline_loss).all())
            beats_most_folds = fold_wins > fold_count / 2
            is_eligible = beats_pooled_baselines and beats_most_folds
            if is_eligible:
                eligible.append((float(summary["log_loss"]), method))
            selection_rows.append(
                {
                    "window": window,
                    "method": method,
                    "pooled_log_loss": float(summary["log_loss"]),
                    "best_baseline_pooled_log_loss": float(baseline_loss.min()),
                    "beats_every_baseline_pooled": beats_pooled_baselines,
                    "fold_wins_vs_best_baseline": fold_wins,
                    "fold_count": fold_count,
                    "beats_most_folds": beats_most_folds,
                    "eligible_by_rule": is_eligible,
                }
            )
        selected = min(eligible, default=None)
        selected_method = selected[1] if selected is not None else "logistic_regression"
        selection_rows.append(
            {
                "window": window,
                "method": selected_method,
                "pooled_log_loss": (
                    selected[0]
                    if selected is not None
                    else float(
                        group.loc[group["method"] == "logistic_regression", "log_loss"].iloc[0]
                    )
                ),
                "best_baseline_pooled_log_loss": float(baseline_loss.min()),
                "beats_every_baseline_pooled": selected is not None,
                "fold_wins_vs_best_baseline": np.nan,
                "fold_count": np.nan,
                "beats_most_folds": selected is not None,
                "eligible_by_rule": selected is not None,
                "recommendation": "selected_by_rule" if selected is not None else "lr_fallback",
            }
        )
    return pd.DataFrame.from_records(selection_rows)


def _write_csv(records: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def _render_svg(summaries: pd.DataFrame, path: Path) -> None:
    """Write a dependency-free bar chart of pooled dev log loss."""
    main = summaries.loc[summaries["feature_set"] == "all_features"].copy()
    entries = main.sort_values(["window", "log_loss", "method"], kind="mergesort")
    height = max(180, 70 + 34 * len(entries))
    width = 920
    max_loss = max(float(entries["log_loss"].max()), 0.01)
    colors = {"full_history": "#356ae6", "post_split": "#009688"}
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        (
            '<text x="32" y="34" font-family="system-ui, sans-serif" '
            'font-size="20" fill="#152238">'
            "Phase 3 pooled walk-forward log loss (development only)</text>"
        ),
    ]
    for index, (_, entry) in enumerate(entries.iterrows()):
        y = 58 + index * 34
        label = f"{entry['window']} · {entry['method']}"
        bar_width = 340 * float(entry["log_loss"]) / max_loss
        color = colors.get(str(entry["window"]), "#6b7280")
        lines.extend(
            [
                (
                    f'<text x="32" y="{y + 18}" font-family="system-ui, sans-serif" '
                    f'font-size="13" fill="#26364a">{label}</text>'
                ),
                (
                    f'<rect x="410" y="{y}" width="{bar_width:.2f}" height="20" '
                    f'rx="3" fill="{color}"/>'
                ),
                (
                    f'<text x="{420 + bar_width:.2f}" y="{y + 16}" '
                    'font-family="system-ui, sans-serif" font-size="13" '
                    f'fill="#26364a">{float(entry["log_loss"]):.5f}</text>'
                ),
            ]
        )
    lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _format_summary_table(summary: pd.DataFrame) -> list[str]:
    lines = [
        (
            "| Window | Feature set | Method | OOF rows | Log loss | Brier | Accuracy | "
            "Signal coverage | Signal accuracy |"
        ),
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in summary.sort_values(["window", "log_loss", "method"]).iterrows():
        signal_accuracy = row["signal_accuracy"]
        signal_text = "n/a" if pd.isna(signal_accuracy) else f"{signal_accuracy:.2%}"
        lines.append(
            f"| {row['window']} | {row['feature_set']} | {row['method']} | "
            f"{int(row['samples']):,} | "
            f"{row['log_loss']:.5f} | {row['brier']:.5f} | {row['accuracy']:.2%} | "
            f"{row['signal_coverage']:.2%} | {signal_text} |"
        )
    return lines


def _write_results(
    run: DevelopmentRun,
    path: Path,
    *,
    holdout_access_count: int,
) -> None:
    selection = run.selections.loc[run.selections["recommendation"].notna()]
    candidate_evidence = run.selections.loc[run.selections["recommendation"].isna()]
    ablation_summary = run.summaries.loc[run.summaries["feature_set"] != "all_features"]
    recommendation_loss = selection.set_index("window")["pooled_log_loss"]
    lines = [
        "# Development walk-forward results",
        "",
        (
            "These are development-only results. The final 30 NYSE sessions are locked "
            "and were not loaded."
        ),
        "",
        f"- Frozen snapshot: `{run.snapshot_hash}`",
        f"- Code commit: `{run.git_hash}`",
        (
            f"- Final holdout sessions: `{run.holdout_sessions[0]}` through "
            f"`{run.holdout_sessions[-1]}`"
        ),
        f"- Holdout access-log entries: **{holdout_access_count}** (must be zero in Phase 3)",
        f"- Walk-forward: expanding train; {MIN_TRAIN_DAYS} initial NYSE sessions; "
        f"{GAP_DAYS}-session gap; {TEST_DAYS}-session test blocks; seed `{SEED}`.",
        (
            "- The date universe includes excluded event sessions, so the one-session "
            "embargo remains a trading-day embargo even when an event day supplies no "
            "supervised rows."
        ),
        "",
        "## Pooled out-of-fold results",
        "",
        *_format_summary_table(run.summaries.loc[run.summaries["feature_set"] == "all_features"]),
        "",
        (
            "`neutral_50_50`, `always_up`, `always_down`, `majority_class`, and "
            "`previous_candle_direction` signal on every row. The RSI rule uses neutral "
            "P(UP)=0.5 outside RSI<30 / RSI>70, so its signal coverage is intentionally lower."
        ),
        "",
        "## Selection-rule evidence",
        "",
        (
            "A classifier is eligible only when its pooled OOF log loss is lower than every "
            "specified baseline and it beats the best baseline in a strict majority of folds. "
            "If no classifier qualifies, the protocol's logistic-regression fallback is named "
            "without claiming an edge."
        ),
        "",
        "| Window | Recommendation | Basis |",
        "|---|---|---|",
    ]
    for _, row in selection.sort_values("window").iterrows():
        lines.append(f"| {row['window']} | {row['method']} | {row['recommendation']} |")
    if {"full_history", "post_split"}.issubset(recommendation_loss.index):
        difference = (
            float(recommendation_loss["post_split"])
            - float(recommendation_loss["full_history"])
        )
        lines.extend(
            [
                "",
                (
                    "The provisional full-history recommendation has lower pooled log loss by "
                    f"`{difference:.5f}` than the post-split recommendation. This small "
                    "development-only difference does not itself adopt a training window; the "
                    "coverage discontinuity remains an owner decision before Phase 4."
                ),
            ]
        )
    lines.extend(
        [
            "",
            (
                "| Window | Classifier | Beats every baseline pooled? | "
                "Fold wins / folds | Eligible? |"
            ),
            "|---|---|---:|---:|---:|",
        ]
    )
    for _, row in candidate_evidence.sort_values(["window", "pooled_log_loss"]).iterrows():
        lines.append(
            f"| {row['window']} | {row['method']} | "
            f"{bool(row['beats_every_baseline_pooled'])} | "
            f"{int(row['fold_wins_vs_best_baseline'])}/{int(row['fold_count'])} | "
            f"{bool(row['eligible_by_rule'])} |"
        )
    lines.extend(
        [
            "",
            "## Feature-family ablations",
            "",
        (
            "Ablations rerun the window's provisional recommendation after removing one causal "
            "feature family. They are diagnostics only, not a license to change the approved "
            "feature schema after model freeze."
        ),
            "",
        *_format_summary_table(ablation_summary),
            "",
            "## Protocol notes",
            "",
        (
            "- HistGradientBoostingClassifier runs with `early_stopping=False`; it therefore "
            "does not create sklearn's internal random validation split."
        ),
        (
            "- Logistic regression scales within each fold only. All labels, model fitting, "
            "thresholds, and selection remain chronological; no random split was used."
        ),
        (
            "- The optional two-candle-horizon ablation was not run. It is not a candidate "
            "for the shipped next-candle target."
        ),
        (
            "- These figures do not use calibration, threshold tuning, or the final holdout. "
            "Phase 4 performs those locked steps once a training window is approved."
        ),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def run_development_experiments(
    *,
    experiments_path: Path = DEFAULT_EXPERIMENTS_PATH,
    oof_path: Path = DEFAULT_OOF_PATH,
    results_path: Path = DEFAULT_RESULTS_PATH,
    plot_path: Path = DEFAULT_PLOT_PATH,
    holdout_log_path: Path = DEFAULT_HOLDOUT_LOG,
) -> DevelopmentRun:
    """Run every Phase 3 development trial while keeping the final holdout locked."""
    if _holdout_access_count(holdout_log_path):
        raise ExperimentError("Phase 3 requires zero final-holdout access-log entries")
    snapshot = load_frozen_snapshot()
    frame = build_labeled_feature_frame(snapshot)
    all_rows = supervised_rows(frame, window="full_history")
    session_universe = frame["session_date"].astype(str)
    partition = partition_final_holdout(
        all_rows,
        holdout_days=HOLDOUT_DAYS,
        session_universe=session_universe,
        access_log_path=holdout_log_path,
    )
    development = partition.development_frame().sort_values("candle_start").reset_index(drop=True)
    development_sessions = pd.Series(partition.development_sessions)
    git_hash = _git_hash()
    run_at_utc = datetime.now(UTC).isoformat()
    records: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []

    for window in TRAINING_WINDOWS:
        window_rows = development.copy()
        universe = development_sessions
        if window == "post_split":
            window_rows = window_rows.loc[window_rows["session_date"] >= POST_SPLIT_START].copy()
            universe = universe.loc[universe >= POST_SPLIT_START]
        window_rows = window_rows.reset_index(drop=True)
        if window_rows.empty:
            raise ExperimentError(f"{window} has no development rows")
        fold_records, fold_predictions = _fold_records(
            window_rows,
            session_universe=universe,
            window=window,
            feature_set="all_features",
            methods=_method_names(),
            snapshot_hash=snapshot.snapshot_hash,
            git_hash=git_hash,
            run_at_utc=run_at_utc,
        )
        records.extend(fold_records)
        predictions.extend(fold_predictions)

    records_frame = pd.DataFrame.from_records(records)
    oof_frame = pd.DataFrame.from_records(predictions)
    summary_frames = [
        _pooled_summaries(oof_frame, records_frame, window=window, feature_set="all_features")
        for window in TRAINING_WINDOWS
    ]
    summaries = pd.concat(summary_frames, ignore_index=True)
    selections = _selection_summary(summaries, records_frame)

    # Feature-family ablations use each window's development-only provisional
    # recommendation. They cannot influence which full-feature model won.
    recommendation_rows = selections.loc[selections["recommendation"].notna()]
    for _, recommendation in recommendation_rows.iterrows():
        window = str(recommendation["window"])
        method = str(recommendation["method"])
        window_rows = development.copy()
        universe = development_sessions
        if window == "post_split":
            window_rows = window_rows.loc[window_rows["session_date"] >= POST_SPLIT_START].copy()
            universe = universe.loc[universe >= POST_SPLIT_START]
        window_rows = window_rows.reset_index(drop=True)
        for family in FEATURE_FAMILIES:
            feature_set = f"without_{family}"
            ablation_records, ablation_predictions = _fold_records(
                window_rows,
                session_universe=universe,
                window=window,
                feature_set=feature_set,
                methods=(method,),
                snapshot_hash=snapshot.snapshot_hash,
                git_hash=git_hash,
                run_at_utc=run_at_utc,
            )
            records.extend(ablation_records)
            predictions.extend(ablation_predictions)

    records_frame = pd.DataFrame.from_records(records)
    oof_frame = pd.DataFrame.from_records(predictions)
    ablation_summaries = [
        _pooled_summaries(oof_frame, records_frame, window=window, feature_set=feature_set)
        for window in TRAINING_WINDOWS
        for feature_set in (f"without_{family}" for family in FEATURE_FAMILIES)
    ]
    summaries = pd.concat([summaries, *ablation_summaries], ignore_index=True)
    run = DevelopmentRun(
        records=records_frame,
        oof_predictions=oof_frame,
        summaries=summaries,
        selections=selections,
        snapshot_hash=snapshot.snapshot_hash,
        git_hash=git_hash,
        holdout_sessions=partition.holdout_sessions,
        development_sessions=partition.development_sessions,
    )
    _write_csv(run.records, experiments_path)
    oof_path.parent.mkdir(parents=True, exist_ok=True)
    run.oof_predictions.to_parquet(oof_path, index=False)
    _render_svg(run.summaries, plot_path)
    _write_results(run, results_path, holdout_access_count=_holdout_access_count(holdout_log_path))
    return run
