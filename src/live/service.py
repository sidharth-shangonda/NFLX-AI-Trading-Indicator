"""Finalization, frozen-artifact inference, and outcome scoring for live/replay bars."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pandas as pd
import pandas_market_calendars as market_calendars

from data.candles import build_regular_session_candles
from features import FEATURE_COLUMNS, add_causal_features
from live.store import PredictionStore, StoreError
from models.artifact import ModelArtifact, load_model_artifact
from nflx_indicator.events import configured_event_session_dates

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH: Final = PROJECT_ROOT / "models" / "model-v1.joblib"
NEW_YORK: Final = "America/New_York"
UTC: Final = "UTC"


class LiveServiceError(RuntimeError):
    """Raised when a bar cannot safely become a final candle or prediction."""


@dataclass(frozen=True)
class FinalizationResult:
    """A newly finalized candle and its immutable prediction row, if inserted."""

    candle: dict[str, Any]
    prediction: dict[str, Any] | None
    inserted: bool


class LiveIndicatorService:
    """Paper-only state machine using the same candle/features code as history."""

    def __init__(
        self,
        store: PredictionStore,
        *,
        artifact: ModelArtifact | None = None,
        artifact_path: Path = DEFAULT_MODEL_PATH,
        symbol: str = "NFLX",
        min_minutes: int = 3,
        finalization_grace_seconds: int = 35,
        event_sessions: set[str] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.store = store
        self.artifact = artifact or load_model_artifact(artifact_path)
        self.symbol = symbol
        self.min_minutes = min_minutes
        self.finalization_grace = pd.Timedelta(seconds=finalization_grace_seconds)
        self.event_sessions = (
            event_sessions
            if event_sessions is not None
            else configured_event_session_dates()
        )
        self.on_event = on_event
        if self.min_minutes < 1 or self.min_minutes > 5:
            raise LiveServiceError("min_minutes must be between one and five")

    @staticmethod
    def _utc(value: object) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            raise LiveServiceError("live timestamps must be timezone-aware")
        return timestamp.tz_convert(UTC)

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        self.store.log_event("live", "INFO", event, payload)
        if self.on_event is not None:
            self.on_event(event, payload)

    def ingest_bar(self, bar: dict[str, Any], *, source: str) -> str:
        """Store a raw minute bar; finalization stays explicitly clock-gated."""
        if str(bar.get("symbol")) != self.symbol:
            raise LiveServiceError(f"expected {self.symbol} bar, received {bar.get('symbol')}")
        result = self.store.upsert_bar(bar, source=source)
        self._emit(
            "candle_update",
            {
                "symbol": self.symbol,
                "timestamp": str(bar["timestamp"]),
                "open": float(bar["open"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "volume": float(bar["volume"]),
                "result": result,
                "source": source,
            },
        )
        return result

    def _session_context(
        self, candle_start: pd.Timestamp
    ) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
        """Return prior/current NYSE session bounds; reject off-session candles."""
        calendar = market_calendars.get_calendar("NYSE")
        local_day = candle_start.tz_convert(NEW_YORK).date()
        schedule = calendar.schedule(
            start_date=(local_day - timedelta(days=10)).isoformat(),
            end_date=local_day.isoformat(),
        )
        if schedule.empty or local_day not in schedule.index.date:
            raise LiveServiceError("candle is not on an NYSE session")
        current_position = next(
            index for index, day in enumerate(schedule.index.date) if day == local_day
        )
        if current_position == 0:
            raise LiveServiceError("no prior NYSE session available for candle fill context")
        current = schedule.iloc[current_position]
        prior = schedule.iloc[current_position - 1]
        market_open = pd.Timestamp(current["market_open"]).tz_convert(UTC)
        market_close = pd.Timestamp(current["market_close"]).tz_convert(UTC)
        if not market_open <= candle_start < market_close:
            raise LiveServiceError("candle start is outside regular NYSE session")
        return (
            pd.Timestamp(prior["market_open"]).tz_convert(UTC),
            market_open,
            market_close,
        )

    def _candidate_candle(self, candle_start: pd.Timestamp) -> pd.Series | None:
        prior_open, _, current_close = self._session_context(candle_start)
        bars = self.store.bars_between(self.symbol, prior_open, current_close)
        if bars.empty:
            return None
        grid = build_regular_session_candles(
            bars,
            start=prior_open,
            end=current_close,
            min_minutes=self.min_minutes,
        )
        candidate = grid.loc[grid["candle_start"] == candle_start]
        if candidate.empty:
            return None
        return candidate.iloc[0]

    def _predict(self, candle: pd.Series, *, now: pd.Timestamp) -> dict[str, Any]:
        reason: str | None = None
        raw_output: float | None = None
        calibrated: float | None = None
        if int(candle["n_minutes"]) < self.min_minutes:
            direction = "NO_CLEAR_SIGNAL"
            reason = f"thin_data_n_minutes_{int(candle['n_minutes'])}"
        elif str(candle["session_date"]) in self.event_sessions:
            direction = "NO_CLEAR_SIGNAL"
            reason = "event_session"
        else:
            context = self.store.final_candles(self.symbol, limit=300)
            features = add_causal_features(context)
            current = features.loc[features["candle_start"] == candle["candle_start"]]
            if current.empty or not bool(current.iloc[-1]["features_ready"]):
                direction = "NO_CLEAR_SIGNAL"
                reason = "feature_warmup"
            else:
                try:
                    input_frame = current.iloc[[-1]].loc[:, FEATURE_COLUMNS]
                    raw_output = float(self.artifact.predict_raw(input_frame)[0])
                    calibrated = float(self.artifact.predict_calibrated(input_frame)[0])
                    if calibrated >= 0.5 + self.artifact.delta:
                        direction = "UP"
                    elif calibrated <= 0.5 - self.artifact.delta:
                        direction = "DOWN"
                    else:
                        direction = "NO_CLEAR_SIGNAL"
                        reason = "uncertain_model_probability"
                except Exception as exc:
                    direction = "NO_CLEAR_SIGNAL"
                    reason = f"inference_error_{type(exc).__name__}"
        late_cutoff = self._utc(candle["candle_end"]) + self.finalization_grace + pd.Timedelta(
            seconds=30
        )
        return self.store.insert_prediction(
            symbol=self.symbol,
            candle_start=candle["candle_start"],
            reference_price=float(candle["close"]),
            direction=direction,
            raw_output=raw_output,
            calibrated_p=calibrated,
            model_version=self.artifact.model_version,
            source_ts=candle["candle_end"],
            generated_late=now > late_cutoff,
            reason=reason,
        )

    def _score_prior_prediction(self, candle: pd.Series) -> None:
        current_start = self._utc(candle["candle_start"])
        prior_start = current_start - pd.Timedelta(minutes=5)
        prior_candle = self.store.candle(self.symbol, prior_start)
        if prior_candle is None or prior_candle["session_date"] != str(candle["session_date"]):
            return
        prior = self.store.prediction_for_candle(
            self.symbol, prior_start, self.artifact.model_version
        )
        if prior is None:
            return
        if int(candle["n_minutes"]) < 1:
            status = "next_candle_no_real_close"
            realized_return = None
            realized_direction = None
        else:
            realized_return = float(candle["close"]) / float(prior["reference_price"]) - 1.0
            if realized_return > 0:
                realized_direction = "UP"
            elif realized_return < 0:
                realized_direction = "DOWN"
            else:
                realized_direction = "ZERO"
            status = "scored"
        if self.store.insert_outcome(
            prediction_id=int(prior["id"]),
            realized_return=realized_return,
            realized_direction=realized_direction,
            status=status,
        ):
            self._emit("outcome", {"prediction_id": int(prior["id"]), "status": status})

    def finalize_candle(
        self,
        candle_start: object,
        *,
        now: object,
    ) -> FinalizationResult | None:
        """Freeze one 5-minute interval after grace time; never rewrite it later."""
        start = self._utc(candle_start).floor("5min")
        clock = self._utc(now)
        if clock < start + pd.Timedelta(minutes=5) + self.finalization_grace:
            return None
        if self.store.candle(self.symbol, start) is not None:
            return None
        candidate = self._candidate_candle(start)
        if candidate is None:
            self.store.log_event(
                "live",
                "WARNING",
                "candle_unavailable_no_prior_close",
                {"candle_start": start.isoformat()},
            )
            return None
        return self._finalize_candidate(candidate, clock)

    def _finalize_candidate(
        self, candidate: pd.Series, clock: pd.Timestamp
    ) -> FinalizationResult | None:
        start = self._utc(candidate["candle_start"])
        if self.store.candle(self.symbol, start) is not None:
            return None
        if not self.store.insert_final_candle(candidate):
            return None
        self._emit(
            "candle_final",
            {
                "symbol": self.symbol,
                "candle_start": self._utc(candidate["candle_start"]).isoformat(),
                "open": float(candidate["open"]),
                "high": float(candidate["high"]),
                "low": float(candidate["low"]),
                "close": float(candidate["close"]),
                "volume": float(candidate["volume"]),
                "n_minutes": int(candidate["n_minutes"]),
                "is_filled": bool(candidate["is_filled"]),
            },
        )
        prediction = self._predict(candidate, now=clock)
        self._score_prior_prediction(candidate)
        candle = self.store.candle(self.symbol, start)
        if candle is None:
            raise StoreError("inserted final candle cannot be read")
        self._emit(
            "prediction_final",
            {
                "candle_start": start.isoformat(),
                "direction": prediction["direction"],
                "calibrated_p": prediction["calibrated_p"],
                "reason": prediction["reason"],
                "generated_late": bool(prediction["generated_late"]),
                "prediction_id": prediction["id"],
            },
        )
        return FinalizationResult(candle=candle, prediction=prediction, inserted=True)

    def finalize_due(self, *, now: object) -> list[FinalizationResult]:
        """Finalize due regular-session grid intervals, including all-zero fills."""
        clock = self._utc(now)
        start = clock - pd.Timedelta(days=7)
        bars = self.store.bars_between(self.symbol, start, clock)
        if bars.empty:
            return []
        earliest = self._utc(pd.to_datetime(bars["timestamp"], utc=True).min())
        calendar = market_calendars.get_calendar("NYSE")
        schedule = calendar.schedule(
            start_date=earliest.tz_convert(NEW_YORK).date().isoformat(),
            end_date=clock.tz_convert(NEW_YORK).date().isoformat(),
        )
        starts: list[pd.Timestamp] = []
        for _, session in schedule.iterrows():
            market_open = pd.Timestamp(session["market_open"]).tz_convert(UTC)
            market_close = pd.Timestamp(session["market_close"]).tz_convert(UTC)
            candle_starts = pd.date_range(
                market_open, market_close, freq="5min", inclusive="left"
            )
            for candidate in candle_starts:
                if candidate >= earliest.floor("5min") and (
                    candidate + pd.Timedelta(minutes=5) + self.finalization_grace <= clock
                ):
                    starts.append(candidate)
        results = []
        for candle_start in starts:
            try:
                result = self.finalize_candle(candle_start, now=clock)
            except LiveServiceError as exc:
                self.store.log_event(
                    "live", "WARNING", "finalization_skipped", {"error": str(exc)}
                )
                continue
            if result is not None:
                results.append(result)
        return results

    def replay(self, bars: Iterable[dict[str, Any]]) -> list[FinalizationResult]:
        """Run recorded real bars through the identical backend, labeled REPLAY by caller."""
        ordered = sorted(bars, key=lambda bar: self._utc(bar["timestamp"]))
        if not ordered:
            return []
        timestamps = pd.to_datetime([bar["timestamp"] for bar in ordered], utc=True)
        first_day = timestamps.min().tz_convert(NEW_YORK).date().isoformat()
        last_day = timestamps.max().tz_convert(NEW_YORK).date().isoformat()
        calendar = market_calendars.get_calendar("NYSE")
        schedule = calendar.schedule(
            start_date=first_day,
            end_date=last_day,
        )
        extended_start = (
            timestamps.min().tz_convert(NEW_YORK).date() - timedelta(days=10)
        ).isoformat()
        extended_schedule = calendar.schedule(
            start_date=extended_start,
            end_date=last_day,
        )
        first_position = next(
            index
            for index, session_day in enumerate(extended_schedule.index.date)
            if session_day.isoformat() == first_day
        )
        prior_open = pd.Timestamp(
            extended_schedule.iloc[first_position - 1]["market_open"]
        ).tz_convert(UTC)
        last_close = pd.Timestamp(schedule.iloc[-1]["market_close"]).tz_convert(UTC)
        for bar in ordered:
            self.ingest_bar(bar, source="replay")
        replay_bars = self.store.bars_between(self.symbol, prior_open, last_close)
        candle_frame = build_regular_session_candles(
            replay_bars,
            start=prior_open,
            end=last_close,
            min_minutes=self.min_minutes,
        )
        grouped: dict[str, pd.Series] = {}
        for _, candle in candle_frame.iterrows():
            grouped[self._utc(candle["candle_start"]).isoformat()] = candle
        results: list[FinalizationResult] = []
        for _, session in schedule.iterrows():
            market_open = pd.Timestamp(session["market_open"]).tz_convert(UTC)
            market_close = pd.Timestamp(session["market_close"]).tz_convert(UTC)
            candle_starts = pd.date_range(
                market_open,
                market_close,
                freq="5min",
                inclusive="left",
            )
            for candle_start in candle_starts:
                candidate = grouped.get(candle_start.isoformat())
                if candidate is None:
                    continue
                result = self._finalize_candidate(
                    candidate,
                    candle_start + pd.Timedelta(minutes=5) + self.finalization_grace,
                )
                if result is not None:
                    results.append(result)
        return results
