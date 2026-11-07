from __future__ import annotations

import pandas as pd

from labels import attach_next_candle_labels


def _candle(
    start: str,
    session_date: str,
    close: float,
    n_minutes: int,
) -> dict[str, object]:
    return {
        "candle_start": pd.Timestamp(start),
        "session_date": session_date,
        "close": close,
        "n_minutes": n_minutes,
        "is_filled": n_minutes == 0,
    }


def test_next_candle_labels_accept_one_real_next_minute_and_never_cross_sessions() -> None:
    candles = pd.DataFrame(
        [
            _candle("2026-11-02T14:30:00Z", "2026-11-02", 100, 3),
            _candle("2026-11-02T14:35:00Z", "2026-11-02", 101, 1),
            _candle("2026-11-02T20:55:00Z", "2026-11-02", 102, 3),
            _candle("2026-11-03T14:30:00Z", "2026-11-03", 103, 3),
        ]
    )
    labeled = attach_next_candle_labels(candles, min_minutes=3)

    first = labeled.iloc[0]
    assert first["prediction_eligible"]
    assert first["next_n_minutes"] == 1
    assert first["label_eligible"]
    assert first["target"] == "UP"
    assert first["target_up"] == 1

    thin_current = labeled.iloc[1]
    assert not thin_current["prediction_eligible"]
    assert thin_current["label_reason"] == "thin_data_at_t"

    session_last = labeled.iloc[2]
    assert pd.isna(session_last["next_candle_start"])
    assert not session_last["label_eligible"]
    assert session_last["label_reason"] == "session_boundary"


def test_labels_drop_zero_return_and_missing_next_real_close() -> None:
    zero_return = attach_next_candle_labels(
        pd.DataFrame(
            [
                _candle("2026-11-02T14:30:00Z", "2026-11-02", 100, 3),
                _candle("2026-11-02T14:35:00Z", "2026-11-02", 100, 1),
            ]
        )
    )
    assert not zero_return.iloc[0]["label_eligible"]
    assert zero_return.iloc[0]["label_reason"] == "zero_return"

    missing_outcome = attach_next_candle_labels(
        pd.DataFrame(
            [
                _candle("2026-11-02T14:30:00Z", "2026-11-02", 100, 3),
                _candle("2026-11-02T14:35:00Z", "2026-11-02", 100, 0),
            ]
        )
    )
    assert not missing_outcome.iloc[0]["label_eligible"]
    assert missing_outcome.iloc[0]["label_reason"] == "next_candle_no_real_close"


def test_event_session_blocks_prediction_and_training_but_retains_label_fact() -> None:
    candles = pd.DataFrame(
        [
            _candle("2025-04-21T13:30:00Z", "2025-04-21", 100, 3),
            _candle("2025-04-21T13:35:00Z", "2025-04-21", 101, 1),
        ]
    )
    labeled = attach_next_candle_labels(candles, event_session_dates={"2025-04-21"})

    assert labeled.iloc[0]["is_event_session"]
    assert not labeled.iloc[0]["prediction_eligible"]
    assert labeled.iloc[0]["prediction_gate_reason"] == "event_session"
    assert labeled.iloc[0]["label_eligible"]
    assert not labeled.iloc[0]["training_eligible"]
