"""Trading-day walk-forward splits and a guarded final-holdout partition.

These utilities intentionally operate on session labels rather than rows.  A
five-minute data set has many rows per session, so a row-based splitter would
otherwise let adjacent rows from one trading day leak across a fold boundary.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOLDOUT_ACCESS_LOG = PROJECT_ROOT / "experiments" / "holdout_access.log"


class WalkForwardError(ValueError):
    """Raised when session labels cannot form a valid chronological split."""


class HoldoutAccessError(PermissionError):
    """Raised when code attempts to load the final holdout without authorization."""


def _normalized_session_labels(session_dates: Sequence[object] | pd.Series) -> pd.Series:
    """Return canonical ISO dates, rejecting missing or non-date session labels."""
    values = pd.Series(session_dates, copy=False)
    if values.empty:
        raise WalkForwardError("at least one session date is required")
    parsed = pd.to_datetime(values, errors="coerce")
    if parsed.isna().any():
        raise WalkForwardError("session dates must all be valid dates")
    return parsed.dt.date.astype(str)


@dataclass(frozen=True)
class WalkForwardFold:
    """A chronological train/gap/test allocation expressed as NYSE session dates."""

    number: int
    train_sessions: tuple[str, ...]
    gap_sessions: tuple[str, ...]
    test_sessions: tuple[str, ...]

    def masks(self, session_dates: Sequence[object] | pd.Series) -> tuple[pd.Series, ...]:
        """Return aligned train, gap, and test masks for rows with session labels."""
        labels = _normalized_session_labels(session_dates)
        return (
            labels.isin(self.train_sessions),
            labels.isin(self.gap_sessions),
            labels.isin(self.test_sessions),
        )


@dataclass(frozen=True)
class TradingDayWalkForward:
    """Expanding-window splitter with a whole-session embargo before each test block."""

    min_train_days: int = 60
    test_days: int = 20
    gap_days: int = 1
    include_partial_last_test: bool = True

    def __post_init__(self) -> None:
        if self.min_train_days < 1:
            raise WalkForwardError("min_train_days must be at least one")
        if self.test_days < 1:
            raise WalkForwardError("test_days must be at least one")
        if self.gap_days < 0:
            raise WalkForwardError("gap_days cannot be negative")

    def split(self, session_dates: Sequence[object] | pd.Series) -> tuple[WalkForwardFold, ...]:
        """Create chronological folds without shuffling or crossing trading days.

        Each train set begins at the oldest available day and grows after every
        test block.  The immediately following ``gap_days`` are never present
        in either train or test for that fold.
        """
        labels = _normalized_session_labels(session_dates)
        sessions = tuple(sorted(labels.unique().tolist()))
        first_test_start = self.min_train_days + self.gap_days
        if len(sessions) <= first_test_start:
            raise WalkForwardError(
                "not enough trading days for the requested training window and gap"
            )

        folds: list[WalkForwardFold] = []
        test_start = first_test_start
        fold_number = 1
        while test_start < len(sessions):
            remaining_days = len(sessions) - test_start
            if remaining_days < self.test_days and not self.include_partial_last_test:
                break
            test_end = min(test_start + self.test_days, len(sessions))
            gap_start = test_start - self.gap_days
            train_sessions = sessions[:gap_start]
            gap_sessions = sessions[gap_start:test_start]
            test_sessions = sessions[test_start:test_end]
            if not train_sessions or not test_sessions:
                break
            folds.append(
                WalkForwardFold(
                    number=fold_number,
                    train_sessions=train_sessions,
                    gap_sessions=gap_sessions,
                    test_sessions=test_sessions,
                )
            )
            fold_number += 1
            test_start = test_end

        if not folds:
            raise WalkForwardError("the requested split produced no test folds")
        return tuple(folds)


@dataclass(frozen=True)
class HoldoutPartition:
    """Dev rows plus a single-touch guarded final holdout.

    ``development_frame`` never accesses or logs the holdout.  A caller must
    explicitly set ``ALLOW_HOLDOUT=1`` to obtain the final period; the access
    is append-only and intentionally excludes inputs, outputs, and secrets.
    """

    frame: pd.DataFrame = field(repr=False)
    session_column: str
    development_sessions: tuple[str, ...]
    holdout_sessions: tuple[str, ...]
    access_log_path: Path = DEFAULT_HOLDOUT_ACCESS_LOG

    def _session_labels(self) -> pd.Series:
        return _normalized_session_labels(self.frame[self.session_column])

    def development_frame(self) -> pd.DataFrame:
        """Return a copy of development rows only, without touching the access log."""
        labels = self._session_labels()
        return self.frame.loc[labels.isin(self.development_sessions)].copy()

    def load_holdout(
        self,
        *,
        purpose: str,
        environment: Mapping[str, str] | None = None,
    ) -> pd.DataFrame:
        """Load the final holdout only after explicit owner-authorized access."""
        effective_environment = os.environ if environment is None else environment
        if effective_environment.get("ALLOW_HOLDOUT") != "1":
            raise HoldoutAccessError(
                "final holdout is locked; set ALLOW_HOLDOUT=1 for the one allowed run"
            )
        clean_purpose = purpose.strip()
        if not clean_purpose:
            raise HoldoutAccessError("holdout access requires a non-empty purpose")
        labels = self._session_labels()
        holdout = self.frame.loc[labels.isin(self.holdout_sessions)].copy()
        self._append_access_log(clean_purpose, len(holdout))
        return holdout

    def _append_access_log(self, purpose: str, row_count: int) -> None:
        self.access_log_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "accessed_at_utc": datetime.now(UTC).isoformat(),
            "purpose": purpose,
            "holdout_first_session": self.holdout_sessions[0],
            "holdout_last_session": self.holdout_sessions[-1],
            "row_count": row_count,
        }
        with self.access_log_path.open("a", encoding="utf-8") as access_log:
            access_log.write(json.dumps(event, sort_keys=True) + "\n")


def partition_final_holdout(
    frame: pd.DataFrame,
    *,
    holdout_days: int = 30,
    session_column: str = "session_date",
    session_universe: Sequence[object] | pd.Series | None = None,
    access_log_path: Path = DEFAULT_HOLDOUT_ACCESS_LOG,
) -> HoldoutPartition:
    """Reserve the most recent ``holdout_days`` trading sessions from a frame.

    ``session_universe`` lets callers preserve a calendar day even if it has no
    eligible supervised rows (for example an excluded earnings session).  This
    keeps the embargo and final holdout measured in actual trading sessions,
    rather than in whichever rows happened to survive label filtering.
    """
    if holdout_days < 1:
        raise WalkForwardError("holdout_days must be at least one")
    if session_column not in frame:
        raise WalkForwardError(f"frame has no {session_column!r} column")
    labels = _normalized_session_labels(frame[session_column])
    universe = labels if session_universe is None else _normalized_session_labels(session_universe)
    sessions = tuple(sorted(universe.unique().tolist()))
    if not labels.isin(sessions).all():
        raise WalkForwardError("frame contains session dates outside the session universe")
    if len(sessions) <= holdout_days:
        raise WalkForwardError("need more sessions than the requested holdout size")
    return HoldoutPartition(
        frame=frame.copy(),
        session_column=session_column,
        development_sessions=sessions[:-holdout_days],
        holdout_sessions=sessions[-holdout_days:],
        access_log_path=Path(access_log_path),
    )
