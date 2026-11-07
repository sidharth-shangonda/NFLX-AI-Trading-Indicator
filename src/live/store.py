"""SQLite persistence with an insert-only final-prediction ledger."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


class StoreError(RuntimeError):
    """Raised when a persistence operation violates an indicator invariant."""


def _timestamp(value: object) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise StoreError("timestamps must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat()


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PredictionStore:
    """Small local SQLite store; it intentionally contains no trading orders."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS bars_1m (
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    trade_count REAL,
                    vwap REAL,
                    source TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, timestamp)
                );
                CREATE TABLE IF NOT EXISTS candles_5m (
                    symbol TEXT NOT NULL,
                    candle_start TEXT NOT NULL,
                    candle_end TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    trade_count REAL,
                    vwap REAL,
                    n_minutes INTEGER NOT NULL,
                    is_filled INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    finalized_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, candle_start)
                );
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    candle_start TEXT NOT NULL,
                    reference_price REAL NOT NULL,
                    horizon TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('UP', 'DOWN', 'NO_CLEAR_SIGNAL')),
                    raw_output REAL,
                    calibrated_p REAL,
                    model_version TEXT NOT NULL,
                    source_ts TEXT NOT NULL,
                    generated_ts TEXT NOT NULL,
                    generated_late INTEGER NOT NULL DEFAULT 0,
                    reason TEXT,
                    UNIQUE(symbol, candle_start, model_version)
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    prediction_id INTEGER NOT NULL UNIQUE,
                    realized_return REAL,
                    realized_direction TEXT,
                    evaluated_ts TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY(prediction_id) REFERENCES predictions(id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    component TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_registry (
                    model_version TEXT PRIMARY KEY,
                    artifact_sha256 TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    registered_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS predictions_insert_only_update
                BEFORE UPDATE ON predictions
                BEGIN
                    SELECT RAISE(ABORT, 'predictions are insert-only');
                END;
                CREATE TRIGGER IF NOT EXISTS predictions_insert_only_delete
                BEFORE DELETE ON predictions
                BEGIN
                    SELECT RAISE(ABORT, 'predictions are insert-only');
                END;
                """
            )

    def log_event(
        self,
        component: str,
        severity: str,
        event: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO events(timestamp, component, severity, event, payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (_now(), component, severity, event, json.dumps(payload or {}, sort_keys=True)),
            )

    def upsert_bar(self, bar: dict[str, Any], *, source: str) -> str:
        """Insert/revise provisional bars, but never revise a finalized interval."""
        required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
        missing = required.difference(bar)
        if missing:
            raise StoreError(f"bar is missing fields: {sorted(missing)}")
        timestamp = _timestamp(bar["timestamp"])
        candle_start = _timestamp(pd.Timestamp(timestamp).floor("5min"))
        symbol = str(bar["symbol"])
        with self._connection() as connection:
            finalized = connection.execute(
                "SELECT 1 FROM candles_5m WHERE symbol = ? AND candle_start = ?",
                (symbol, candle_start),
            ).fetchone()
            if finalized:
                connection.execute(
                    "INSERT INTO events(timestamp, component, severity, event, payload_json) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        _now(),
                        "store",
                        "WARNING",
                        "late_bar_revision_ignored",
                        json.dumps({"symbol": symbol, "timestamp": timestamp}, sort_keys=True),
                    ),
                )
                return "late_ignored"
            prior = connection.execute(
                "SELECT 1 FROM bars_1m WHERE symbol = ? AND timestamp = ?",
                (symbol, timestamp),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO bars_1m(symbol, timestamp, open, high, low, close, volume,
                                    trade_count, vwap, source, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timestamp) DO UPDATE SET
                    open = excluded.open, high = excluded.high, low = excluded.low,
                    close = excluded.close, volume = excluded.volume,
                    trade_count = excluded.trade_count, vwap = excluded.vwap,
                    source = excluded.source, received_at = excluded.received_at
                """,
                (
                    symbol,
                    timestamp,
                    float(bar["open"]),
                    float(bar["high"]),
                    float(bar["low"]),
                    float(bar["close"]),
                    float(bar["volume"]),
                    None if bar.get("trade_count") is None else float(bar["trade_count"]),
                    None if bar.get("vwap") is None else float(bar["vwap"]),
                    source,
                    _now(),
                ),
            )
            return "revised" if prior else "inserted"

    def bars_between(self, symbol: str, start: object, end: object) -> pd.DataFrame:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT symbol, timestamp, open, high, low, close, volume, trade_count, vwap "
                "FROM bars_1m WHERE symbol = ? AND timestamp >= ? AND timestamp < ? "
                "ORDER BY timestamp ASC",
                (symbol, _timestamp(start), _timestamp(end)),
            ).fetchall()
        return pd.DataFrame.from_records([dict(row) for row in rows])

    def latest_bar(self, symbol: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM bars_1m WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        return dict(row) if row else None

    def latest_prediction(self, symbol: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT p.*, o.realized_return, o.realized_direction, o.status AS outcome_status "
                "FROM predictions p LEFT JOIN outcomes o ON p.id = o.prediction_id "
                "WHERE p.symbol = ? ORDER BY p.candle_start DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        return dict(row) if row else None

    def latest_event(self, component: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM events WHERE component = ? ORDER BY id DESC LIMIT 1",
                (component,),
            ).fetchone()
        if row is None:
            return None
        output = dict(row)
        output["payload"] = json.loads(output.pop("payload_json"))
        return output

    def insert_final_candle(self, candle: pd.Series | dict[str, Any]) -> bool:
        data = dict(candle)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO candles_5m(
                    symbol, candle_start, candle_end, session_date, open, high, low, close,
                    volume, trade_count, vwap, n_minutes, is_filled, status, finalized_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'final', ?)
                """,
                (
                    str(data["symbol"]),
                    _timestamp(data["candle_start"]),
                    _timestamp(data["candle_end"]),
                    str(data["session_date"]),
                    float(data["open"]),
                    float(data["high"]),
                    float(data["low"]),
                    float(data["close"]),
                    float(data["volume"]),
                    None if pd.isna(data.get("trade_count")) else float(data["trade_count"]),
                    None if pd.isna(data.get("vwap")) else float(data["vwap"]),
                    int(data["n_minutes"]),
                    int(bool(data["is_filled"])),
                    _now(),
                ),
            )
            return cursor.rowcount == 1

    def final_candles(self, symbol: str, *, limit: int = 250) -> pd.DataFrame:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT symbol, candle_start, candle_end, session_date, open, high, low, close, "
                "volume, trade_count, vwap, n_minutes, is_filled FROM candles_5m "
                "WHERE symbol = ? ORDER BY candle_start DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        frame = pd.DataFrame.from_records([dict(row) for row in rows])
        if frame.empty:
            return frame
        frame["candle_start"] = pd.to_datetime(frame["candle_start"], utc=True)
        frame["candle_end"] = pd.to_datetime(frame["candle_end"], utc=True)
        frame["is_filled"] = frame["is_filled"].astype(bool)
        return frame.sort_values("candle_start", kind="mergesort").reset_index(drop=True)

    def candle(self, symbol: str, candle_start: object) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM candles_5m WHERE symbol = ? AND candle_start = ?",
                (symbol, _timestamp(candle_start)),
            ).fetchone()
        return dict(row) if row else None

    def insert_prediction(
        self,
        *,
        symbol: str,
        candle_start: object,
        reference_price: float,
        direction: str,
        raw_output: float | None,
        calibrated_p: float | None,
        model_version: str,
        source_ts: object,
        generated_late: bool,
        reason: str | None,
    ) -> dict[str, Any]:
        if direction not in {"UP", "DOWN", "NO_CLEAR_SIGNAL"}:
            raise StoreError("prediction direction is invalid")
        start = _timestamp(candle_start)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO predictions(
                    symbol, candle_start, reference_price, horizon, direction, raw_output,
                    calibrated_p, model_version, source_ts, generated_ts, generated_late, reason
                ) VALUES (?, ?, ?, 'next_5m', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    start,
                    float(reference_price),
                    direction,
                    raw_output,
                    calibrated_p,
                    model_version,
                    _timestamp(source_ts),
                    _now(),
                    int(generated_late),
                    reason,
                ),
            )
            row = connection.execute(
                "SELECT * FROM predictions WHERE symbol = ? AND candle_start = ? "
                "AND model_version = ?",
                (symbol, start, model_version),
            ).fetchone()
        if row is None:
            raise StoreError("prediction insert did not return a row")
        output = dict(row)
        output["inserted"] = cursor.rowcount == 1
        return output

    def prediction_for_candle(
        self, symbol: str, candle_start: object, model_version: str
    ) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM predictions WHERE symbol = ? AND candle_start = ? "
                "AND model_version = ?",
                (symbol, _timestamp(candle_start), model_version),
            ).fetchone()
        return dict(row) if row else None

    def predictions(self, symbol: str, *, limit: int = 250) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT p.*, o.realized_return, o.realized_direction, o.evaluated_ts, o.status "
                "FROM predictions p LEFT JOIN outcomes o ON p.id = o.prediction_id "
                "WHERE p.symbol = ? ORDER BY p.candle_start DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_outcome(
        self,
        *,
        prediction_id: int,
        realized_return: float | None,
        realized_direction: str | None,
        status: str,
    ) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO outcomes(prediction_id, realized_return, "
                "realized_direction, "
                "evaluated_ts, status) VALUES (?, ?, ?, ?, ?)",
                (prediction_id, realized_return, realized_direction, _now(), status),
            )
            return cursor.rowcount == 1

    def register_model(
        self, model_version: str, artifact_sha256: str, metadata: dict[str, Any]
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO model_registry(model_version, artifact_sha256, "
                "metadata_json, "
                "registered_at) VALUES (?, ?, ?, ?)",
                (model_version, artifact_sha256, json.dumps(metadata, sort_keys=True), _now()),
            )

    def model(self, model_version: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM model_registry WHERE model_version = ?", (model_version,)
            ).fetchone()
        if row is None:
            return None
        output = dict(row)
        output["metadata"] = json.loads(output.pop("metadata_json"))
        return output
