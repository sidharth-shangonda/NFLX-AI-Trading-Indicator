from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.prediction import (
    PredictionError,
    evaluate_probabilities,
    fit_predict,
    method_parameters,
)


def _features(rows: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "return_1": np.linspace(-0.02, 0.02, rows),
            "rsi_14": np.linspace(20.0, 80.0, rows),
            "other": np.arange(rows, dtype=float),
        }
    )


def test_baselines_only_use_train_target_and_define_rsi_no_signal_as_neutral() -> None:
    train_x = _features(12)
    test_x = _features(4)
    train_y = pd.Series([1] * 9 + [0] * 3)

    majority = fit_predict(
        "majority_class",
        train_features=train_x,
        train_target=train_y,
        test_features=test_x,
        seed=7,
    )
    rsi = fit_predict(
        "rsi_rule",
        train_features=train_x,
        train_target=train_y,
        test_features=test_x,
        seed=7,
    )

    assert majority.probabilities.tolist() == [1.0] * 4
    assert rsi.probabilities.tolist() == [1.0, 0.5, 0.5, 0.0]
    assert rsi.signal_mask.tolist() == [True, False, False, True]


@pytest.mark.parametrize(
    "method", ["logistic_regression", "hist_gradient_boosting", "random_forest"]
)
def test_classifiers_are_seeded_and_emit_valid_probabilities(method: str) -> None:
    train_x = _features(20)
    test_x = _features(5)
    train_y = pd.Series([0, 1] * 10)

    first = fit_predict(
        method,
        train_features=train_x,
        train_target=train_y,
        test_features=test_x,
        seed=19,
    )
    second = fit_predict(
        method,
        train_features=train_x,
        train_target=train_y,
        test_features=test_x,
        seed=19,
    )

    assert np.all((0.0 <= first.probabilities) & (first.probabilities <= 1.0))
    assert np.allclose(first.probabilities, second.probabilities)


def test_metrics_clip_extreme_probability_and_keep_rule_coverage() -> None:
    metrics = evaluate_probabilities(
        np.array([0, 1, 0, 1]),
        np.array([0.0, 1.0, 1.0, 0.0]),
        signal_mask=np.array([False, True, True, False]),
    )

    assert metrics["samples"] == 4
    assert metrics["signal_count"] == 2
    assert metrics["signal_coverage"] == 0.5
    assert metrics["signal_accuracy"] == 0.5
    assert metrics["log_loss"] > 0


def test_predict_rejects_schema_mismatch() -> None:
    with pytest.raises(PredictionError, match="schemas differ"):
        fit_predict(
            "logistic_regression",
            train_features=_features(4),
            train_target=pd.Series([0, 1, 0, 1]),
            test_features=_features(4).drop(columns="other"),
            seed=1,
        )


def test_hgb_configuration_disables_internal_random_validation_split() -> None:
    assert method_parameters("hist_gradient_boosting")["early_stopping"] is False
