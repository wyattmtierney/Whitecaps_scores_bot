from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from whitecaps_bot.apifootball import MatchState, SubstitutionEvent


ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary"


def _athlete_name(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return first.get("displayName") or first.get("shortName") or default
        if isinstance(first, str):
            return first
    if isinstance(value, dict):
        return value.get("displayName") or value.get("shortName") or default
    return default


@dataclass(frozen=True)
class EspnFixtureRef:
    event_id: str
    match: MatchState


class EspnClient:
    def __init__(self, team_id: str = "9720", team_name: str = "Vancouver Whitecaps", timeout_seconds: int = 15):
        self.team_id = str(team_id)
        self.team_name = team_name.lower()
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json()

    def _is_target_team(self, home: dict[str, Any], away: dict[str, Any], home_name: str, away_name: str) -> bool:
        home_id = str((home.get("team") or {}).get("id") or "")
        away_id = str((away.get("team") or {}).get("id") or "")

        if self.team_id and (self.team_id == home_id or self.team_id == away_id):
            return True

        return self.team_name in home_name.lower() or self.team_name in away_name.lower()

    def _extract_match(self, event: dict[str, Any]) -> MatchState | None:
        comp = (event.get("competitions") or [{}])[0]
        competitors = comp.get("competitors") or []
        if len(competitors) < 2:
            return None

        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home_name = (home.get("team") or {}).get("displayName", "Home")
        away_name = (away.get("team") or {}).get("displayName", "Away")

        if not self._is_target_team(home, away, home_name, away_name):
            return None

        status = event.get("status") or {}
        status_type = status.get("type") or {}
        short_detail = status_type.get("shortDetail") or ""
        elapsed = None
        m = re.search(r"(\d+)", short_detail)
        if m:
            elapsed = int(m.group(1))

        starts_at = None
        date_raw = event.get("date")
        if date_raw:
            starts_at = datetime.fromisoformat(date_raw.replace("Z", "+00:00")).astimezone(timezone.utc)

        return MatchState(
            fixture_id=int(event.get("id")),
            home_name=home_name,
            away_name=away_name,
            home_goals=int(home.get("score") or 0),
            away_goals=int(away.get("score") or 0),
            elapsed=elapsed,
            short_status=(status_type.get("state") or "pre").upper(),
            long_status=status_type.get("detail") or status_type.get("description") or "",
            starts_at=starts_at,
        )

    async def get_current_or_next_whitecaps_fixture(self) -> tuple[MatchState | None, str | None]:
        now = datetime.now(timezone.utc).date()
        candidates: list[EspnFixtureRef] = []

        # Public-ESPN-API docs show team-filtered scoreboard usage.
        for offset in (-1, 0, 1, 2, 3):
            day = now + timedelta(days=offset)
            payload = await self._get(ESPN_SCOREBOARD_URL, {"dates": day.strftime("%Y%m%d"), "team": self.team_id})
            for event in payload.get("events", []):
                match = self._extract_match(event)
                if match is not None:
                    candidates.append(EspnFixtureRef(event_id=str(event.get("id")), match=match))

        if not candidates:
            return None, None

        in_progress = [c for c in candidates if c.match.state == "in"]
        if in_progress:
            chosen = sorted(in_progress, key=lambda c: c.match.elapsed or 0)[0]
            return chosen.match, chosen.event_id

        upcoming = [c for c in candidates if c.match.starts_at is not None and c.match.starts_at >= datetime.now(timezone.utc)]
        if upcoming:
            chosen = sorted(upcoming, key=lambda c: c.match.starts_at)[0]
            return chosen.match, chosen.event_id

        chosen = sorted(candidates, key=lambda c: c.match.starts_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[0]
        return chosen.match, chosen.event_id

    async def get_substitutions(self, event_id: str, fixture_id: int) -> list[SubstitutionEvent]:
        payload = await self._get(ESPN_SUMMARY_URL, {"event": event_id})
        plays = payload.get("plays", [])
        substitutions: list[SubstitutionEvent] = []

        for play in plays:
            text = (play.get("text") or "").lower()
            if "substitution" not in text:
                continue
            team = ((play.get("team") or {}).get("displayName")) or "Unknown team"
            minute = play.get("clock", {}).get("value")
            substitutions.append(
                SubstitutionEvent(
                    fixture_id=fixture_id,
                    elapsed=int(minute) if isinstance(minute, (int, float)) else None,
                    team_name=team,
                    player_in=_athlete_name(play.get("athletesIn"), "Unknown in"),
                    player_out=_athlete_name(play.get("athletesOut"), "Unknown out"),
                )
            )

        return substitutions
