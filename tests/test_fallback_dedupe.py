"""Regression tests for duplicate posts when switching data providers mid-match."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from whitecaps_bot.apifootball import KeyEvent, MatchState
from whitecaps_bot.config import Settings
from whitecaps_bot.provider import ScoreProvider
from whitecaps_bot.tracker import MatchTracker

KICKOFF = datetime.now(timezone.utc) - timedelta(minutes=40)
ESPN_ID = 761934
API_FOOTBALL_ID = 1350001


def _live(fixture_id, starts_at=KICKOFF, goals=(0, 1)):
    return MatchState(
        fixture_id=fixture_id,
        home_name="CF Montréal",
        away_name="Vancouver Whitecaps",
        home_goals=goals[0],
        away_goals=goals[1],
        elapsed=40,
        short_status="IN" if fixture_id == ESPN_ID else "1H",
        long_status="First Half",
        starts_at=starts_at,
    )


GOAL = KeyEvent(
    fixture_id=ESPN_ID, event_type="goal", elapsed=23, team_name="Vancouver Whitecaps",
    player_name="Brian White", detail="", text="Goal",
)


class FakeThread:
    def __init__(self):
        self.sent = []

    async def send(self, *args, **kwargs):
        self.sent.append(kwargs.get("embed") or (args[0] if args else None))


class FakeApi:
    def __init__(self):
        self.match = None
        self.events = []

    async def get_current_or_next_whitecaps_fixture(self, team_id):
        return self.match

    async def get_key_events(self, fixture_id):
        return list(self.events)


def _bot_with_thread():
    from whitecaps_bot.bot import WhitecapsBot

    settings = Settings(
        discord_token="x", discord_guild_id=None, channel_id=None, forum_channel_id=None,
        api_football_key=None, espn_team_id="9727", espn_team_name="Vancouver Whitecaps",
        whitecaps_team_id=1603, poll_interval_seconds=30,
    )
    bot = WhitecapsBot(settings)
    bot.api = FakeApi()
    thread = FakeThread()
    bot.tracker.reset_for_new_fixture(ESPN_ID, KICKOFF)
    bot.tracker.match_thread_id = 4242
    bot.get_channel = lambda channel_id: thread if channel_id == 4242 else None
    return bot, thread


def test_espn_outage_mid_match_does_not_repost_anything():
    async def scenario():
        bot, thread = _bot_with_thread()

        # Tick 1: ESPN live, goal already scored -> kickoff + goal posted.
        bot.api.match, bot.api.events = _live(ESPN_ID), [GOAL]
        await bot._update_once()
        posted_after_espn = len(thread.sent)

        # Tick 2: ESPN down, API-Football reports the same match under its own ID.
        bot.api.match, bot.api.events = _live(API_FOOTBALL_ID, KICKOFF + timedelta(minutes=1)), []
        await bot._update_once()

        # Tick 3: ESPN back with the same goal event.
        bot.api.match, bot.api.events = _live(ESPN_ID), [GOAL]
        await bot._update_once()

        await bot.close()
        return posted_after_espn, len(thread.sent), bot.tracker.match_thread_id

    posted_after_espn, posted_total, thread_id = asyncio.run(scenario())
    assert posted_after_espn == 2  # kickoff + goal
    assert posted_total == 2       # nothing reposted after the outage
    assert thread_id == 4242       # still posting to the same match thread


def test_genuinely_new_match_still_resets_state():
    tracker = MatchTracker()
    tracker.reset_for_new_fixture(ESPN_ID, KICKOFF)
    tracker.posted_event_keys.add("something")

    next_week = _live(761999, KICKOFF + timedelta(days=7))
    assert tracker.is_same_match(next_week) is False


def test_same_match_detection():
    tracker = MatchTracker()
    assert tracker.is_same_match(_live(ESPN_ID)) is False  # nothing tracked yet

    tracker.reset_for_new_fixture(ESPN_ID, KICKOFF)
    assert tracker.is_same_match(_live(ESPN_ID)) is True
    assert tracker.is_same_match(_live(API_FOOTBALL_ID, KICKOFF + timedelta(minutes=5))) is True
    assert tracker.is_same_match(_live(API_FOOTBALL_ID, KICKOFF + timedelta(hours=4))) is False
    assert tracker.is_same_match(_live(API_FOOTBALL_ID, starts_at=None)) is False


def test_key_events_skipped_while_on_fallback():
    async def scenario():
        provider = ScoreProvider(api_football_key="k", espn_team_id="9727", espn_team_name="Vancouver Whitecaps")
        provider.espn.get_current_or_next_whitecaps_fixture = AsyncMock(return_value=(_live(ESPN_ID), str(ESPN_ID)))
        provider.espn.get_key_events = AsyncMock(return_value=[GOAL])
        provider.api_football.get_current_or_next_whitecaps_fixture = AsyncMock(return_value=_live(API_FOOTBALL_ID))

        await provider.get_current_or_next_whitecaps_fixture(1603)
        on_espn = await provider.get_key_events(ESPN_ID)

        provider.espn.get_current_or_next_whitecaps_fixture = AsyncMock(side_effect=asyncio.TimeoutError)
        provider.espn.get_summary = AsyncMock(side_effect=asyncio.TimeoutError)  # live mode tries this first
        await provider.get_current_or_next_whitecaps_fixture(1603)
        on_fallback = await provider.get_key_events(API_FOOTBALL_ID)
        return on_espn, on_fallback

    on_espn, on_fallback = asyncio.run(scenario())
    assert on_espn == [GOAL]
    assert on_fallback == []


def _finished(fixture_id=ESPN_ID):
    from dataclasses import replace
    return replace(_live(fixture_id, goals=(1, 2)), short_status="FT", elapsed=90)


def test_restart_after_full_time_posts_nothing():
    """A deploy after a match must not re-post into the old thread."""
    async def scenario():
        from whitecaps_bot.bot import WhitecapsBot
        from whitecaps_bot.tracker import compute_poll_delay

        bot, thread = _bot_with_thread()
        # Simulate a fresh process: nothing tracked yet.
        bot.tracker = type(bot.tracker)()
        bot.api.match = _finished()
        assert bot.api.match.state == "post"

        await bot._update_once()
        await bot._update_once()  # and on later ticks

        delay = compute_poll_delay(bot.api.match, base_seconds=30,
                                   fulltime_posted=bot.tracker.fulltime_posted)
        await bot.close()
        return thread.sent, bot.tracker, delay

    sent, tracker, delay = asyncio.run(scenario())
    assert sent == []
    assert tracker.match_thread_id is None
    assert tracker.fulltime_posted is True
    assert delay == 30 * 60  # goes back to slow polling


def test_full_time_still_posted_when_match_ends_while_running():
    async def scenario():
        bot, thread = _bot_with_thread()
        bot.api.match, bot.api.events = _live(ESPN_ID), []
        await bot._update_once()
        sent_live = len(thread.sent)
        bot.api.match = _finished()
        await bot._update_once()
        await bot.close()
        return sent_live, len(thread.sent)

    sent_live, sent_total = asyncio.run(scenario())
    assert sent_total == sent_live + 1  # exactly one full-time post
