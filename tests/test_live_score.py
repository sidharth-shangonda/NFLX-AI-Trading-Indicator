from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from eval.live_score import score_database
from live.store import PredictionStore


def test_score_uses_on_time_predictions_and_emits_same_candle_baselines(tmp_path: Path) -> None:
    database = tmp_path / "replay.sqlite"
    store = PredictionStore(database)
    store.register_model("model-v1", "a" * 64, {"delta": 0.05})
    first = date(2026, 1, 5)
    candle_count = 35
    for index in range(candle_count):
        day_offset, slot = divmod(index, 13)
        timestamp = pd.Timestamp(first + timedelta(days=day_offset), tz="UTC")
        start = timestamp + pd.Timedelta(hours=14, minutes=30 + (slot * 5))
        price = 100.0 + index * 0.1
        store.insert_final_candle(
            {
                "symbol": "NFLX",
                "candle_start": start,
                "candle_end": start + pd.Timedelta(minutes=5),
                "session_date": (first + timedelta(days=day_offset)).isoformat(),
                "open": price,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price,
                "volume": 100 + index,
                "trade_count": None,
                "vwap": None,
                "n_minutes": 5,
                "is_filled": False,
            }
        )
    candles = store.final_candles("NFLX", limit=100)
    for index in range(candle_count - 1):
        current = candles.iloc[index]
        following = candles.iloc[index + 1]
        prediction = store.insert_prediction(
            symbol="NFLX",
            candle_start=current["candle_start"],
            reference_price=float(current["close"]),
            direction="NO_CLEAR_SIGNAL",
            raw_output=0.5,
            calibrated_p=0.5,
            model_version="model-v1",
            source_ts=current["candle_end"],
            generated_late=False,
            reason="uncertain_model_probability",
        )
        realized_return = float(following["close"]) / float(current["close"]) - 1.0
        store.insert_outcome(
            prediction_id=int(prediction["id"]),
            realized_return=realized_return,
            realized_direction="UP",
            status="scored",
        )

    report = score_database(database)

    assert report["prediction_outcomes"] == candle_count - 1
    assert report["metrics"]["all"]["model-v1"]["observations"] == candle_count - 1
    assert report["metrics"]["all"]["always_up"]["signals"] == candle_count - 1
    assert report["metrics"]["all"]["model-v1"]["brier"] == 0.25
    assert report["feed_label"].startswith("REPLAY")
