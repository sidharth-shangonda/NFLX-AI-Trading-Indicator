"""Specified baselines and deterministic sklearn classifiers for development."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASELINE_NAMES: Final = (
    "neutral_50_50",
    "always_up",
    "always_down",
    "majority_class",
    "previous_candle_direction",
    "rsi_rule",
)
CLASSIFIER_NAMES: Final = (
    "logistic_regression",
    "hist_gradient_boosting",
    "random_forest",
)
ALL_METHOD_NAMES: Final = BASELINE_NAMES + CLASSIFIER_NAMES
_PROBABILITY_EPSILON: Final = 1e-6


class PredictionError(ValueError):
    """Raised when a model or baseline cannot safely make a probability."""


@dataclass(frozen=True)
class PredictionOutput:
    """Probabilities plus which rows a rule baseline actually signalled on."""

    probabilities: np.ndarray
    signal_mask: np.ndarray
    fitted_estimator: Any | None = None


def method_parameters(method: str) -> dict[str, Any]:
    """Return the fixed, pre-specified configuration logged for a method."""
    if method in BASELINE_NAMES:
        return {"kind": "baseline"}
    if method == "logistic_regression":
        return {
            "C": 1.0,
            "max_iter": 1_000,
            "scaler": "StandardScaler",
            "solver": "lbfgs",
        }
    if method == "hist_gradient_boosting":
        return {
            "early_stopping": False,
            "l2_regularization": 1.0,
            "learning_rate": 0.05,
            "max_iter": 150,
            "max_leaf_nodes": 15,
        }
    if method == "random_forest":
        return {
            "max_depth": 6,
            "max_features": "sqrt",
            "min_samples_leaf": 20,
            "n_estimators": 150,
        }
    raise PredictionError(f"unknown method: {method}")


def _target_array(values: pd.Series | np.ndarray) -> np.ndarray:
    target = np.asarray(values, dtype=float)
    if target.ndim != 1 or not len(target):
        raise PredictionError("target must be a non-empty one-dimensional array")
    if not np.isfinite(target).all() or not np.isin(target, (0.0, 1.0)).all():
        raise PredictionError("target must contain only finite binary values")
    return target.astype(int)


def _feature_frame(values: pd.DataFrame) -> pd.DataFrame:
    if values.empty:
        raise PredictionError("feature frame cannot be empty")
    numeric = values.astype(float)
    if not np.isfinite(numeric.to_numpy()).all():
        raise PredictionError("feature frame contains missing or non-finite values")
    return numeric


def _classifier(method: str, *, seed: int) -> Any:
    if method == "logistic_regression":
        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=1.0,
                        max_iter=1_000,
                        random_state=seed,
                        solver="lbfgs",
                    ),
                ),
            ]
        )
    if method == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            learning_rate=0.05,
            l2_regularization=1.0,
            max_iter=150,
            max_leaf_nodes=15,
            early_stopping=False,
            random_state=seed,
        )
    if method == "random_forest":
        return RandomForestClassifier(
            n_estimators=150,
            max_depth=6,
            min_samples_leaf=20,
            max_features="sqrt",
            n_jobs=-1,
            random_state=seed,
        )
    raise PredictionError(f"unknown classifier: {method}")


def _baseline_predictions(
    method: str,
    *,
    train_target: np.ndarray,
    test_features: pd.DataFrame,
) -> PredictionOutput:
    count = len(test_features)
    if method == "neutral_50_50":
        return PredictionOutput(np.full(count, 0.5), np.ones(count, dtype=bool))
    if method == "always_up":
        return PredictionOutput(np.ones(count), np.ones(count, dtype=bool))
    if method == "always_down":
        return PredictionOutput(np.zeros(count), np.ones(count, dtype=bool))
    if method == "majority_class":
        probability = float(train_target.mean() >= 0.5)
        return PredictionOutput(np.full(count, probability), np.ones(count, dtype=bool))
    if method == "previous_candle_direction":
        if "return_1" not in test_features:
            raise PredictionError("previous_candle_direction baseline requires return_1")
        returns = test_features["return_1"].to_numpy(dtype=float)
        fallback = float(train_target.mean() >= 0.5)
        probabilities = np.where(returns > 0, 1.0, np.where(returns < 0, 0.0, fallback))
        return PredictionOutput(probabilities, np.ones(count, dtype=bool))
    if method == "rsi_rule":
        if "rsi_14" not in test_features:
            raise PredictionError("rsi_rule baseline requires rsi_14")
        rsi = test_features["rsi_14"].to_numpy(dtype=float)
        up_signal = rsi < 30.0
        down_signal = rsi > 70.0
        probabilities = np.full(count, 0.5)
        probabilities[up_signal] = 1.0
        probabilities[down_signal] = 0.0
        return PredictionOutput(probabilities, up_signal | down_signal)
    raise PredictionError(f"unknown baseline: {method}")


def fit_predict(
    method: str,
    *,
    train_features: pd.DataFrame,
    train_target: pd.Series | np.ndarray,
    test_features: pd.DataFrame,
    seed: int,
) -> PredictionOutput:
    """Fit only on a fold's train rows and predict P(UP) for its test rows."""
    if method not in ALL_METHOD_NAMES:
        raise PredictionError(f"unknown method: {method}")
    train_x = _feature_frame(train_features)
    test_x = _feature_frame(test_features)
    if tuple(train_x.columns) != tuple(test_x.columns):
        raise PredictionError("train and test feature schemas differ")
    target = _target_array(train_target)
    if len(train_x) != len(target):
        raise PredictionError("train feature and target lengths differ")
    if method in BASELINE_NAMES:
        return _baseline_predictions(method, train_target=target, test_features=test_x)

    # A very small or degenerate early walk-forward fold is still evaluated
    # honestly as its train prevalence rather than crashing or peeking ahead.
    if np.unique(target).size == 1:
        return PredictionOutput(
            np.full(len(test_x), float(target[0])),
            np.ones(len(test_x), dtype=bool),
            fitted_estimator=None,
        )
    estimator = _classifier(method, seed=seed)
    estimator.fit(train_x, target)
    probability = estimator.predict_proba(test_x)[:, 1]
    return PredictionOutput(
        probabilities=np.asarray(probability, dtype=float),
        signal_mask=np.ones(len(test_x), dtype=bool),
        fitted_estimator=estimator,
    )


def fit_classifier(
    method: str,
    *,
    train_features: pd.DataFrame,
    train_target: pd.Series | np.ndarray,
    seed: int,
) -> Any:
    """Fit one configured trained classifier for a frozen artifact.

    This is intentionally separate from walk-forward prediction: a caller can
    serialize the exact estimator it evaluates, without retraining it later.
    """
    if method not in CLASSIFIER_NAMES:
        raise PredictionError(f"unknown classifier: {method}")
    train_x = _feature_frame(train_features)
    target = _target_array(train_target)
    if len(train_x) != len(target):
        raise PredictionError("train feature and target lengths differ")
    if np.unique(target).size < 2:
        raise PredictionError("a frozen classifier requires both target classes")
    estimator = _classifier(method, seed=seed)
    estimator.fit(train_x, target)
    return estimator


def evaluate_probabilities(
    target: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    *,
    signal_mask: np.ndarray | None = None,
) -> dict[str, float | int | None]:
    """Return deterministic probability and direction metrics for one test fold."""
    actual = _target_array(target)
    probability = np.asarray(probabilities, dtype=float)
    if probability.ndim != 1 or len(probability) != len(actual):
        raise PredictionError("probability and target lengths differ")
    if not np.isfinite(probability).all():
        raise PredictionError("probabilities must be finite")
    if (probability < 0).any() or (probability > 1).any():
        raise PredictionError("probabilities must lie between zero and one")
    clipped = np.clip(probability, _PROBABILITY_EPSILON, 1.0 - _PROBABILITY_EPSILON)
    direction = (probability >= 0.5).astype(int)
    signals = (
        np.ones(len(actual), dtype=bool)
        if signal_mask is None
        else np.asarray(signal_mask, dtype=bool)
    )
    if signals.shape != actual.shape:
        raise PredictionError("signal-mask and target lengths differ")
    signal_count = int(signals.sum())
    return {
        "samples": int(len(actual)),
        "up_rate": float(actual.mean()),
        "log_loss": float(log_loss(actual, clipped, labels=[0, 1])),
        "brier": float(brier_score_loss(actual, probability)),
        "accuracy": float(accuracy_score(actual, direction)),
        "balanced_accuracy": float(balanced_accuracy_score(actual, direction)),
        "signal_count": signal_count,
        "signal_coverage": float(signal_count / len(actual)),
        "signal_accuracy": (
            float(accuracy_score(actual[signals], direction[signals])) if signal_count else None
        ),
    }
