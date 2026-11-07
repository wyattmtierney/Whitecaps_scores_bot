from datetime import datetime, timedelta, timezone

from whitecaps_bot.apifootball import MatchState
from whitecaps_bot.tracker import compute_poll_delay

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
BASE = 30


def _match(starts_in: timedelta | None, short_status: str = "NS") -> MatchState:
    return MatchState(
        fixture_id=1,
        home_name="CF Montréal",
        away_name="Vancouver Whitecaps",
        home_goals=0,
        away_goals=0,
        elapsed=None,
        short_status=short_status,
        long_status="",
        starts_at=None if starts_in is None else NOW + starts_in,
    )


def _delay(match, fulltime_posted=False):
    return compute_poll_delay(match, base_seconds=BASE, fulltime_posted=fulltime_posted, now=NOW)


def test_no_match_polls_slowly():
    assert _delay(None) == 30 * 60


def test_live_and_halftime_poll_fast():
    assert _delay(_match(timedelta(minutes=-40), "1H")) == BASE
    assert _delay(_match(timedelta(minutes=-50), "HT")) == BASE
    assert _delay(_match(timedelta(minutes=-50), "IN")) == BASE


def test_finished_polls_fast_until_full_time_posted():
    finished = _match(timedelta(hours=-2), "FT")
    assert _delay(finished, fulltime_posted=False) == BASE
    assert _delay(finished, fulltime_posted=True) == 30 * 60


def test_fast_polling_starts_30_min_before_kickoff():
    assert _delay(_match(timedelta(minutes=30))) == BASE
    assert _delay(_match(timedelta(minutes=5))) == BASE


def test_overdue_kickoff_still_polls_fast():
    # Kickoff time passed but the feed still says pre-match (delayed start).
    assert _delay(_match(timedelta(minutes=-10), "PRE")) == BASE


def test_inside_thread_window_polls_every_10_min():
    assert _delay(_match(timedelta(hours=5))) == 10 * 60


def test_inside_window_wakes_in_time_for_fast_polling():
    # 35 min to kickoff: next poll in 5 min (at the 30-min mark), not 10.
    assert _delay(_match(timedelta(minutes=35))) == 5 * 60


def test_far_out_polls_every_30_min():
    assert _delay(_match(timedelta(days=4))) == 30 * 60


def test_wakes_exactly_when_thread_window_opens():
    # 12h10m out: the window opens in 10 min, so poll then, not in 30.
    assert _delay(_match(timedelta(hours=12, minutes=10))) == 10 * 60
    # 12h0m20s out: never below the base interval.
    assert _delay(_match(timedelta(hours=12, seconds=20))) == BASE


def test_unknown_kickoff_time_polls_every_10_min():
    assert _delay(_match(None)) == 10 * 60
