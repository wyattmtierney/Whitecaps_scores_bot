from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from whitecaps_bot.apifootball import CardEvent, MatchState, StandingsEntry, SubstitutionEvent


ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary"
ESPN_STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/soccer/usa.1/standings"


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
    def __init__(self, team_id: str = "9727", team_name: str = "Vancouver Whitecaps", timeout_seconds: int = 15):
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

        # Venue
        venue = (comp.get("venue") or {}).get("fullName", "")

        # Broadcasts
        broadcasts: list[str] = []
        for b in comp.get("broadcasts", []):
            names = b.get("names", [])
            if names:
                broadcasts.extend(names)
            else:
                media = b.get("media", {})
                short = media.get("shortName") or media.get("name", "")
                if short:
                    broadcasts.append(short)
        for gb in comp.get("geoBroadcasts", []):
            media = gb.get("media", {})
            short = media.get("shortName") or media.get("name", "")
            if short and short not in broadcasts:
                broadcasts.append(short)

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
            venue=venue,
            broadcasts=tuple(broadcasts),
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

    async def get_upcoming_fixtures(self, days_ahead: int = 14) -> list[MatchState]:
        today = datetime.now(timezone.utc).date()
        now_utc = datetime.now(timezone.utc)

        seen: set[int] = set()
        upcoming: list[MatchState] = []

        for offset in range(0, days_ahead + 1):
            day = today + timedelta(days=offset)
            payload = await self._get(
                ESPN_SCOREBOARD_URL,
                {"dates": day.strftime("%Y%m%d"), "team": self.team_id},
            )
            for event in payload.get("events", []):
                match = self._extract_match(event)
                if match is not None and match.fixture_id not in seen:
                    seen.add(match.fixture_id)
                    if match.starts_at and match.starts_at > now_utc:
                        upcoming.append(match)

        upcoming.sort(key=lambda m: m.starts_at)
        return upcoming[:5]

    async def get_standings(self) -> list[StandingsEntry]:
        payload = await self._get(ESPN_STANDINGS_URL, {})
        entries: list[StandingsEntry] = []

        # Handle conference-based structure (MLS has Eastern/Western)
        raw_entries: list[dict] = []
        if "children" in payload:
            for child in payload["children"]:
                for entry in child.get("standings", {}).get("entries", []):
                    raw_entries.append(entry)
        else:
            for entry in payload.get("standings", {}).get("entries", []):
                raw_entries.append(entry)

        for idx, entry in enumerate(raw_entries, 1):
            team = entry.get("team", {})
            stats = {s.get("name", ""): s.get("value", 0) for s in entry.get("stats", [])}
            entries.append(StandingsEntry(
                rank=idx,
                team_name=team.get("displayName", "Unknown"),
                played=int(stats.get("gamesPlayed", 0)),
                wins=int(stats.get("wins", 0)),
                draws=int(stats.get("ties", stats.get("draws", 0))),
                losses=int(stats.get("losses", 0)),
                goals_for=int(stats.get("pointsFor", 0)),
                goals_against=int(stats.get("pointsAgainst", 0)),
                goal_difference=int(stats.get("pointDifferential", 0)),
                points=int(stats.get("points", 0)),
            ))

        return entries

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

    async def get_cards(self, event_id: str, fixture_id: int) -> list[CardEvent]:
        payload = await self._get(ESPN_SUMMARY_URL, {"event": event_id})
        plays = payload.get("plays", [])
        cards: list[CardEvent] = []

        for play in plays:
            text = (play.get("text") or "").lower()
            card_type = None
            if "red card" in text:
                card_type = "Red Card"
            elif "yellow card" in text or "booking" in text:
                card_type = "Yellow Card"

            if card_type is None:
                continue

            team = ((play.get("team") or {}).get("displayName")) or "Unknown team"
            minute = play.get("clock", {}).get("value")
            player = self._extract_card_player(play)

            cards.append(CardEvent(
                fixture_id=fixture_id,
                elapsed=int(minute) if isinstance(minute, (int, float)) else None,
                team_name=team,
                player_name=player,
                card_type=card_type,
            ))

        return cards

    @staticmethod
    def _extract_card_player(play: dict) -> str:
        for p in play.get("participants", []):
            if isinstance(p, dict):
                athlete = p.get("athlete", {})
                if isinstance(athlete, dict):
                    name = athlete.get("displayName") or athlete.get("shortName")
                    if name:
                        return name
        # Fall back to parsing from text like "Yellow Card - John Smith"
        original_text = play.get("text") or ""
        parts = original_text.split(" - ", 1)
        if len(parts) > 1:
            name_part = parts[1].strip()
            paren = name_part.find("(")
            if paren > 0:
                name_part = name_part[:paren].strip()
            if name_part:
                return name_part
        return "Unknown"
