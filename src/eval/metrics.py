"""Honest evaluation helpers shared by the model freeze and later scoring."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, log_loss, matthews_corrcoef


class MetricError(ValueError):
    """Raised when evaluation inputs are not aligned binary observations."""


def _binary(values: Iterable[object]) -> np.ndarray:
    result = np.asarray(list(values), dtype=float)
    if result.ndim != 1 or not len(result):
        raise MetricError("expected a non-empty one-dimensional binary vector")
    if not np.isfinite(result).all() or not np.isin(result, (0.0, 1.0)).all():
        raise MetricError("binary vector must contain only zero and one")
    return result.astype(int)


def wilson_lower_bound(successes: int, total: int, z: float = 1.96) -> float:
    """Two-sided 95% Wilson lower confidence bound for an observed proportion."""
    if total <= 0:
        return 0.0
    proportion = successes / total
    denominator = 1.0 + z**2 / total
    centre = proportion + z**2 / (2.0 * total)
    spread = z * np.sqrt(proportion * (1.0 - proportion) / total + z**2 / (4.0 * total**2))
    return float((centre - spread) / denominator)


def direction_and_signal(
    probabilities: Iterable[object], delta: float
) -> tuple[np.ndarray, np.ndarray]:
    """Convert calibrated P(UP) into UP/DOWN/no-signal without hidden tie rules."""
    if not 0.0 <= delta < 0.5:
        raise MetricError("delta must be between zero and 0.5")
    probability = np.asarray(list(probabilities), dtype=float)
    if probability.ndim != 1 or not np.isfinite(probability).all():
        raise MetricError("probabilities must be a finite one-dimensional vector")
    if (probability < 0.0).any() or (probability > 1.0).any():
        raise MetricError("probabilities must lie between zero and one")
    direction = np.zeros(len(probability), dtype=int)
    direction[probability >= 0.5 + delta] = 1
    direction[probability <= 0.5 - delta] = -1
    return direction, direction != 0


def select_delta(
    target_up: Iterable[object],
    probabilities: Iterable[object],
    *,
    minimum_coverage: float = 0.10,
    candidates: Iterable[float] = tuple(np.arange(0.0, 0.151, 0.005)),
) -> tuple[float, pd.DataFrame]:
    """Choose threshold only from development predictions by Wilson lower bound."""
    actual = _binary(target_up)
    probability = np.asarray(list(probabilities), dtype=float)
    if len(actual) != len(probability):
        raise MetricError("target and probability lengths differ")
    if not 0.0 < minimum_coverage <= 1.0:
        raise MetricError("minimum coverage must lie in (0, 1]")
    rows: list[dict[str, Any]] = []
    for candidate in sorted({float(value) for value in candidates}):
        direction, signal = direction_and_signal(probability, candidate)
        count = int(signal.sum())
        coverage = count / len(actual)
        correct = int(((direction[signal] == 1) == (actual[signal] == 1)).sum()) if count else 0
        rows.append(
            {
                "delta": candidate,
                "signal_count": count,
                "coverage": coverage,
                "signal_accuracy": correct / count if count else None,
                "wilson_lower_bound": wilson_lower_bound(correct, count),
                "meets_minimum_coverage": coverage >= minimum_coverage,
            }
        )
    table = pd.DataFrame.from_records(rows)
    eligible = table.loc[table["meets_minimum_coverage"]]
    if eligible.empty:
        raise MetricError("no threshold reaches the required development coverage")
    winner = eligible.sort_values(
        ["wilson_lower_bound", "signal_accuracy", "delta"],
        ascending=[False, False, False],
        kind="mergesort",
    ).iloc[0]
    return float(winner["delta"]), table


def reliability_table(
    target_up: Iterable[object], probabilities: Iterable[object], bins: int = 10
) -> pd.DataFrame:
    """Return fixed-width reliability bins; empty bins are intentionally omitted."""
    actual = _binary(target_up)
    probability = np.asarray(list(probabilities), dtype=float)
    if len(actual) != len(probability):
        raise MetricError("target and probability lengths differ")
    if bins < 2:
        raise MetricError("at least two reliability bins are required")
    bucket = np.minimum((probability * bins).astype(int), bins - 1)
    rows: list[dict[str, float | int]] = []
    for index in range(bins):
        mask = bucket == index
        if not mask.any():
            continue
        rows.append(
            {
                "bin": index,
                "lower": index / bins,
                "upper": (index + 1) / bins,
                "count": int(mask.sum()),
                "mean_predicted_probability": float(probability[mask].mean()),
                "observed_up_rate": float(actual[mask].mean()),
            }
        )
    return pd.DataFrame.from_records(rows)


def probability_metrics(
    target_up: Iterable[object], probabilities: Iterable[object]
) -> dict[str, float]:
    """Calculate proper probability metrics without turning a hard rule into certainty."""
    actual = _binary(target_up)
    probability = np.asarray(list(probabilities), dtype=float)
    if len(actual) != len(probability):
        raise MetricError("target and probability lengths differ")
    clipped = np.clip(probability, 1e-6, 1.0 - 1e-6)
    return {
        "log_loss": float(log_loss(actual, clipped, labels=[0, 1])),
        "brier": float(brier_score_loss(actual, probability)),
    }


def directional_metrics(
    target_up: Iterable[object],
    probabilities: Iterable[object],
    *,
    delta: float,
    next_return: Iterable[object] | None = None,
    costs_bp: Iterable[float] = (0.0, 1.0, 2.0, 3.0),
) -> dict[str, Any]:
    """Metrics for confident signals; P&L is explicitly an assumed-cost simulation."""
    actual = _binary(target_up)
    probability = np.asarray(list(probabilities), dtype=float)
    if len(actual) != len(probability):
        raise MetricError("target and probability lengths differ")
    direction, signal = direction_and_signal(probability, delta)
    count = int(signal.sum())
    output: dict[str, Any] = {
        "samples": int(len(actual)),
        "signal_count": count,
        "coverage": float(count / len(actual)),
        "delta": float(delta),
        "signal_accuracy": None,
        "signal_wilson_lower_bound": 0.0,
        "signal_balanced_accuracy": None,
        "signal_mcc": None,
        "confusion_matrix": {"true_down_pred_down": 0, "true_down_pred_up": 0,
                             "true_up_pred_down": 0, "true_up_pred_up": 0},
        "simulated_pnl_bp": {},
    }
    if not count:
        return output
    observed = actual[signal]
    predicted = (direction[signal] == 1).astype(int)
    successes = int((observed == predicted).sum())
    output["signal_accuracy"] = float(successes / count)
    output["signal_wilson_lower_bound"] = wilson_lower_bound(successes, count)
    output["signal_balanced_accuracy"] = float(balanced_accuracy_score(observed, predicted))
    output["signal_mcc"] = float(matthews_corrcoef(observed, predicted))
    output["confusion_matrix"] = {
        "true_down_pred_down": int(((observed == 0) & (predicted == 0)).sum()),
        "true_down_pred_up": int(((observed == 0) & (predicted == 1)).sum()),
        "true_up_pred_down": int(((observed == 1) & (predicted == 0)).sum()),
        "true_up_pred_up": int(((observed == 1) & (predicted == 1)).sum()),
    }
    if next_return is not None:
        returns = np.asarray(list(next_return), dtype=float)
        if len(returns) != len(actual) or not np.isfinite(returns).all():
            raise MetricError("next returns must align with finite target rows")
        gross_bp = direction[signal] * returns[signal] * 10_000.0
        for cost in costs_bp:
            if cost < 0:
                raise MetricError("cost assumptions cannot be negative")
            # Each signal represents an entry and exit, hence two per-side costs.
            net_bp = gross_bp - 2.0 * float(cost)
            output["simulated_pnl_bp"][str(float(cost))] = {
                "total": float(net_bp.sum()),
                "mean_per_signal": float(net_bp.mean()),
            }
    return output
