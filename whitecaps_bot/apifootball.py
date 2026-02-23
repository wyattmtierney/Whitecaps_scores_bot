from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp


BASE_URL = "https://v3.football.api-sports.io"

PRE_MATCH_CODES = {"TBD", "NS", "PST", "CANC", "ABD", "AWD", "WO"}
IN_MATCH_CODES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"}
FINAL_CODES = {"FT", "AET", "PEN"}


@dataclass(frozen=True)
class MatchState:
    fixture_id: int
    home_name: str
    away_name: str
    home_goals: int | None
    away_goals: int | None
    elapsed: int | None
    short_status: str
    long_status: str
    starts_at: datetime | None

    @property
    def state(self) -> str:
        short = (self.short_status or "").upper()
        if short in IN_MATCH_CODES:
            return "in"
        if short in FINAL_CODES:
            return "post"
        return "pre"


@dataclass(frozen=True)
class SubstitutionEvent:
    fixture_id: int
    elapsed: int | None
    team_name: str
    player_in: str
    player_out: str

    @property
    def dedupe_key(self) -> str:
        return f"{self.fixture_id}:{self.elapsed}:{self.team_name}:{self.player_in}:{self.player_out}"


class ApiFootballClient:
    def __init__(self, api_key: str, timeout_seconds: int = 15):
        self._headers = {
            "x-apisports-key": api_key,
        }
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        async with aiohttp.ClientSession(timeout=self._timeout, headers=self._headers) as session:
            async with session.get(f"{BASE_URL}{path}", params=params) as response:
                response.raise_for_status()
                return await response.json()

    @staticmethod
    def _to_match_state(item: dict[str, Any]) -> MatchState:
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        status = fixture.get("status", {})

        starts_at_raw = fixture.get("date")
        starts_at = None
        if starts_at_raw:
            starts_at = datetime.fromisoformat(starts_at_raw.replace("Z", "+00:00")).astimezone(timezone.utc)

        return MatchState(
            fixture_id=fixture.get("id"),
            home_name=teams.get("home", {}).get("name", "Home"),
            away_name=teams.get("away", {}).get("name", "Away"),
            home_goals=goals.get("home"),
            away_goals=goals.get("away"),
            elapsed=status.get("elapsed"),
            short_status=status.get("short", ""),
            long_status=status.get("long", ""),
            starts_at=starts_at,
        )

    async def get_live_whitecaps_fixture(self, team_id: int) -> MatchState | None:
        payload = await self._get("/fixtures", {"team": team_id, "live": "all"})
        response_items = payload.get("response", [])
        if not response_items:
            return None

        item = sorted(
            response_items,
            key=lambda x: x.get("fixture", {}).get("status", {}).get("elapsed") or 0,
        )[0]

        return self._to_match_state(item)

    async def get_next_whitecaps_fixture(self, team_id: int) -> MatchState | None:
        payload = await self._get("/fixtures", {"team": team_id, "next": 1})
        response_items = payload.get("response", [])
        if not response_items:
            return None
        return self._to_match_state(response_items[0])

    async def get_current_or_next_whitecaps_fixture(self, team_id: int) -> MatchState | None:
        live = await self.get_live_whitecaps_fixture(team_id)
        if live:
            return live
        return await self.get_next_whitecaps_fixture(team_id)

    async def get_substitutions(self, fixture_id: int) -> list[SubstitutionEvent]:
        payload = await self._get("/fixtures/events", {"fixture": fixture_id})
        subs: list[SubstitutionEvent] = []
        for event in payload.get("response", []):
            if (event.get("type") or "").lower() != "subst":
                continue

            subs.append(
                SubstitutionEvent(
                    fixture_id=fixture_id,
                    elapsed=event.get("time", {}).get("elapsed"),
                    team_name=event.get("team", {}).get("name", "Unknown team"),
                    player_in=event.get("assist", {}).get("name") or "Unknown in",
                    player_out=event.get("player", {}).get("name") or "Unknown out",
                )
            )

        subs.sort(key=lambda s: s.elapsed or 0)
        return subs


async def with_retry(coro_factory, retries: int = 3, delay_seconds: float = 1.0):
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_factory()
        except Exception as err:  # noqa: BLE001
            last_error = err
            if attempt == retries:
                break
            await asyncio.sleep(delay_seconds * attempt)
    raise RuntimeError(f"Operation failed after {retries} attempts") from last_error
