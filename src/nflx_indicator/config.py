"""Project settings loaded from TOML defaults and the ignored local .env file."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = PROJECT_ROOT / "config" / "settings.toml"
DOTENV_FILE = PROJECT_ROOT / ".env"


class ConfigurationError(ValueError):
    """Raised when a project setting is invalid or required credentials are absent."""


@dataclass(frozen=True)
class Settings:
    symbol: str = "NFLX"
    feed: str = "iex"
    adjustment: str = "split"
    min_minutes: int = 3
    finalization_grace_seconds: int = 35
    log_level: str = "INFO"
    alpaca_key_id: str | None = field(default=None, repr=False)
    alpaca_secret_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(
        cls,
        environment: Mapping[str, str],
        project_config: Mapping[str, object] | None = None,
    ) -> Settings:
        config = project_config or {}
        market_data = config.get("market_data", {})
        data = config.get("data", {})
        live = config.get("live", {})
        if not isinstance(market_data, Mapping):
            market_data = {}
        if not isinstance(data, Mapping):
            data = {}
        if not isinstance(live, Mapping):
            live = {}

        try:
            min_minutes = int(environment.get("MIN_MINUTES", data.get("min_minutes", 3)))
            finalization_grace_seconds = int(
                live.get("finalization_grace_seconds", 35)
            )
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("numeric configuration value is invalid") from exc

        if not 1 <= min_minutes <= 5:
            raise ConfigurationError("MIN_MINUTES must be between 1 and 5")
        if finalization_grace_seconds < 0:
            raise ConfigurationError("finalization grace must not be negative")

        return cls(
            symbol=str(market_data.get("symbol", "NFLX")),
            feed=str(market_data.get("feed", "iex")),
            adjustment=str(market_data.get("adjustment", "split")),
            min_minutes=min_minutes,
            finalization_grace_seconds=finalization_grace_seconds,
            log_level=environment.get("LOG_LEVEL", "INFO").upper(),
            alpaca_key_id=environment.get("APCA_API_KEY_ID"),
            alpaca_secret_key=environment.get("APCA_API_SECRET_KEY"),
        )

    def require_alpaca_credentials(self) -> tuple[str, str]:
        if not self.alpaca_key_id or not self.alpaca_secret_key:
            raise ConfigurationError(
                "Alpaca credentials are missing; add paper keys to the local .env file"
            )
        return self.alpaca_key_id, self.alpaca_secret_key


def load_settings() -> Settings:
    """Read local settings without printing or logging credential values."""
    load_dotenv(DOTENV_FILE, override=False)
    with SETTINGS_FILE.open("rb") as settings_file:
        project_config = tomllib.load(settings_file)
    return Settings.from_env(os.environ, project_config)
