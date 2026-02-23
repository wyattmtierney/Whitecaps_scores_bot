from datetime import datetime, timezone

from whitecaps_bot.apifootball import MatchState
from whitecaps_bot.tracker import MatchTracker


def test_build_thread_title_when_whitecaps_home():
    match = MatchState(
        fixture_id=1,
        home_name="Vancouver Whitecaps",
        away_name="Seattle Sounders",
        home_goals=None,
        away_goals=None,
        elapsed=None,
        short_status="NS",
        long_status="Not Started",
        starts_at=datetime(2026, 2, 18, 3, 0, tzinfo=timezone.utc),
    )

    title = MatchTracker.build_thread_title(match)
    assert title == "Seattle Sounders @ Vancouver Whitecaps - February 18, 2026"


def test_build_thread_title_when_whitecaps_away():
    match = MatchState(
        fixture_id=1,
        home_name="CS Cartagines",
        away_name="Vancouver Whitecaps",
        home_goals=None,
        away_goals=None,
        elapsed=None,
        short_status="NS",
        long_status="Not Started",
        starts_at=datetime(2026, 2, 18, 3, 0, tzinfo=timezone.utc),
    )

    title = MatchTracker.build_thread_title(match)
    assert title == "Vancouver Whitecaps @ CS Cartagines - February 18, 2026"
