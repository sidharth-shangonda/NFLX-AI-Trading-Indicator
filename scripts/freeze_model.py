"""Owner-authorized Phase 4 model training and freeze."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ["ALLOW_HOLDOUT"] = "1"

from eval.freeze import FreezeError, freeze_model_once  # noqa: E402
from nflx_indicator.training_data import TrainingDataError  # noqa: E402


def main() -> int:
    try:
        evaluation = freeze_model_once(force=True)
    except (FreezeError, TrainingDataError) as exc:
        print(f"PHASE4_BLOCKER {exc}")
        return 2
    acc_text = (
        f"{evaluation.holdout_metrics['signal_accuracy']:.2%}"
        if evaluation.holdout_metrics["signal_accuracy"] is not None
        else "n/a"
    )
    signals = evaluation.holdout_metrics["signal_count"]
    samples = evaluation.holdout_metrics["samples"]
    coverage = evaluation.holdout_metrics["coverage"]
    wilson_lb = evaluation.holdout_metrics["signal_wilson_lower_bound"]
    print(
        "PHASE4_FROZEN "
        f"model={evaluation.artifact.model_version} "
        f"method={evaluation.artifact.method} "
        f"artifact={evaluation.artifact_hash} "
        f"holdout={evaluation.holdout_first_session}..{evaluation.holdout_last_session} "
        f"signals={signals}/{samples} "
        f"coverage={coverage:.2%} "
        f"test_accuracy={acc_text} "
        f"wilson_lower_bound={wilson_lb:.2%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
