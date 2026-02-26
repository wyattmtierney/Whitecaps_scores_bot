from datetime import datetime, timezone

from whitecaps_bot.apifootball import CardEvent, MatchState, StandingsEntry, SubstitutionEvent


def test_substitution_dedupe_key_is_stable():
    event = SubstitutionEvent(
        fixture_id=123,
        elapsed=54,
        team_name="Vancouver Whitecaps",
        player_in="Ali Ahmed",
        player_out="Ryan Gauld",
    )

    assert event.dedupe_key == "123:54:Vancouver Whitecaps:Ali Ahmed:Ryan Gauld"


def test_card_event_dedupe_key_is_stable():
    card = CardEvent(
        fixture_id=456,
        elapsed=30,
        team_name="Seattle Sounders",
        player_name="Jordan Morris",
        card_type="Yellow Card",
    )
    assert card.dedupe_key == "456:30:Seattle Sounders:Jordan Morris:Yellow Card"


def test_standings_entry_fields():
    entry = StandingsEntry(
        rank=1,
        team_name="Vancouver Whitecaps",
        played=10,
        wins=6,
        draws=2,
        losses=2,
        goals_for=18,
        goals_against=10,
        goal_difference=8,
        points=20,
    )
    assert entry.rank == 1
    assert entry.points == 20
    assert entry.goal_difference == 8


def test_is_halftime_with_ht_status():
    match = MatchState(
        fixture_id=1, home_name="A", away_name="B",
        home_goals=1, away_goals=0, elapsed=45,
        short_status="HT", long_status="Half Time",
        starts_at=datetime.now(timezone.utc),
    )
    assert match.is_halftime is True


def test_is_halftime_with_espn_long_status():
    match = MatchState(
        fixture_id=1, home_name="A", away_name="B",
        home_goals=0, away_goals=0, elapsed=45,
        short_status="IN", long_status="Halftime",
        starts_at=datetime.now(timezone.utc),
    )
    assert match.is_halftime is True


def test_is_halftime_false_during_play():
    match = MatchState(
        fixture_id=1, home_name="A", away_name="B",
        home_goals=0, away_goals=0, elapsed=30,
        short_status="1H", long_status="First Half",
        starts_at=datetime.now(timezone.utc),
    )
    assert match.is_halftime is False
