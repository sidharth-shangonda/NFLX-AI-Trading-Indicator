from __future__ import annotations

import pandas as pd

from eval.experiments import _selection_summary


def test_selection_requires_every_baseline_pooled_and_majority_fold_wins() -> None:
    methods = [
        "neutral_50_50",
        "always_up",
        "always_down",
        "majority_class",
        "previous_candle_direction",
        "rsi_rule",
        "logistic_regression",
        "hist_gradient_boosting",
        "random_forest",
    ]
    losses = {method: 0.70 for method in methods}
    losses["logistic_regression"] = 0.65
    losses["hist_gradient_boosting"] = 0.64
    losses["random_forest"] = 0.71
    summaries = pd.DataFrame(
        {
            "window": ["post_split"] * len(methods),
            "feature_set": ["all_features"] * len(methods),
            "method": methods,
            "log_loss": [losses[method] for method in methods],
        }
    )
    records = pd.DataFrame(
        [
            {
                "window": "post_split",
                "feature_set": "all_features",
                "method": method,
                "fold": fold,
                "log_loss": loss,
            }
            for fold in (1, 2, 3)
            for method, loss in losses.items()
        ]
    )
    records.loc[
        (records["method"] == "hist_gradient_boosting")
        & records["fold"].isin([1, 2]),
        "log_loss",
    ] = 0.72
    records.loc[
        (records["method"] == "hist_gradient_boosting") & (records["fold"] == 3),
        "log_loss",
    ] = 0.48

    selection = _selection_summary(summaries, records)

    recommendation = selection.loc[selection["recommendation"].notna()].iloc[0]
    assert recommendation["method"] == "logistic_regression"
    assert recommendation["recommendation"] == "selected_by_rule"
