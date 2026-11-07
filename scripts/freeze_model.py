"""Owner-authorized one-time Phase 4 model freeze."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval.freeze import FreezeError, freeze_model_once  # noqa: E402
from nflx_indicator.training_data import TrainingDataError  # noqa: E402


def main() -> int:
    try:
        evaluation = freeze_model_once()
    except (FreezeError, TrainingDataError) as exc:
        print(f"PHASE4_BLOCKER {exc}")
        return 2
    print(
        "PHASE4_FROZEN "
        f"artifact={evaluation.artifact_hash} "
        f"holdout={evaluation.holdout_first_session}..{evaluation.holdout_last_session} "
        f"coverage={evaluation.holdout_metrics['coverage']:.6f} "
        f"signals={evaluation.holdout_metrics['signal_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
