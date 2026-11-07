from __future__ import annotations

from pathlib import Path

import pandas as pd

from live.service import LiveIndicatorService
from live.store import PredictionStore

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "model-v1.joblib"


def _bar(timestamp: str, price: float) -> dict[str, object]:
    return {
        "symbol": "NFLX",
        "timestamp": timestamp,
        "open": price,
        "high": price + 0.1,
        "low": price - 0.1,
        "close": price,
        "volume": 100.0,
        "trade_count": 5,
        "vwap": price,
    }


def _service(tmp_path: Path) -> tuple[PredictionStore, LiveIndicatorService]:
    store = PredictionStore(tmp_path / "live.sqlite")
    service = LiveIndicatorService(
        store,
        artifact_path=MODEL_PATH,
        event_sessions=set(),
        finalization_grace_seconds=35,
    )
    # Previous NYSE close: establishes the fill value for a missing current candle.
    service.ingest_bar(_bar("2026-10-30T13:30:00Z", 100.0), source="unit")
    return store, service


def test_finalization_gates_thin_data_and_never_repaints(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    start = pd.Timestamp("2026-11-02T14:30:00Z")
    service.ingest_bar(_bar(start.isoformat(), 101.0), source="unit")

    result = service.finalize_candle(start, now="2026-11-02T14:35:35Z")

    assert result is not None
    assert result.candle["n_minutes"] == 1
    assert result.prediction["direction"] == "NO_CLEAR_SIGNAL"
    assert result.prediction["reason"] == "thin_data_n_minutes_1"
    assert service.finalize_candle(start, now="2026-11-02T14:40:35Z") is None
    assert service.ingest_bar(_bar(start.isoformat(), 105.0), source="late") == "late_ignored"
    saved = store.prediction_for_candle("NFLX", start, "model-v1")
    assert saved["reference_price"] == 101.0


def test_outcome_is_scored_once_on_next_real_close_and_not_overnight(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    first = pd.Timestamp("2026-11-02T14:30:00Z")
    for minute, price in enumerate((101.0, 101.1, 101.2)):
        timestamp = (first + pd.Timedelta(minutes=minute)).isoformat()
        service.ingest_bar(_bar(timestamp, price), source="unit")
    second = first + pd.Timedelta(minutes=5)
    service.ingest_bar(_bar(second.isoformat(), 101.5), source="unit")
    service.finalize_candle(first, now="2026-11-02T14:40:35Z")
    service.finalize_candle(second, now="2026-11-02T14:40:35Z")

    predictions = store.predictions("NFLX")
    first_prediction = next(row for row in predictions if row["candle_start"] == first.isoformat())
    assert first_prediction["status"] == "scored"
    assert first_prediction["realized_direction"] == "UP"
    assert abs(first_prediction["realized_return"] - (101.5 / 101.2 - 1.0)) < 1e-12
    assert len(predictions) == 2


def test_replay_uses_the_same_finalizer_and_records_replay_source(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    bars = [
        _bar("2026-11-02T14:30:00Z", 101.0),
        _bar("2026-11-02T14:31:00Z", 101.1),
    ]

    results = service.replay(bars)

    assert len(results) == 78
    assert results[0].candle["n_minutes"] == 2
    assert results[0].prediction["reason"] == "thin_data_n_minutes_2"
    assert sum(result.candle["n_minutes"] == 0 for result in results) == 77
    latest = store.latest_bar("NFLX")
    assert latest["source"] == "replay"
