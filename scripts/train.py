"""Train, evaluate, and verify the production model."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval.freeze import FreezeError, freeze_model_once  # noqa: E402
from eval.frozen_model import (  # noqa: E402
    FrozenModelVerificationError,
    verify_frozen_model,
)
from nflx_indicator.training_data import TrainingDataError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train, evaluate on holdout test set, and verify model artifact."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="only verify existing frozen model without retraining",
    )
    args = parser.parse_args()

    if not args.verify_only:
        os.environ["ALLOW_HOLDOUT"] = "1"
        try:
            eval_res = freeze_model_once(force=True)
            acc = eval_res.holdout_metrics["signal_accuracy"]
            acc_str = f"{acc:.2%}" if acc is not None else "n/a"
            signals = eval_res.holdout_metrics["signal_count"]
            samples = eval_res.holdout_metrics["samples"]
            coverage = eval_res.holdout_metrics["coverage"]
            wilson_lb = eval_res.holdout_metrics["signal_wilson_lower_bound"]
            sessions = f"{eval_res.holdout_first_session}..{eval_res.holdout_last_session}"
            print(
                "TRAIN_AND_EVALUATE_COMPLETE "
                f"method={eval_res.artifact.method} "
                f"holdout_sessions={sessions} "
                f"test_signals={signals}/{samples} "
                f"coverage={coverage:.2%} "
                f"test_accuracy={acc_str} "
                f"wilson_lower_bound={wilson_lb:.2%}"
            )
        except (FreezeError, TrainingDataError) as exc:
            print(f"TRAIN_BLOCKER {exc}")
            return 2

    try:
        result = verify_frozen_model()
    except (FrozenModelVerificationError, TrainingDataError) as exc:
        print(f"FROZEN_MODEL_BLOCKER {exc}")
        return 2

    print(
        "FROZEN_MODEL_VERIFIED "
        f"model={result.model_version} "
        f"method={result.method} "
        f"artifact={result.artifact_hash} "
        f"features={result.feature_count} "
        f"candles={result.candle_count} "
        f"feature_ready={result.feature_ready_count} "
        f"up={result.up_count} "
        f"down={result.down_count} "
        f"no_clear_signal={result.no_clear_signal_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
