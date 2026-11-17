"""FastAPI endpoints and local lifecycle for LIVE-IEX, TEST STREAM, and REPLAY."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pandas_market_calendars as market_calendars
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from live.adapter import AlpacaIEXIngestor, fetch_clock_offset
from live.service import DEFAULT_MODEL_PATH, LiveIndicatorService
from live.store import PredictionStore
from nflx_indicator.config import ConfigurationError, load_settings
from nflx_indicator.history import fetch_bars
from nflx_indicator.json_logging import configure_json_logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_FILE = PROJECT_ROOT / "ui" / "index.html"
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "live.sqlite"
logger = logging.getLogger("nflx_api")


def _json_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _market_is_open(now: pd.Timestamp) -> bool:
    local_day = now.tz_convert("America/New_York").date().isoformat()
    calendar = market_calendars.get_calendar("NYSE")
    schedule = calendar.schedule(start_date=local_day, end_date=local_day)
    if schedule.empty:
        return False
    market_open = pd.Timestamp(schedule.iloc[0]["market_open"]).tz_convert("UTC")
    market_close = pd.Timestamp(schedule.iloc[0]["market_close"]).tz_convert("UTC")
    return market_open <= now < market_close


def _next_market_open(now: pd.Timestamp) -> pd.Timestamp | None:
    local_day = now.tz_convert("America/New_York").date()
    calendar = market_calendars.get_calendar("NYSE")
    schedule = calendar.schedule(
        start_date=local_day.isoformat(),
        end_date=(local_day + timedelta(days=14)).isoformat(),
    )
    opens = pd.to_datetime(schedule["market_open"], utc=True)
    future = opens.loc[opens > now]
    return pd.Timestamp(future.iloc[0]) if not future.empty else None


def create_app(
    *,
    database_path: Path = DEFAULT_DATABASE,
    model_path: Path = DEFAULT_MODEL_PATH,
    settings_loader=load_settings,
) -> FastAPI:
    """Build an app with injectable local paths for tests and laptop use."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_json_logging()
        settings = settings_loader()
        mode = os.environ.get("FEED_MODE", "live").strip().lower()
        if mode not in {"live", "test", "replay"}:
            mode = "auth_error"
        symbol = "FAKEPACA" if mode == "test" else settings.symbol
        db_path = database_path
        if mode == "test":
            db_path = database_path.with_name("test_stream.sqlite")
        elif mode == "replay":
            db_path = database_path.with_name("replay.sqlite")
        store = PredictionStore(db_path)
        service = LiveIndicatorService(
            store,
            artifact_path=model_path,
            symbol=symbol,
            min_minutes=settings.min_minutes,
            finalization_grace_seconds=settings.finalization_grace_seconds,
            delta=settings.prediction_delta,
        )
        app.state.store = store
        app.state.service = service
        app.state.settings = settings
        app.state.mode = mode
        app.state.feed_state = "MARKET CLOSED"
        app.state.last_bar_seen = None
        app.state.last_message = None
        app.state.clock_offset_seconds = None
        app.state.connected_clients = set()
        app.state.ingestor = None
        artifact_hash_path = PROJECT_ROOT / "models" / "model-v1.joblib.sha256"
        if artifact_hash_path.is_file():
            store.register_model(
                service.artifact.model_version,
                artifact_hash_path.read_text().strip(),
                {
                    "method": service.artifact.method,
                    "snapshot_hash": service.artifact.snapshot_hash,
                    "delta": service.artifact.delta,
                },
            )

        loop = asyncio.get_running_loop()

        def publish(event: str, payload: dict[str, Any]) -> None:
            if event == "candle_update":
                app.state.last_bar_seen = payload.get("timestamp")
            message = {"type": event, **payload}
            for client in list(app.state.connected_clients):
                asyncio.run_coroutine_threadsafe(client.send_json(message), loop)

        service.on_event = publish

        def status_callback(state: str, details: dict[str, Any]) -> None:
            previous_state = app.state.feed_state
            if state == "LIVE-IEX" and previous_state == "DISCONNECTED":
                try:
                    from alpaca.data.historical import StockHistoricalDataClient

                    key_id, secret_key = settings.require_alpaca_credentials()
                    client = StockHistoricalDataClient(key_id, secret_key)
                    latest = store.latest_bar(settings.symbol)
                    start_at = (
                        pd.Timestamp(latest["timestamp"]).to_pydatetime()
                        if latest
                        else datetime.now(UTC) - timedelta(minutes=10)
                    )
                    backfill = fetch_bars(
                        client,
                        settings.symbol,
                        start_at,
                        datetime.now(UTC),
                        settings.adjustment,
                        feed="iex",
                    )
                    for bar in backfill.to_dict(orient="records"):
                        service.ingest_bar(bar, source="rest_backfill")
                except Exception as exc:
                    store.log_event(
                        "backfill",
                        "ERROR",
                        "reconnect_backfill_failed",
                        {"error_type": type(exc).__name__},
                    )
            app.state.feed_state = state
            app.state.last_message = {"state": state, **details}
            severity = "ERROR" if state in {"DISCONNECTED", "AUTH ERROR", "RATE LIMIT"} else "INFO"
            store.log_event("stream", severity, "feed_state_changed", app.state.last_message)
            publish("health", app.state.last_message)

        if mode == "test":
            app.state.feed_state = "TEST STREAM"
            app.state.ingestor = AlpacaIEXIngestor(
                service,
                key_id=settings.alpaca_key_id or "",
                secret_key=settings.alpaca_secret_key or "",
                mode="test",
                on_status=status_callback,
            )
            if settings.alpaca_key_id and settings.alpaca_secret_key:
                app.state.ingestor.start()
            else:
                app.state.feed_state = "AUTH ERROR"
                app.state.last_message = {"error": "test stream requires local paper credentials"}
        elif mode == "replay":
            app.state.feed_state = "REPLAY"
        else:
            try:
                key_id, secret_key = settings.require_alpaca_credentials()
            except ConfigurationError:
                app.state.feed_state = "AUTH ERROR"
                app.state.last_message = {"error": "missing_local_credentials"}
            else:
                try:
                    from alpaca.data.historical import StockHistoricalDataClient

                    client = StockHistoricalDataClient(key_id, secret_key)
                    existing_candles = len(store.final_candles(settings.symbol, limit=100))
                    if existing_candles < 60:
                        backfill_start = datetime.now(UTC) - timedelta(days=5)
                    else:
                        last_bar = store.latest_bar(settings.symbol)
                        backfill_start = (
                            pd.Timestamp(last_bar["timestamp"]).to_pydatetime()
                            if last_bar
                            else datetime.now(UTC) - timedelta(days=5)
                        )
                    backfill = fetch_bars(
                        client,
                        settings.symbol,
                        backfill_start,
                        datetime.now(UTC),
                        settings.adjustment,
                        feed="iex",
                    )
                    for bar in backfill.to_dict(orient="records"):
                        service.ingest_bar(bar, source="rest_backfill")
                    service.finalize_due(now=pd.Timestamp.now(tz=UTC))
                    if not backfill.empty:
                        app.state.last_bar_seen = str(backfill["timestamp"].max())
                    offset = fetch_clock_offset(key_id=key_id, secret_key=secret_key)
                    app.state.clock_offset_seconds = offset
                    if offset is not None and abs(offset) > 2:
                        logger.warning("clock_offset_warning", extra={"component": "clock"})
                    app.state.ingestor = AlpacaIEXIngestor(
                        service,
                        key_id=key_id,
                        secret_key=secret_key,
                        mode="live",
                        on_status=status_callback,
                    )
                    app.state.feed_state = "LIVE-IEX"
                    app.state.ingestor.start()
                except Exception as exc:  # network, auth, or SDK startup errors are surfaced
                    app.state.feed_state = (
                        "AUTH ERROR" if "auth" in str(exc).lower() else "DISCONNECTED"
                    )
                    app.state.last_message = {"error_type": type(exc).__name__}
                    store.log_event("startup", "ERROR", "live_start_failed", app.state.last_message)
        yield
        if app.state.ingestor is not None:
            app.state.ingestor.stop()

    app = FastAPI(title="NFLX AI Indicator", version="1.0.0", lifespan=lifespan)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(UI_FILE)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        now = pd.Timestamp.now(tz=UTC)
        state = app.state.feed_state
        symbol = app.state.service.symbol
        latest = app.state.store.latest_bar(symbol)
        last_ts = pd.Timestamp(latest["timestamp"]) if latest else None
        if state == "LIVE-IEX" and _market_is_open(now):
            if last_ts is None or now - last_ts > pd.Timedelta(minutes=3):
                state = "STALE"
        elif state in {"LIVE-IEX", "DISCONNECTED"} and not _market_is_open(now):
            state = "MARKET CLOSED"
        next_open = _next_market_open(now) if state == "MARKET CLOSED" else None
        return {
            "state": state,
            "mode": app.state.mode.upper(),
            "symbol": symbol,
            "feed": "iex" if app.state.mode == "live" else app.state.mode,
            "last_bar_at": last_ts.isoformat() if last_ts is not None else None,
            "clock_offset_seconds": app.state.clock_offset_seconds,
            "last_message": app.state.last_message,
            "now_utc": now.isoformat(),
            "model_version": app.state.service.artifact.model_version,
            "next_open_at": next_open.isoformat() if next_open is not None else None,
        }

    @app.get("/api/candles")
    async def candles(limit: int = 250) -> dict[str, Any]:
        frame = app.state.store.final_candles(
            app.state.service.symbol,
            limit=max(1, min(limit, 2000)),
        )
        columns = [
            "candle_start",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "n_minutes",
            "is_filled",
        ]
        records = frame.loc[:, columns].to_dict(orient="records") if not frame.empty else []
        items = [{key: _json_value(value) for key, value in row.items()} for row in records]
        return {"symbol": app.state.service.symbol, "items": items}

    @app.get("/api/predictions")
    async def predictions(limit: int = 250) -> dict[str, Any]:
        rows = app.state.store.predictions(app.state.service.symbol, limit=max(1, min(limit, 2000)))
        return {"symbol": app.state.service.symbol, "items": rows}

    @app.get("/api/predictions/export.csv")
    async def predictions_csv() -> Response:
        rows = app.state.store.predictions(app.state.service.symbol, limit=10_000)
        output = io.StringIO()
        columns = [
            "symbol",
            "candle_start",
            "reference_price",
            "direction",
            "calibrated_p",
            "model_version",
            "generated_ts",
            "generated_late",
            "reason",
            "realized_return",
            "realized_direction",
            "status",
        ]
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return Response(output.getvalue(), media_type="text/csv")

    @app.get("/api/model")
    async def model() -> dict[str, Any]:
        artifact = app.state.service.artifact
        return {
            "model_version": artifact.model_version,
            "method": artifact.method,
            "snapshot_hash": artifact.snapshot_hash,
            "artifact_hash": (
                (PROJECT_ROOT / "models" / "model-v1.joblib.sha256").read_text().strip()
            ),
            "delta": app.state.service.delta,
            "artifact_delta": artifact.delta,
            "feature_columns": list(artifact.feature_columns),
            "training_window": artifact.production_window,
        }

    @app.post("/api/replay")
    async def replay() -> dict[str, Any]:
        if app.state.mode != "replay":
            return {"error": "Replay is available only when FEED_MODE=replay", "state": "LIVE-IEX"}
        files = sorted((PROJECT_ROOT / "data" / "snapshot").glob("*.parquet"))
        if not files:
            return {
                "error": "No local frozen snapshot; run make data-freeze first",
                "state": "REPLAY",
            }
        bars = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
        timestamps = pd.to_datetime(bars["timestamp"], utc=True)
        last_day = timestamps.dt.tz_convert("America/New_York").dt.date.max()
        calendar = market_calendars.get_calendar("NYSE")
        sessions = calendar.schedule(
            start_date=(last_day - timedelta(days=14)).isoformat(),
            end_date=last_day.isoformat(),
        ).index.date[-5:]
        selected = bars.loc[
            timestamps.dt.tz_convert("America/New_York").dt.date.isin(sessions)
        ].copy()
        records = selected.to_dict(orient="records")
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            results = await loop.run_in_executor(executor, app.state.service.replay, records)
        app.state.feed_state = "REPLAY"
        session_labels = {day.isoformat() for day in sessions}
        persisted_candles = app.state.store.final_candles(
            app.state.service.symbol,
            limit=10_000,
        )
        session_candles = persisted_candles.loc[
            persisted_candles["session_date"].astype(str).isin(session_labels)
        ]
        persisted_predictions = app.state.store.predictions(
            app.state.service.symbol,
            limit=10_000,
        )
        session_predictions = [
            item
            for item in persisted_predictions
            if pd.Timestamp(item["candle_start"]).tz_convert("America/New_York").date().isoformat()
            in session_labels
        ]
        return {
            "state": "REPLAY",
            "sessions": sorted(session_labels),
            "bars": len(records),
            "candles_finalized": len(session_candles),
            "newly_finalized": len(results),
            "predictions": len(session_predictions),
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        app.state.connected_clients.add(websocket)
        await websocket.send_json(
            {
                "type": "snapshot",
                "health": await health(),
                "candles": (await candles(250))["items"],
                "predictions": (await predictions(100))["items"],
            }
        )
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            app.state.connected_clients.discard(websocket)

    return app


app = create_app()
