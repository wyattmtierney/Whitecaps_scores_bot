from datetime import datetime, timedelta, timezone

from whitecaps_bot.apifootball import MatchState
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
        starts_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    assert tracker.should_create_thread(match) is False


def test_should_create_thread_allows_near_kickoff():
    tracker = MatchTracker()
    match = _make_match(
        starts_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    assert tracker.should_create_thread(match) is True


def test_should_create_thread_allows_live():
    tracker = MatchTracker()
    match = _make_match(short_status="1H", elapsed=25)
    assert tracker.should_create_thread(match) is True
