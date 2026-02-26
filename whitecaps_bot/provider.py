from __future__ import annotations

import logging

from whitecaps_bot.apifootball import ApiFootballClient, CardEvent, MatchState, StandingsEntry, SubstitutionEvent
from whitecaps_bot.espn import EspnClient

logger = logging.getLogger("whitecaps_bot.provider")


class ScoreProvider:
    def __init__(self, api_football_key: str | None, espn_team_id: str, espn_team_name: str):
        self.espn = EspnClient(team_id=espn_team_id, team_name=espn_team_name)
        self.api_football = ApiFootballClient(api_football_key) if api_football_key else None
        self._last_espn_event_id: str | None = None

    async def get_current_or_next_whitecaps_fixture(self, team_id: int) -> MatchState | None:
        try:
            match, event_id = await self.espn.get_current_or_next_whitecaps_fixture()
            if match:
                self._last_espn_event_id = event_id
                return match
        except Exception:  # noqa: BLE001
            logger.exception("ESPN fetch failed; trying API-Football fallback")

        if self.api_football is None:
            return None

        return await self.api_football.get_current_or_next_whitecaps_fixture(team_id)

    async def get_upcoming_fixtures(self) -> list[MatchState]:
        return await self.espn.get_upcoming_fixtures()

    async def get_standings(self) -> list[StandingsEntry]:
        return await self.espn.get_standings()

    async def get_cards(self, fixture_id: int) -> list[CardEvent]:
        if self._last_espn_event_id:
            try:
                return await self.espn.get_cards(self._last_espn_event_id, fixture_id)
            except Exception:  # noqa: BLE001
                logger.exception("ESPN cards fetch failed")
        return []

    async def get_substitutions(self, fixture_id: int) -> list[SubstitutionEvent]:
        if self._last_espn_event_id:
            try:
                return await self.espn.get_substitutions(self._last_espn_event_id, fixture_id)
            except Exception:  # noqa: BLE001
                logger.exception("ESPN substitutions fetch failed; trying API-Football fallback")

        if self.api_football is None:
            return []

        return await self.api_football.get_substitutions(fixture_id)
