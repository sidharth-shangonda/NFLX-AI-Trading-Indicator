from __future__ import annotations

import numpy as np

from eval.metrics import (
    direction_and_signal,
    directional_metrics,
    select_delta,
    wilson_lower_bound,
)


def test_delta_selection_uses_only_eligible_coverage_and_wilson_ordering() -> None:
    target = np.array([1, 1, 0, 0, 0, 1, 1, 0, 0, 1])
    probability = np.array([0.9, 0.8, 0.1, 0.2, 0.55, 0.45, 0.6, 0.4, 0.51, 0.49])

    delta, table = select_delta(target, probability, minimum_coverage=0.4, candidates=[0.0, 0.1])

    assert delta == 0.1
    assert table.loc[table["delta"] == 0.1, "meets_minimum_coverage"].item()
    assert wilson_lower_bound(8, 10) < 0.8


def test_directional_metrics_use_two_per_side_costs_and_no_signal_state() -> None:
    probability = np.array([0.7, 0.3, 0.51, 0.49])
    direction, signal = direction_and_signal(probability, 0.1)
    assert direction.tolist() == [1, -1, 0, 0]
    assert signal.tolist() == [True, True, False, False]

    metrics = directional_metrics(
        np.array([1, 0, 1, 0]),
        probability,
        delta=0.1,
        next_return=np.array([0.001, -0.002, 0.0, 0.0]),
    )
    assert metrics["signal_count"] == 2
    assert metrics["signal_accuracy"] == 1.0
    assert metrics["simulated_pnl_bp"]["1.0"]["total"] == 26.0
