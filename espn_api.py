"""ESPN API client for fetching Vancouver Whitecaps MLS match data."""

import logging
import aiohttp
from datetime import datetime, timezone

log = logging.getLogger(__name__)

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1"
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/soccer/usa.1/standings"
WHITECAPS_ID = "9727"
WHITECAPS_NAMES = {"Vancouver Whitecaps FC", "Vancouver Whitecaps", "Whitecaps"}

_STAT_KEY_MAP = {
    "ppg": "pointsPerGame",
}


async def _fetch(session: aiohttp.ClientSession, url: str) -> dict | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                log.debug("GET %s -> 200, keys=%s", url, list(data.keys()) if isinstance(data, dict) else type(data))
                return data
            log.warning("GET %s -> HTTP %s", url, resp.status)
    except aiohttp.ClientError as e:
        log.warning("Network error fetching %s: %s", url, e)
    except Exception as e:
        log.warning("Unexpected error fetching %s: %s", url, e)
    return None


def _is_whitecaps(competitor: dict) -> bool:
    name = competitor.get("team", {}).get("displayName", "")
    team_id = competitor.get("team", {}).get("id", "")
    return name in WHITECAPS_NAMES or str(team_id) == WHITECAPS_ID


def _parse_competitor(comp: dict) -> dict:
    team = comp.get("team", {})
    logo = team.get("logo") or (team.get("logos") or [{}])[0].get("href", "")
    return {
        "id": team.get("id"),
        "name": team.get("displayName", "Unknown"),
        "abbreviation": team.get("abbreviation", "???"),
        "logo": logo,
        "score": comp.get("score", "0"),
        "home_away": comp.get("homeAway", ""),
        "winner": comp.get("winner", False),
    }


def _parse_match(event: dict) -> dict | None:
    competitions = event.get("competitions", [])
    if not competitions:
        return None
    comp = competitions[0]
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return None
    home = away = None
    for c in competitors:
        if c.get("homeAway") == "home":
            home = _parse_competitor(c)
        else:
            away = _parse_competitor(c)
    if not home or not away:
        return None
    status = comp.get("status", {})
    status_type = status.get("type", {})
    return {
        "id": event.get("id"),
        "name": event.get("name", ""),
        "date": event.get("date", ""),
        "venue": comp.get("venue", {}).get("fullName", ""),
        "home": home,
        "away": away,
        "status": {
            "state": status_type.get("state", "pre"),
            "detail": status_type.get("detail", ""),
            "description": status_type.get("description", ""),
            "clock": status.get("displayClock", "0'"),
            "period": status.get("period", 0),
        },
        "is_whitecaps_home": _is_whitecaps(competitors[0]) if competitors[0].get("homeAway") == "home" else _is_whitecaps(competitors[1]),
    }


async def get_scoreboard(session: aiohttp.ClientSession) -> list[dict]:
    data = await _fetch(session, f"{BASE_URL}/scoreboard")
    if not data:
        return []
    matches = []
    for event in data.get("events", []):
        for comp in event.get("competitions", []):
            for c in comp.get("competitors", []):
                if _is_whitecaps(c):
                    parsed = _parse_match(event)
                    if parsed:
                        matches.append(parsed)
                    break
    return matches


async def get_match_summary(session: aiohttp.ClientSession, event_id: str) -> dict | None:
    data = await _fetch(session, f"{BASE_URL}/summary?event={event_id}")
    if not data:
        return None
    key_events = []
    rosters = {}
    for roster in data.get("rosters", []):
        team_name = roster.get("team", {}).get("displayName", "")
        team_abbr = roster.get("team", {}).get("abbreviation", "")
        for entry in roster.get("roster", []):
            player = entry.get("athlete", {})
            pid = player.get("id", "")
            rosters[pid] = {
                "name": player.get("displayName", "Unknown"),
                "team": team_name,
                "team_abbr": team_abbr,
                "jersey": entry.get("jersey", ""),
                "position": entry.get("position", {}).get("abbreviation", ""),
            }
    for item in data.get("keyEvents", []):
        play = item.get("play", item)
        participants = []
        for p in play.get("participants", []):
            athlete = p.get("athlete", {})
            participants.append({
                "name": athlete.get("displayName", "Unknown"),
                "id": athlete.get("id", ""),
                "type": p.get("type", {}).get("text", ""),
            })
        team = play.get("team", {})
        key_events.append({
            "type": play.get("type", {}).get("text", ""),
            "clock": play.get("clock", {}).get("displayValue", ""),
            "period": play.get("period", {}).get("number", 0),
            "text": play.get("text", ""),
            "team": team.get("displayName", ""),
            "team_abbr": team.get("abbreviation", ""),
            "participants": participants,
        })
    details = []
    for item in data.get("commentary", []):
        details.append({
            "time": item.get("time", {}).get("displayValue", ""),
            "text": item.get("text", ""),
        })
    formations = {}
    for roster in data.get("rosters", []):
        team_name = roster.get("team", {}).get("displayName", "")
        formation = roster.get("formation", "")
        if formation:
            formations[team_name] = formation
    return {"key_events": key_events, "rosters": rosters, "commentary": details, "formations": formations}


async def get_schedule(session: aiohttp.ClientSession) -> list[dict]:
    year = datetime.now(timezone.utc).year
    for url in (
        f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year - 1}",
        f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year}",
        f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule",
    ):
        data = await _fetch(session, url)
        if not data:
            continue
        events = data.get("events", [])
        log.info("Schedule url=%s events=%d", url, len(events))
        matches = [m for e in events for m in [_parse_match(e)] if m]
        if matches:
            log.info("get_schedule: %d matches", len(matches))
            return matches
    return []


async def get_standings(session: aiohttp.ClientSession) -> dict | None:
    data = await _fetch(session, STANDINGS_URL)
    if not data:
        return None
    children = data.get("children") or data.get("groups") or []
    if not children:
        return None
    standings = {}
    for group in children:
        conf_name = group.get("name", "Conference")
        raw_entries = (
            group.get("standings", {}).get("entries")
            or group.get("entries")
            or []
        )
        entries = []
        for entry in raw_entries:
            team = entry.get("team", {})
            logo = team.get("logo") or (team.get("logos") or [{}])[0].get("href", "")
            stats = {}
            for s in entry.get("stats", []):
                raw_key = s.get("name", "")
                key = _STAT_KEY_MAP.get(raw_key, raw_key)
                stats[key] = s.get("displayValue", s.get("value", ""))
            entries.append({
                "name": team.get("displayName", ""),
                "abbreviation": team.get("abbreviation", ""),
                "logo": logo,
                "stats": stats,
                "is_whitecaps": (
                    str(team.get("id", "")) == WHITECAPS_ID
                    or team.get("displayName") in WHITECAPS_NAMES
                ),
            })
        if entries:
            standings[conf_name] = entries
    if standings:
        log.info("get_standings: %d conference(s)", len(standings))
        return standings
    return None


async def get_next_match(session: aiohttp.ClientSession) -> dict | None:
    schedule = await get_schedule(session)
    now = datetime.now(timezone.utc)
    for m in schedule:
        try:
            match_date = datetime.fromisoformat(m["date"].replace("Z", "+00:00"))
            if match_date > now or m["status"]["state"] in ("in", "pre"):
                return m
        except (ValueError, KeyError):
            continue
    scoreboard = await get_scoreboard(session)
    for m in scoreboard:
        if m["status"]["state"] in ("pre", "in"):
            return m
    return None


async def debug_endpoints(session: aiohttp.ClientSession) -> dict:
    year = datetime.now(timezone.utc).year
    urls = {
        "scoreboard": f"{BASE_URL}/scoreboard",
        f"schedule season={year - 1} [primary]": f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year - 1}",
        f"schedule season={year}": f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year}",
        "schedule default": f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule",
        "standings v2 [primary]": STANDINGS_URL,
        f"standings site/v2 season={year}": f"{BASE_URL}/standings?season={year}",
        f"standings site/v2 season={year - 1}": f"{BASE_URL}/standings?season={year - 1}",
    }
    results = {}
    for label, url in urls.items():
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                status = resp.status
                if status == 200:
                    data = await resp.json(content_type=None)
                    keys = list(data.keys()) if isinstance(data, dict) else str(type(data))
                    counts = {k: len(data[k]) for k in ("events", "children", "groups", "entries") if k in data and isinstance(data[k], list)}
                    results[label] = f"200 OK | keys: {keys} | counts: {counts}"
                else:
                    body = await resp.text()
                    results[label] = f"HTTP {status} | {body[:120]}"
        except Exception as e:
            results[label] = f"ERROR: {e}"
    return results
