from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from live.store import PredictionStore


def test_prediction_is_insert_only_and_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "live.sqlite"
    store = PredictionStore(path)
    prediction = store.insert_prediction(
        symbol="NFLX",
        candle_start="2026-11-02T14:30:00Z",
        reference_price=100.0,
        direction="NO_CLEAR_SIGNAL",
        raw_output=0.52,
        calibrated_p=0.51,
        model_version="model-v1",
        source_ts="2026-11-02T14:35:00Z",
        generated_late=False,
        reason="thin_data_n_minutes_1",
    )
    duplicate = store.insert_prediction(
        symbol="NFLX",
        candle_start="2026-11-02T14:30:00Z",
        reference_price=999.0,
        direction="UP",
        raw_output=0.99,
        calibrated_p=0.99,
        model_version="model-v1",
        source_ts="2026-11-02T14:35:00Z",
        generated_late=False,
        reason=None,
    )

    assert prediction["inserted"] is True
    assert duplicate["inserted"] is False
    assert duplicate["reference_price"] == 100.0

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="insert-only"):
            connection.execute(
                "UPDATE predictions SET direction='UP' WHERE id=?", (prediction["id"],)
            )
        with pytest.raises(sqlite3.IntegrityError, match="insert-only"):
            connection.execute("DELETE FROM predictions WHERE id=?", (prediction["id"],))

    restarted = PredictionStore(path)
    restored = restarted.predictions("NFLX")
    assert len(restored) == 1
    assert restored[0]["direction"] == "NO_CLEAR_SIGNAL"


def test_bar_revisions_are_idempotent_until_the_interval_is_final(tmp_path: Path) -> None:
    store = PredictionStore(tmp_path / "live.sqlite")
    bar = {
        "symbol": "NFLX",
        "timestamp": "2026-11-02T14:30:00Z",
        "open": 100.0,
        "high": 100.0,
        "low": 100.0,
        "close": 100.0,
        "volume": 1.0,
    }
    assert store.upsert_bar(bar, source="test") == "inserted"
    revised = {**bar, "close": 100.2}
    assert store.upsert_bar(revised, source="test") == "revised"
    revised_rows = store.bars_between("NFLX", bar["timestamp"], "2026-11-02T14:31:00Z")
    assert float(revised_rows.iloc[0]["close"]) == 100.2

    candle = {
        "symbol": "NFLX",
        "candle_start": "2026-11-02T14:30:00Z",
        "candle_end": "2026-11-02T14:35:00Z",
        "session_date": "2026-11-02",
        "open": 100.0,
        "high": 100.2,
        "low": 100.0,
        "close": 100.2,
        "volume": 2,
        "n_minutes": 1,
        "is_filled": False,
    }
    assert store.insert_final_candle(candle)
    assert store.upsert_bar({**bar, "close": 101.0}, source="late") == "late_ignored"
