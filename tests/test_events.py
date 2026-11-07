from __future__ import annotations

from nflx_indicator.events import (
    configured_event_session_dates,
    first_sessions_after_releases,
    load_event_releases,
)


def test_configured_earnings_events_use_next_nyse_session() -> None:
    releases = load_event_releases()
    sessions = first_sessions_after_releases(releases)

    assert len(releases) == 9
    q1_2025_session = sessions.loc[
        sessions["label"].eq("Q1 2025"), "event_session_date"
    ].item()
    assert q1_2025_session == "2025-04-21"
    assert configured_event_session_dates() == set(sessions["event_session_date"])
    assert "2026-10-21" in configured_event_session_dates()
