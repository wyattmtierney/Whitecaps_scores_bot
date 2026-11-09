"""Live mode: one ESPN summary request per poll during a match, fast fallback."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from whitecaps_bot.apifootball import MatchState
from whitecaps_bot.espn import ESPN_SCOREBOARD_URL, ESPN_SUMMARY_URL, EspnClient
from whitecaps_bot.provider import LIVE_REQUEST_TIMEOUT, ScoreProvider
from whitecaps_bot.tracker import compute_poll_delay

EVENT_ID = "761934"
NOW = datetime.now(timezone.utc)
KICKOFF = NOW - timedelta(minutes=70)


def _summary(state="in", home="1", away="2", detail="73'", event_id=EVENT_ID, key_events=None):
    return {
        "header": {
            "id": event_id,
            "competitions": [{
                "date": KICKOFF.strftime("%Y-%m-%dT%H:%MZ"),
                "status": {"type": {"state": state, "detail": detail, "shortDetail": detail}},
                "competitors": [
                    {"homeAway": "home", "score": home, "team": {"id": "9720", "displayName": "CF Montréal"}},
                    {"homeAway": "away", "score": away, "team": {"id": "9727", "displayName": "Vancouver Whitecaps"}},
                ],
            }],
        },
        "keyEvents": key_events if key_events is not None else [{
            "type": {"text": "Goal"},
            "text": "Goal! CF Montréal 1, Vancouver Whitecaps 2. Brian White (Vancouver Whitecaps) right footed shot.",
            "team": {"displayName": "Vancouver Whitecaps"},
            "clock": {"displayValue": "72:10"},
            "participants": [{"athlete": {"displayName": "Brian White"}}],
            "wallclock": (NOW - timedelta(seconds=40)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }],
    }


def _scoreboard_match(state="IN", starts_at=KICKOFF, goals=(1, 1)):
    return MatchState(
        fixture_id=int(EVENT_ID), home_name="CF Montréal", away_name="Vancouver Whitecaps",
        home_goals=goals[0], away_goals=goals[1], elapsed=60, short_status=state,
        long_status="", starts_at=starts_at, venue="Stade Saputo", broadcasts=("TSN",),
        home_logo="home.png", away_logo="away.png",
    )


class RecordingEspn(EspnClient):
    """EspnClient with the network replaced by canned responses."""

    def __init__(self, summary=None, scoreboard_match=None, summary_error=None):
        super().__init__()
        self.calls = []
        self.summary = summary
        self.summary_error = summary_error
        self.scoreboard_match = scoreboard_match

    async def _get(self, url, params, timeout=None):
        self.calls.append((url, timeout))
        if url == ESPN_SUMMARY_URL:
            if self.summary_error:
                raise self.summary_error
            return self.summary
        raise AssertionError("scoreboard is fetched via get_current_or_next_whitecaps_fixture in these tests")

    async def get_current_or_next_whitecaps_fixture(self, timeout=None):
        self.calls.append((ESPN_SCOREBOARD_URL, timeout))
        return self.scoreboard_match, EVENT_ID


def _provider(espn):
    provider = ScoreProvider(api_football_key=None, espn_team_id="9727", espn_team_name="Vancouver Whitecaps")
    provider.espn = espn
    return provider


def test_header_parse_reads_live_score_and_status():
    update = EspnClient.live_update_from_summary(_summary(), EVENT_ID)
    assert update == {
        "home_goals": 1, "away_goals": 2, "elapsed": 73,
        "short_status": "IN", "long_status": "73'",
    }


def test_header_parse_rejects_wrong_or_incomplete_payloads():
    assert EspnClient.live_update_from_summary(_summary(event_id="999"), EVENT_ID) is None
    assert EspnClient.live_update_from_summary({}, EVENT_ID) is None
    broken = _summary()
    broken["header"]["competitions"][0]["competitors"].pop()
    assert EspnClient.live_update_from_summary(broken, EVENT_ID) is None
    bad_state = _summary(state="weird")
    assert EspnClient.live_update_from_summary(bad_state, EVENT_ID) is None


def test_live_match_uses_one_request_per_poll():
    async def scenario():
        espn = RecordingEspn(summary=_summary(), scoreboard_match=_scoreboard_match())
        provider = _provider(espn)

        await provider.get_current_or_next_whitecaps_fixture(1613)  # first tick: scoreboard, finds live match
        espn.calls.clear()

        match = await provider.get_current_or_next_whitecaps_fixture(1613)
        events = await provider.get_key_events(match.fixture_id)
        return match, events, espn.calls

    match, events, calls = asyncio.run(scenario())
    assert calls == [(ESPN_SUMMARY_URL, LIVE_REQUEST_TIMEOUT)]  # one request, short timeout, key events reused
    assert (match.home_goals, match.away_goals, match.state) == (1, 2, "in")
    # Fields the summary doesn't carry are kept from the scoreboard.
    assert (match.venue, match.broadcasts, match.away_logo) == ("Stade Saputo", ("TSN",), "away.png")
    assert [e.player_name for e in events] == ["Brian White"]
    assert events[0].wallclock is not None


def test_live_summary_failure_falls_back_to_scoreboard_with_short_timeout():
    async def scenario():
        espn = RecordingEspn(summary_error=asyncio.TimeoutError(), scoreboard_match=_scoreboard_match())
        provider = _provider(espn)
        await provider.get_current_or_next_whitecaps_fixture(1613)
        espn.calls.clear()
        match = await provider.get_current_or_next_whitecaps_fixture(1613)
        return match, espn.calls

    match, calls = asyncio.run(scenario())
    assert match is not None and match.state == "in"
    assert calls == [(ESPN_SUMMARY_URL, LIVE_REQUEST_TIMEOUT), (ESPN_SCOREBOARD_URL, LIVE_REQUEST_TIMEOUT)]


def test_bad_summary_payload_falls_back_to_scoreboard():
    async def scenario():
        espn = RecordingEspn(summary={"header": {}}, scoreboard_match=_scoreboard_match())
        provider = _provider(espn)
        await provider.get_current_or_next_whitecaps_fixture(1613)
        espn.calls.clear()
        await provider.get_current_or_next_whitecaps_fixture(1613)
        return espn.calls

    calls = asyncio.run(scenario())
    assert [url for url, _ in calls] == [ESPN_SUMMARY_URL, ESPN_SCOREBOARD_URL]


def test_not_live_mode_far_from_kickoff_or_long_overdue():
    async def scenario(starts_at):
        espn = RecordingEspn(summary=_summary(state="pre"), scoreboard_match=_scoreboard_match("PRE", starts_at))
        provider = _provider(espn)
        await provider.get_current_or_next_whitecaps_fixture(1613)
        espn.calls.clear()
        await provider.get_current_or_next_whitecaps_fixture(1613)
        return [url for url, _ in espn.calls]

    assert asyncio.run(scenario(NOW + timedelta(hours=2))) == [ESPN_SCOREBOARD_URL]
    assert asyncio.run(scenario(NOW - timedelta(hours=4))) == [ESPN_SCOREBOARD_URL]  # postponed / stale
    assert asyncio.run(scenario(NOW + timedelta(minutes=4))) == [ESPN_SUMMARY_URL]  # about to kick off


def test_live_polling_intervals():
    def delay(state, starts_in, fulltime_posted=False):
        m = _scoreboard_match(state, NOW + starts_in)
        return compute_poll_delay(m, base_seconds=30, live_seconds=10, fulltime_posted=fulltime_posted, now=NOW)

    assert delay("IN", timedelta(minutes=-50)) == 10
    assert delay("PRE", timedelta(minutes=4)) == 10      # last 5 min before kickoff
    assert delay("PRE", timedelta(minutes=-3)) == 10     # kickoff overdue
    assert delay("PRE", timedelta(minutes=20)) == 30     # 5-30 min out
    assert delay("PRE", timedelta(minutes=5, seconds=10)) == 10  # wakes right at the 5-min mark
    assert delay("POST", timedelta(hours=-2)) == 10      # full time not posted yet
    assert delay("POST", timedelta(hours=-2), fulltime_posted=True) == 30 * 60


def test_goal_timing_is_logged(caplog):
    from test_fallback_dedupe import _bot_with_thread, _live

    async def scenario():
        bot, thread = _bot_with_thread()
        espn_goal_time = datetime.now(timezone.utc) - timedelta(seconds=40)
        from whitecaps_bot.apifootball import KeyEvent
        goal = KeyEvent(
            fixture_id=761934, event_type="goal", elapsed=72, team_name="Vancouver Whitecaps",
            player_name="Brian White", detail="", text="Goal", wallclock=espn_goal_time,
        )
        bot.api.match, bot.api.events = _live(761934, goals=(1, 1)), []
        await bot._update_once()
        bot.api.match, bot.api.events = _live(761934, goals=(1, 2)), [goal]
        await bot._update_once()
        await bot.close()

    with caplog.at_level(logging.INFO, logger="whitecaps_bot"):
        asyncio.run(scenario())

    lines = [r.getMessage() for r in caplog.records]
    assert any(line.startswith("Score change seen: CF Montréal 1-2 Vancouver Whitecaps") for line in lines)
    goal_line = next(line for line in lines if line.startswith("Goal posted (key event)"))
    assert "Brian White 72'" in goal_line
    assert "ESPN goal time" in goal_line and "s before post" in goal_line
    assert "score change first seen 0s before post" in goal_line


def test_blank_feed_result_mid_match_keeps_live_polling():
    from test_fallback_dedupe import _bot_with_thread, _live

    async def scenario():
        bot, _thread = _bot_with_thread()
        bot.api.match, bot.api.events = _live(761934), []
        await bot._update_once()
        bot.api.match = None  # feed glitch: no fixture returned
        await bot._update_once()
        delay = compute_poll_delay(
            bot._last_fetched_match or bot._last_known_match,
            base_seconds=30, live_seconds=10, fulltime_posted=bot.tracker.fulltime_posted,
        )
        active = bot._match_is_active()
        await bot.close()
        return delay, active

    delay, active = asyncio.run(scenario())
    assert delay == 10
    assert active is True
