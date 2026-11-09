from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import aiohttp

from whitecaps_bot.apifootball import ApiFootballClient, KeyEvent, MatchState, StandingsEntry
from whitecaps_bot.espn import EspnClient

_NETWORK_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError)

logger = logging.getLogger("whitecaps_bot.provider")

# Live mode: during a match (or just before kickoff) poll only the ESPN match
# summary, which has the score, status and key events in one response,
# instead of five scoreboard days plus the summary.
LIVE_MODE_BEFORE_KICKOFF = timedelta(minutes=5)
# Stop treating an unstarted match as "about to start" this long after its
# scheduled kickoff (postponements, bad data), so we don't stay in live mode.
LIVE_MODE_MAX_OVERDUE = timedelta(hours=3)
# Fail fast during a match: a slow ESPN response is abandoned after this many
# seconds and the next poll (10s later) tries again.
LIVE_REQUEST_TIMEOUT = 4.0


class ScoreProvider:
    def __init__(self, api_football_key: str | None, espn_team_id: str, espn_team_name: str):
        self.espn = EspnClient(team_id=espn_team_id, team_name=espn_team_name)
        self.api_football = ApiFootballClient(api_football_key) if api_football_key else None
        self._last_espn_event_id: str | None = None
        # True only when the latest fixture came from ESPN. Key events come
        # from ESPN, so after a fallback tick the stored ESPN event ID may
        # belong to a different match.
        self._last_fixture_from_espn = False
        # Last full match from ESPN; live-mode updates are applied on top of it
        # so venue, broadcasts and logos carry over.
        self._last_espn_match: MatchState | None = None
        # Key events parsed from this tick's summary, so get_key_events doesn't
        # fetch the same summary a second time.
        self._prefetched_events: tuple[str, list[KeyEvent]] | None = None

    def _in_live_mode(self, now: datetime | None = None) -> bool:
        match = self._last_espn_match
        if match is None or not self._last_espn_event_id or not self._last_fixture_from_espn:
            return False
        if match.state == "in":
            return True
        if match.state == "pre" and match.starts_at is not None:
            until_kickoff = match.starts_at - (now or datetime.now(timezone.utc))
            return -LIVE_MODE_MAX_OVERDUE <= until_kickoff <= LIVE_MODE_BEFORE_KICKOFF
        return False

    async def _live_snapshot(self) -> MatchState | None:
        """One summary request -> updated match + prefetched key events."""
        event_id = self._last_espn_event_id
        base = self._last_espn_match
        assert event_id is not None and base is not None
        try:
            payload = await self.espn.get_summary(event_id, timeout=LIVE_REQUEST_TIMEOUT)
        except _NETWORK_ERRORS as err:
            logger.warning("Live summary fetch failed (%s); using scoreboard this tick", type(err).__name__)
            return None

        update = self.espn.live_update_from_summary(payload, event_id)
        if update is None:
            logger.warning("Live summary for event %s missing score/status; using scoreboard this tick", event_id)
            return None

        match = replace(base, **update)
        self._prefetched_events = (event_id, self.espn.parse_key_events(payload, match.fixture_id))
        return match

    async def get_current_or_next_whitecaps_fixture(self, team_id: int) -> MatchState | None:
        self._prefetched_events = None
        live = self._in_live_mode()

        if live:
            match = await self._live_snapshot()
            if match is not None:
                self._last_espn_match = match
                return match

        try:
            # In live mode the scoreboard is only a fallback, so it gets the
            # short timeout too.
            match, event_id = await self.espn.get_current_or_next_whitecaps_fixture(
                timeout=LIVE_REQUEST_TIMEOUT if live else None
            )
            if match:
                self._last_espn_event_id = event_id
                self._last_fixture_from_espn = True
                self._last_espn_match = match
                return match
        except _NETWORK_ERRORS:
            logger.exception("ESPN fetch failed; trying API-Football fallback")

        self._last_fixture_from_espn = False
        if self.api_football is None:
            return None

        return await self.api_football.get_current_or_next_whitecaps_fixture(team_id)

    async def get_upcoming_fixtures(self) -> list[MatchState]:
        return await self.espn.get_upcoming_fixtures()

    async def get_standings(self) -> list[StandingsEntry]:
        return await self.espn.get_standings()

    async def get_key_events(self, fixture_id: int) -> list[KeyEvent]:
        # Skip while on the fallback; anything missed is picked up (and
        # deduplicated by ESPN's IDs) once ESPN is back.
        if not (self._last_espn_event_id and self._last_fixture_from_espn):
            return []

        if self._prefetched_events and self._prefetched_events[0] == self._last_espn_event_id:
            events = self._prefetched_events[1]
            self._prefetched_events = None
            return events

        try:
            return await self.espn.get_key_events(
                self._last_espn_event_id, fixture_id,
                timeout=LIVE_REQUEST_TIMEOUT if self._in_live_mode() else None,
            )
        except _NETWORK_ERRORS:
            logger.exception("ESPN key events fetch failed")
        return []
