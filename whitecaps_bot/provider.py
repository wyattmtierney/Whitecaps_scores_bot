from __future__ import annotations

import asyncio
import logging

import aiohttp

from whitecaps_bot.apifootball import ApiFootballClient, KeyEvent, MatchState, StandingsEntry
from whitecaps_bot.espn import EspnClient

_NETWORK_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError)

logger = logging.getLogger("whitecaps_bot.provider")


class ScoreProvider:
    def __init__(self, api_football_key: str | None, espn_team_id: str, espn_team_name: str):
        self.espn = EspnClient(team_id=espn_team_id, team_name=espn_team_name)
        self.api_football = ApiFootballClient(api_football_key) if api_football_key else None
        self._last_espn_event_id: str | None = None
        # True only when the latest fixture came from ESPN. Key events come
        # from ESPN, so after a fallback tick the stored ESPN event ID may
        # belong to a different match.
        self._last_fixture_from_espn = False

    async def get_current_or_next_whitecaps_fixture(self, team_id: int) -> MatchState | None:
        try:
            match, event_id = await self.espn.get_current_or_next_whitecaps_fixture()
            if match:
                self._last_espn_event_id = event_id
                self._last_fixture_from_espn = True
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
        if self._last_espn_event_id and self._last_fixture_from_espn:
            try:
                return await self.espn.get_key_events(self._last_espn_event_id, fixture_id)
            except _NETWORK_ERRORS:
                logger.exception("ESPN key events fetch failed")
        return []

