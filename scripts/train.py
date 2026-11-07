"""Run Phase 3 development-only chronological model experiments."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval.experiments import ExperimentError, run_development_experiments  # noqa: E402
from nflx_indicator.training_data import TrainingDataError  # noqa: E402


def main() -> int:
    try:
        run = run_development_experiments()
    except (ExperimentError, TrainingDataError) as exc:
        print(f"PHASE3_BLOCKER {exc}")
        return 2
    recommendations = run.selections.loc[run.selections["recommendation"].notna()]
    recommendation_text = ",".join(
        f"{row.window}:{row.method}:{row.recommendation}"
        for row in recommendations.itertuples(index=False)
    )
    print(
        "PHASE3_DEV "
        f"snapshot={run.snapshot_hash} "
        f"git={run.git_hash} "
        f"fold_trials={len(run.records)} "
        f"holdout={run.holdout_sessions[0]}..{run.holdout_sessions[-1]} "
        f"recommendations={recommendation_text}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
