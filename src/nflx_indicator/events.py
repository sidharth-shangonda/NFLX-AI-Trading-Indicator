"""Load verified earnings releases and derive their first post-release session."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandas_market_calendars as market_calendars

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVENTS_FILE = PROJECT_ROOT / "config" / "events.yaml"
NEW_YORK = "America/New_York"


class EventConfigError(ValueError):
    """Raised when the JSON-compatible YAML events configuration is invalid."""


def load_event_releases(path: Path = DEFAULT_EVENTS_FILE) -> pd.DataFrame:
    """Read release facts from JSON-compatible YAML without a parser dependency."""
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EventConfigError(f"cannot read event configuration: {path}") from exc
    events = document.get("events") if isinstance(document, dict) else None
    if not isinstance(events, list):
        raise EventConfigError("event configuration needs an events list")
    rows = []
    for event in events:
        if not isinstance(event, dict):
            raise EventConfigError("each event must be an object")
        required = {"kind", "label", "released_at", "source_url"}
        missing = required.difference(event)
        if missing:
            raise EventConfigError(f"event is missing fields: {sorted(missing)}")
        released_at = pd.Timestamp(event["released_at"])
        if released_at.tzinfo is None:
            raise EventConfigError("released_at must include a UTC offset")
        rows.append({**event, "released_at": released_at.tz_convert("UTC")})
    return pd.DataFrame.from_records(rows).sort_values("released_at", kind="mergesort")


def first_sessions_after_releases(
    releases: pd.DataFrame,
    *,
    calendar_name: str = "NYSE",
) -> pd.DataFrame:
    """Return first NYSE session strictly after each release's New York date."""
    if releases.empty:
        return releases.assign(event_session_date=pd.Series(dtype=str))
    if "released_at" not in releases:
        raise EventConfigError("releases need a released_at column")
    calendar = market_calendars.get_calendar(calendar_name)
    output = releases.copy()
    event_sessions: list[str] = []
    for released_at in pd.to_datetime(output["released_at"], utc=True):
        release_day = released_at.tz_convert(NEW_YORK).date()
        schedule = calendar.schedule(
            start_date=(release_day + pd.Timedelta(days=1)).isoformat(),
            end_date=(release_day + pd.Timedelta(days=10)).isoformat(),
        )
        if schedule.empty:
            raise EventConfigError(f"no NYSE session found after {release_day.isoformat()}")
        event_sessions.append(schedule.index[0].date().isoformat())
    output["event_session_date"] = event_sessions
    return output


def configured_event_session_dates(path: Path = DEFAULT_EVENTS_FILE) -> set[str]:
    """Return all first-post-release event-session dates from the verified config."""
    releases = load_event_releases(path)
    return set(first_sessions_after_releases(releases)["event_session_date"])
