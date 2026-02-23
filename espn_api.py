"""ESPN API client for fetching Vancouver Whitecaps MLS match data."""

import json
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone

import aiohttp

log = logging.getLogger(__name__)

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1"
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/soccer/usa.1/standings"
THESPORTSDB_BASE_URL = "https://www.thesportsdb.com/api/v1/json/3"
THESPORTSDB_WHITECAPS_ID = "134864"
WHITECAPS_ID = "9727"
WHITECAPS_NAMES = {"Vancouver Whitecaps FC", "Vancouver Whitecaps", "Whitecaps"}
CACHE_FILE = Path(".whitecaps_cache.json")

_STAT_KEY_MAP = {
    "ppg": "pointsPerGame",
}

_GOAL_HINTS = ("goal", "scores", "finds the net", "penalty")
_SUB_HINTS = ("substitution", "substitutes", "comes on", "replaces")




def _read_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text())
    except Exception as exc:
        log.debug("Failed to read cache: %s", exc)
    return {}


def _write_cache_section(key: str, value) -> None:
    try:
        data = _read_cache()
        data[key] = value
        CACHE_FILE.write_text(json.dumps(data))
    except Exception as exc:
        log.debug("Failed to write cache section %s: %s", key, exc)


def _read_cache_section(key: str):
    data = _read_cache()
    return data.get(key)


def _infer_commentary_event_type(text: str) -> str | None:
    lower = text.lower()
    if any(hint in lower for hint in _GOAL_HINTS):
        return "Goal"
    if any(hint in lower for hint in _SUB_HINTS):
        return "Substitution"
    if "yellow card" in lower:
        return "Yellow Card"
    if "red card" in lower:
        return "Red Card"
    return None


def _extract_names_from_commentary(text: str) -> list[str]:
    # ESPN text often starts with a player name like "Ryan Gauld scores...".
    # Keep this lightweight and resilient rather than using brittle full parsing.
    names = re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+)+)", text)
    # preserve order while deduplicating
    seen = set()
    unique = []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique





def _scoreboard_urls() -> list[str]:
    """Build scoreboard URLs for nearby dates to avoid timezone/date-bound misses."""
    now = datetime.now(timezone.utc)
    days = (now - timedelta(days=1), now, now + timedelta(days=1))
    urls = [f"{BASE_URL}/scoreboard"]
    for day in days:
        urls.append(f"{BASE_URL}/scoreboard?dates={day.strftime('%Y%m%d')}")
    # preserve order while removing duplicates
    return list(dict.fromkeys(urls))


def _parse_score(raw) -> str:
    """Handle ESPN score fields which can be a plain string OR a dict.

    Scoreboard endpoint returns a plain string like "2".
    Schedule endpoint returns a dict like
    {"value": 2.0, "displayValue": "2", "winner": False, ...}.
    """
    if isinstance(raw, dict):
        display = raw.get("displayValue")
        if display not in (None, ""):
            return str(display)

        value = raw.get("value")
        if value in (None, ""):
            return "0"

        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return str(value)
    return str(raw) if raw is not None else "0"

        value = raw.get("value")
        if value in (None, ""):
            return "0"

        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return str(value)
    return str(raw) if raw is not None else "0"


def _parse_match_datetime(value: str | None) -> datetime | None:
    """Parse match datetime and normalize to timezone-aware UTC."""
    if not value:
        return None

    candidates = [value]
    if value.endswith("+00:00Z"):
        candidates.append(value.removesuffix("Z"))

    dt = None
    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            break
        except ValueError:
            continue

    if dt is None:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _fetch(session: aiohttp.ClientSession, url: str) -> dict | None:
    headers = {"User-Agent": "WhitecapsBot/1.0 (+https://discord.com)"}
    last_error = None
    for _ in range(2):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=12), headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    log.debug("GET %s -> 200", url)
                    return data
                last_error = f"HTTP {resp.status}"
                log.warning("GET %s -> HTTP %s", url, resp.status)
        except aiohttp.ClientError as e:
            last_error = str(e)
            log.warning("Network error fetching %s: %s", url, e)
        except Exception as e:
            last_error = str(e)
            log.warning("Unexpected error fetching %s: %s", url, e)
    log.warning("GET %s failed after retries: %s", url, last_error)
    return None



def _parse_the_sports_db_event(event: dict) -> dict | None:
    event_id = event.get("idEvent")
    if not event_id:
        return None

    home_name = event.get("strHomeTeam", "Home")
    away_name = event.get("strAwayTeam", "Away")
    home_score_raw = event.get("intHomeScore")
    away_score_raw = event.get("intAwayScore")

    home_score = "0" if home_score_raw in (None, "") else str(home_score_raw)
    away_score = "0" if away_score_raw in (None, "") else str(away_score_raw)

    state = "pre"
    detail = event.get("strStatus") or "Scheduled"
    if home_score_raw not in (None, "") and away_score_raw not in (None, ""):
        state = "post"
        detail = "Final"

    dt = event.get("strTimestamp")
    if not dt:
        date = event.get("dateEvent")
        tm = event.get("strTime") or "00:00:00"
        dt = f"{date}T{tm}Z" if date else ""

    home_is_wc = "whitecaps" in home_name.lower()
    away_is_wc = "whitecaps" in away_name.lower()

    return {
        "id": str(event_id),
        "name": event.get("strEvent") or f"{away_name} at {home_name}",
        "date": dt,
        "venue": event.get("strVenue") or "",
        "home": {
            "id": event.get("idHomeTeam"),
            "name": home_name,
            "abbreviation": home_name.split()[-1][:3].upper() if home_name else "HOM",
            "logo": event.get("strHomeTeamBadge") or "",
            "score": home_score,
            "home_away": "home",
            "winner": _to_float(home_score) > _to_float(away_score),
        },
        "away": {
            "id": event.get("idAwayTeam"),
            "name": away_name,
            "abbreviation": away_name.split()[-1][:3].upper() if away_name else "AWY",
            "logo": event.get("strAwayTeamBadge") or "",
            "score": away_score,
            "home_away": "away",
            "winner": _to_float(away_score) > _to_float(home_score),
        },
        "status": {
            "state": state,
            "detail": detail,
            "description": detail,
            "clock": "0'",
            "period": 0,
        },
        "is_whitecaps_home": home_is_wc or not away_is_wc,
    }


async def _fallback_schedule_from_the_sports_db(session: aiohttp.ClientSession) -> list[dict]:
    urls = (
        f"{THESPORTSDB_BASE_URL}/eventslast.php?id={THESPORTSDB_WHITECAPS_ID}",
        f"{THESPORTSDB_BASE_URL}/eventsnext.php?id={THESPORTSDB_WHITECAPS_ID}",
    )
    matches_by_id: dict[str, dict] = {}
    for url in urls:
        data = await _fetch(session, url)
        if not data:
            continue
        for event in data.get("results") or data.get("events") or []:
            parsed = _parse_the_sports_db_event(event)
            if parsed and parsed.get("id"):
                matches_by_id[str(parsed["id"])] = parsed

    matches = list(matches_by_id.values())
    matches.sort(key=lambda m: m.get("date", ""))
    if matches:
        log.info("TheSportsDB fallback schedule yielded %d matches", len(matches))
    return matches

def _is_whitecaps(competitor: dict) -> bool:
    name = competitor.get("team", {}).get("displayName", "")
    team_id = competitor.get("team", {}).get("id", "")
    return name in WHITECAPS_NAMES or str(team_id) == WHITECAPS_ID


def _parse_competitor(comp: dict) -> dict:
    team = comp.get("team", {})
    logo = team.get("logo") or (team.get("logos") or [{}])[0].get("href", "")
    # winner can be a bool or nested in the score dict
    raw_score = comp.get("score")
    winner = comp.get("winner", False)
    if isinstance(raw_score, dict) and not isinstance(winner, bool):
        winner = raw_score.get("winner", False)
    return {
        "id": team.get("id"),
        "name": team.get("displayName", "Unknown"),
        "abbreviation": team.get("abbreviation", "???"),
        "logo": logo,
        "score": _parse_score(raw_score),
        "home_away": comp.get("homeAway", ""),
        "winner": winner,
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
    matches_by_id: dict[str, dict] = {}

    for url in _scoreboard_urls():
        data = await _fetch(session, url)
        if not data:
            continue

        for event in data.get("events", []):
            for comp in event.get("competitions", []):
                for c in comp.get("competitors", []):
                    if _is_whitecaps(c):
                        parsed = _parse_match(event)
                        if parsed and parsed.get("id"):
                            matches_by_id[str(parsed["id"])] = parsed
                        break

    matches = list(matches_by_id.values())
    matches.sort(key=lambda m: m.get("date", ""))
    if matches:
        _write_cache_section("scoreboard", matches)
        return matches

    cached = _read_cache_section("scoreboard")
    return cached if isinstance(cached, list) else []
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
    commentary_events = []
    for item in data.get("commentary", []):
        text = item.get("text", "")
        time = item.get("time", {}).get("displayValue", "")
        details.append({"time": time, "text": text})

        etype = _infer_commentary_event_type(text)
        if not etype:
            continue

        names = _extract_names_from_commentary(text)
        commentary_events.append({
            "type": etype,
            "clock": time,
            "period": item.get("period", {}).get("number", 0),
            "text": text,
            "team": "",
            "team_abbr": "",
            "participants": [{"name": n, "id": "", "type": ""} for n in names],
        })
    formations = {}
    for roster in data.get("rosters", []):
        team_name = roster.get("team", {}).get("displayName", "")
        formation = roster.get("formation", "")
        if formation:
            formations[team_name] = formation
    # Merge commentary-derived events as a fallback so we can still surface
    # substitutions/goals when ESPN's keyEvents feed is sparse.
    for ev in commentary_events:
        if not any(
            existing.get("type") == ev.get("type")
            and existing.get("clock") == ev.get("clock")
            and existing.get("text") == ev.get("text")
            for existing in key_events
        ):
            key_events.append(ev)

    return {"key_events": key_events, "rosters": rosters, "commentary": details, "formations": formations}


def _schedule_urls() -> list[str]:
    """Build schedule URLs across nearby seasons to capture full current calendar."""
    year = datetime.now(timezone.utc).year
    urls = [
        f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year - 1}",
        f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year}",
        f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year + 1}",
        f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule",
    ]
    return list(dict.fromkeys(urls))


async def get_schedule(session: aiohttp.ClientSession) -> list[dict]:
    """Get Whitecaps schedule by merging ESPN seasons with TheSportsDB fallback."""
    matches_by_id: dict[str, dict] = {}

    for url in _schedule_urls():
        data = await _fetch(session, url)
        if not data:
            continue

        events = data.get("events", [])
        log.info("Schedule url=%s events=%d", url, len(events))

        for event in events:
            try:
                parsed = _parse_match(event)
            except Exception as exc:
                log.warning("Skipping malformed schedule event id=%s: %s", event.get("id"), exc)
                continue
            if parsed and parsed.get("id"):
                matches_by_id[str(parsed["id"])] = parsed

    espn_count = len(matches_by_id)
    fallback = await _fallback_schedule_from_the_sports_db(session)
    for match in fallback:
        match_id = str(match.get("id", ""))
        if match_id and match_id not in matches_by_id:
            matches_by_id[match_id] = match

    sportsdb_added = len(matches_by_id) - espn_count

    matches = list(matches_by_id.values())
    matches.sort(key=lambda m: m.get("date", ""))
    log.info(
        "get_schedule: %d merged matches (espn=%d, sportsdb=%d)",
        len(matches),
        espn_count,
        sportsdb_added,
    )
    if matches:
        _write_cache_section("schedule", matches)
        return matches

    cached = _read_cache_section("schedule")
    return cached if isinstance(cached, list) else []


async def get_standings(session: aiohttp.ClientSession) -> dict | None:
    """Get MLS standings via /apis/v2/ endpoint."""
    data = await _fetch(session, STANDINGS_URL)
    if not data:
        cached = _read_cache_section("standings")
        return cached if isinstance(cached, dict) else None

    children = data.get("children") or data.get("groups") or []
    if not children:
        cached = _read_cache_section("standings")
        return cached if isinstance(cached, dict) else None
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
        entries.sort(
            key=lambda e: (
                -_to_float(e.get("stats", {}).get("points"), default=-1),
                -_to_float(e.get("stats", {}).get("pointsPerGame"), default=-1),
                -_to_float(e.get("stats", {}).get("wins"), default=-1),
                e.get("name", ""),
            )
        )
        if entries:
            standings[conf_name] = entries
    if standings:
        log.info("get_standings: %d conference(s)", len(standings))
        _write_cache_section("standings", standings)
        return standings

    cached = _read_cache_section("standings")
    return cached if isinstance(cached, dict) else None


async def get_next_match(session: aiohttp.ClientSession) -> dict | None:
    schedule = await get_schedule(session)
    now = datetime.now(timezone.utc)
    upcoming: list[tuple[datetime, dict]] = []

    for m in schedule:
        try:
            state = m.get("status", {}).get("state", "pre")
            if state == "in":
                return m

            match_date = _parse_match_datetime(m.get("date"))
            if match_date and match_date >= now and state in ("pre", "in", "post"):
                upcoming.append((match_date, m))
        except (KeyError, AttributeError):
            continue

    if upcoming:
        upcoming.sort(key=lambda pair: pair[0])
        return upcoming[0][1]

    scoreboard = await get_scoreboard(session)
    for m in scoreboard:
        if m.get("status", {}).get("state") in ("pre", "in"):
            return m
    return None


async def debug_endpoints(session: aiohttp.ClientSession) -> dict:
    year = datetime.now(timezone.utc).year
    urls = {
        "scoreboard": f"{BASE_URL}/scoreboard",
        f"schedule season={year - 1}": f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year - 1}",
        f"schedule season={year} [primary]": f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year}",
        f"schedule season={year + 1}": f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule?season={year + 1}",
        "schedule default": f"{BASE_URL}/teams/{WHITECAPS_ID}/schedule",
        "TheSportsDB last": f"{THESPORTSDB_BASE_URL}/eventslast.php?id={THESPORTSDB_WHITECAPS_ID}",
        "TheSportsDB next": f"{THESPORTSDB_BASE_URL}/eventsnext.php?id={THESPORTSDB_WHITECAPS_ID}",
        "standings v2": STANDINGS_URL,
    }
    results = {}
    for label, url in urls.items():
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "WhitecapsBot/1.0 (+https://discord.com)"},
            ) as resp:
                status = resp.status
                if status == 200:
                    data = await resp.json(content_type=None)
                    keys = list(data.keys()) if isinstance(data, dict) else str(type(data))
                    counts = {
                        k: len(data[k])
                        for k in ("events", "children", "results")
                        if k in data and isinstance(data[k], list)
                    }
                    has_items = any(counts.get(k, 0) > 0 for k in ("events", "results", "children"))
                    state = "OK" if has_items else "EMPTY"
                    results[label] = f"200 {state} | keys: {keys} | counts: {counts}"
                else:
                    body = await resp.text()
                    results[label] = f"HTTP {status} | {body[:120]}"
        except Exception as e:
            results[label] = f"ERROR: {e}"
    return results
