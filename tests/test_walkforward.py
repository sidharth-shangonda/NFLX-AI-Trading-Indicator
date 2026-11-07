from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from eval.walkforward import (
    HoldoutAccessError,
    TradingDayWalkForward,
    WalkForwardError,
    partition_final_holdout,
)


def _frame(days: int = 13) -> pd.DataFrame:
    sessions = pd.bdate_range("2026-01-05", periods=days)
    return pd.DataFrame(
        {
            "session_date": [day.date().isoformat() for day in sessions for _ in range(2)],
            "row_value": range(days * 2),
        }
    )


def test_walk_forward_grows_training_and_keeps_whole_day_gap() -> None:
    frame = _frame()
    splitter = TradingDayWalkForward(min_train_days=4, gap_days=1, test_days=3)
    folds = splitter.split(frame["session_date"])

    assert len(folds) == 3
    assert folds[0].train_sessions == (
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-01-08",
    )
    assert folds[0].gap_sessions == ("2026-01-09",)
    assert folds[0].test_sessions == (
        "2026-01-12",
        "2026-01-13",
        "2026-01-14",
    )
    # The prior fold's final test day becomes this fold's one-day embargo;
    # earlier prior-test days may join the expanding train window.
    assert folds[1].train_sessions[-1] == "2026-01-13"
    assert folds[1].gap_sessions == ("2026-01-14",)
    assert folds[1].test_sessions[0] == "2026-01-15"

    for fold in folds:
        train, gap, test = fold.masks(frame["session_date"])
        assert not (train & gap).any()
        assert not (train & test).any()
        assert not (gap & test).any()
        assert train.sum() == len(fold.train_sessions) * 2
        assert test.sum() == len(fold.test_sessions) * 2
        assert max(fold.train_sessions) < min(fold.gap_sessions) < min(fold.test_sessions)


def test_walk_forward_rejects_insufficient_sessions() -> None:
    with pytest.raises(WalkForwardError, match="not enough trading days"):
        TradingDayWalkForward(min_train_days=4, gap_days=1, test_days=3).split(
            _frame(5)["session_date"]
        )


def test_holdout_is_locked_and_development_never_logs_access(tmp_path: Path) -> None:
    access_log = tmp_path / "holdout_access.log"
    partition = partition_final_holdout(_frame(10), holdout_days=3, access_log_path=access_log)

    development = partition.development_frame()
    assert development["session_date"].nunique() == 7
    assert development["session_date"].max() == "2026-01-13"
    assert not access_log.exists()

    with pytest.raises(HoldoutAccessError, match="ALLOW_HOLDOUT=1"):
        partition.load_holdout(purpose="phase-4 final evaluation", environment={})
    assert not access_log.exists()


def test_allowed_holdout_access_logs_a_small_non_secret_record(tmp_path: Path) -> None:
    access_log = tmp_path / "holdout_access.log"
    partition = partition_final_holdout(_frame(10), holdout_days=3, access_log_path=access_log)

    holdout = partition.load_holdout(
        purpose="phase-4 final evaluation", environment={"ALLOW_HOLDOUT": "1"}
    )

    assert holdout["session_date"].nunique() == 3
    event = pd.read_json(access_log, lines=True).iloc[0].to_dict()
    assert event["purpose"] == "phase-4 final evaluation"
    assert event["holdout_first_session"] == "2026-01-14"
    assert event["holdout_last_session"] == "2026-01-16"
    assert event["row_count"] == 6


def test_holdout_uses_calendar_universe_even_without_eligible_rows(tmp_path: Path) -> None:
    frame = _frame(8)
    # Simulate an excluded event session: it remains in the calendar, but has
    # no eligible supervised rows in the input frame.
    missing_session = "2026-01-12"
    eligible = frame.loc[frame["session_date"] != missing_session].copy()
    calendar = _frame(8)["session_date"]

    partition = partition_final_holdout(
        eligible,
        holdout_days=3,
        session_universe=calendar,
        access_log_path=tmp_path / "holdout_access.log",
    )

    assert partition.holdout_sessions == ("2026-01-12", "2026-01-13", "2026-01-14")
    assert partition.development_frame()["session_date"].max() == "2026-01-09"
