from datetime import datetime, timezone

from whitecaps_bot.apifootball import MatchState


def test_match_state_supports_espn_state_in():
    match = MatchState(
        fixture_id=1,
        home_name="A",
        away_name="B",
        home_goals=1,
        away_goals=0,
        elapsed=10,
        short_status="IN",
        long_status="In Progress",
        starts_at=datetime.now(timezone.utc),
    )
    assert match.state == "in"


def test_match_state_supports_espn_state_post():
    match = MatchState(
        fixture_id=1,
        home_name="A",
        away_name="B",
        home_goals=1,
        away_goals=0,
        elapsed=90,
        short_status="POST",
        long_status="Final",
        starts_at=datetime.now(timezone.utc),
    )
    assert match.state == "post"
