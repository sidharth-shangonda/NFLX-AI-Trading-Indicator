from __future__ import annotations

import pytest

from nflx_indicator.config import ConfigurationError, Settings


def test_min_minutes_comes_from_project_config() -> None:
    settings = Settings.from_env({}, {"data": {"min_minutes": 3}})

    assert settings.min_minutes == 3
    assert settings.symbol == "NFLX"
    assert settings.feed == "iex"


def test_min_minutes_can_be_overridden_with_valid_value() -> None:
    settings = Settings.from_env({"MIN_MINUTES": "4"}, {"data": {"min_minutes": 3}})

    assert settings.min_minutes == 4


@pytest.mark.parametrize("value", ["0", "6", "not-a-number"])
def test_invalid_min_minutes_is_rejected(value: str) -> None:
    with pytest.raises(ConfigurationError):
        Settings.from_env({"MIN_MINUTES": value})


def test_credentials_are_not_in_settings_repr() -> None:
    settings = Settings.from_env(
        {"APCA_API_KEY_ID": "paper-id", "APCA_API_SECRET_KEY": "secret-value"}
    )

    assert "paper-id" not in repr(settings)
    assert "secret-value" not in repr(settings)


def test_missing_credentials_has_safe_error() -> None:
    settings = Settings.from_env({})

    with pytest.raises(ConfigurationError, match="credentials are missing"):
        settings.require_alpaca_credentials()
