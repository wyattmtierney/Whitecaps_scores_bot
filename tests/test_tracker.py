from datetime import datetime, timedelta, timezone

from whitecaps_bot.apifootball import CardEvent, MatchState, StandingsEntry
from whitecaps_bot.tracker import MatchTracker


def _make_match(**overrides) -> MatchState:
    defaults = dict(
        fixture_id=1,
        home_name="Vancouver Whitecaps",
        away_name="Seattle Sounders",
        home_goals=None,
        away_goals=None,
        elapsed=None,
        short_status="NS",
        long_status="Not Started",
        # 20:00 UTC = 12:00 PST, keeps the date as Feb 18 in PST
        starts_at=datetime(2026, 2, 18, 20, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return MatchState(**defaults)


def test_build_thread_title_when_whitecaps_home():
    match = _make_match()
    title = MatchTracker.build_thread_title(match)
    assert title == "Seattle Sounders @ Vancouver Whitecaps - February 18, 2026"


def test_build_thread_title_when_whitecaps_away():
    match = _make_match(
        home_name="CS Cartagines",
        away_name="Vancouver Whitecaps",
    )
    title = MatchTracker.build_thread_title(match)
    assert title == "Vancouver Whitecaps @ CS Cartagines - February 18, 2026"


def test_should_create_thread_blocks_duplicate():
    tracker = MatchTracker()
    match = _make_match(
        starts_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    # First time: should be allowed
    assert tracker.should_create_thread(match) is True
    # Mark as created
    tracker._threads_created_for.add(match.fixture_id)
    # Second time: should be blocked
    assert tracker.should_create_thread(match) is False


def test_should_create_thread_blocks_far_future():
    tracker = MatchTracker()
    match = _make_match(
        starts_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    assert tracker.should_create_thread(match) is False


def test_should_create_thread_allows_near_kickoff():
    tracker = MatchTracker()
    match = _make_match(
        starts_at=datetime.now(timezone.utc) + timedelta(hours=20),
    )
    assert tracker.should_create_thread(match) is True


def test_should_create_thread_allows_live():
    tracker = MatchTracker()
    match = _make_match(short_status="1H", elapsed=25)
    assert tracker.should_create_thread(match) is True


def test_build_card_embed_yellow():
    card = CardEvent(
        fixture_id=1, elapsed=34, team_name="Vancouver Whitecaps",
        player_name="Ranko Veselinovic", card_type="Yellow Card",
    )
    embed = MatchTracker.build_card_embed(card)
    assert "Yellow Card" in embed.title
    assert "Ranko Veselinovic" in embed.description
    assert embed.color.value == 0xFFCC00


def test_build_card_embed_red():
    card = CardEvent(
        fixture_id=1, elapsed=67, team_name="Seattle Sounders",
        player_name="Jordan Morris", card_type="Red Card",
    )
    embed = MatchTracker.build_card_embed(card)
    assert "Red Card" in embed.title
    assert embed.color.value == 0xFF0000


def test_build_halftime_embed():
    match = _make_match(
        home_goals=1, away_goals=0, elapsed=45,
        short_status="HT", long_status="Half Time",
    )
    embed = MatchTracker.build_halftime_embed(match)
    assert "Half Time" in embed.title
    assert "Vancouver Whitecaps" in embed.description
    assert "`1`" in embed.description
    assert "`0`" in embed.description


def test_build_upcoming_embed():
    matches = [
        _make_match(
            away_name="Toronto FC",
            starts_at=datetime(2026, 3, 1, 2, 30, tzinfo=timezone.utc),
            venue="BC Place",
            broadcasts=("TSN", "Apple TV"),
        ),
        _make_match(
            home_name="Portland Timbers",
            away_name="Vancouver Whitecaps",
            starts_at=datetime(2026, 3, 8, 2, 0, tzinfo=timezone.utc),
            venue="Providence Park",
        ),
    ]
    embed = MatchTracker.build_upcoming_embed(matches)
    assert "Upcoming" in embed.title
    assert "Toronto FC" in embed.description
    assert "Portland Timbers" in embed.description
    assert "HOME" in embed.description
    assert "AWAY" in embed.description


def test_build_standings_embed():
    entries = [
        StandingsEntry(rank=1, team_name="LA Galaxy", played=10, wins=7, draws=2, losses=1, goals_for=20, goals_against=8, goal_difference=12, points=23),
        StandingsEntry(rank=2, team_name="Vancouver Whitecaps", played=10, wins=6, draws=2, losses=2, goals_for=18, goals_against=10, goal_difference=8, points=20),
    ]
    embed = MatchTracker.build_standings_embed(entries)
    assert "MLS Standings" in embed.title
    assert "LA Galaxy" in embed.description
    assert "Vancouver Whitecaps" in embed.description


def test_tracker_card_keys_tracking():
    tracker = MatchTracker()
    assert len(tracker.posted_card_keys) == 0
    tracker.posted_card_keys.add("test_key")
    assert "test_key" in tracker.posted_card_keys


def test_tracker_halftime_fulltime_flags():
    tracker = MatchTracker()
    assert tracker.halftime_posted is False
    assert tracker.fulltime_posted is False
    tracker.halftime_posted = True
    tracker.fulltime_posted = True
    assert tracker.halftime_posted is True
    assert tracker.fulltime_posted is True
