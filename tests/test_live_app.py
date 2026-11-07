from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
from fastapi import WebSocketDisconnect

from live.app import _next_market_open, create_app
from nflx_indicator.config import Settings


def test_next_market_open_uses_current_nyse_schedule() -> None:
    next_open = _next_market_open(pd.Timestamp("2026-11-07T16:00:00Z"))
    assert next_open == pd.Timestamp("2026-11-09T14:30:00Z")


def test_local_api_snapshot_model_csv_and_websocket(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FEED_MODE", "replay")
    app = create_app(
        database_path=tmp_path / "live.sqlite",
        settings_loader=lambda: Settings(),
    )

    routes = {route.path: route.endpoint for route in app.routes if hasattr(route, "endpoint")}

    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages = []

        async def accept(self) -> None:
            return None

        async def send_json(self, payload) -> None:
            self.messages.append(payload)

        async def receive_text(self) -> str:
            raise WebSocketDisconnect()

    async def exercise() -> None:
        async with app.router.lifespan_context(app):
            health = await routes["/api/health"]()
            model = await routes["/api/model"]()
            assert health["state"] == "REPLAY"
            assert health["mode"] == "REPLAY"
            assert model["model_version"] == "model-v1"
            assert (await routes["/api/candles"]())["items"] == []
            assert (await routes["/api/predictions"]())["items"] == []
            csv_response = await routes["/api/predictions/export.csv"]()
            assert "candle_start" in csv_response.body.decode()
            file_response = await routes["/"]()
            assert Path(file_response.path).is_file()
            websocket = FakeWebSocket()
            await routes["/ws"](websocket)
            assert websocket.messages[0]["type"] == "snapshot"
            assert websocket.messages[0]["health"]["mode"] == "REPLAY"

    asyncio.run(exercise())
