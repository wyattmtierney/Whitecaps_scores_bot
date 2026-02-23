"""Discord embed builders for Whitecaps bot."""

from datetime import datetime, timezone
import discord

WHITECAPS_BLUE = 0x002F6C
WHITECAPS_TEAL = 0x009CDE
WIN_GREEN = 0x2ECC71
LOSS_RED = 0xE74C3C
DRAW_GRAY = 0x95A5A6

GOAL_EMOJI = "⚽"
CARD_YELLOW = "🟨"
CARD_RED = "🟥"
SUB_EMOJI = "🔄"
CLOCK_EMOJI = "⏱️"
LIVE_EMOJI = "🔴"
CALENDAR_EMOJI = "📅"
TROPHY_EMOJI = "🏆"
FLAG_CANADA = "🇨🇦"

STATUS_EMOJI = {
    "pre": "📋",
    "in": LIVE_EMOJI,
    "post": "✅",
}

_FIELD_LIMIT = 1024


def _parse_match_datetime(value: str | None) -> datetime | None:
    """Parse ISO-like dates from providers and normalize to UTC."""
    if not value:
        return None

    candidates = [value]
    # Some providers include both offset and trailing Z; normalize that case.
    if value.endswith("+00:00Z"):
        candidates.append(value.removesuffix("Z"))

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue

        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return None


def _safe_field(value: str) -> str:
    """Truncate a field value to Discord's 1024-char limit."""
    if len(value) <= _FIELD_LIMIT:
        return value
    return value[:_FIELD_LIMIT - 3] + "..."


def _score_line(home: dict, away: dict) -> str:
    return f"**{home['name']}** {home['score']} - {away['score']} **{away['name']}**"


def _short_score_line(home: dict, away: dict) -> str:
    return f"{home['abbreviation']} {home['score']} - {away['score']} {away['abbreviation']}"


def _outcome_color(match: dict) -> int:
    home = match["home"]
    away = match["away"]
    status = match["status"]["state"]
    if status != "post":
        return WHITECAPS_BLUE if status == "pre" else WHITECAPS_TEAL
    wc_comp = home if match["is_whitecaps_home"] else away
    if wc_comp.get("winner"):
        return WIN_GREEN
    opp = away if match["is_whitecaps_home"] else home
    if opp.get("winner"):
        return LOSS_RED
    return DRAW_GRAY


def build_match_embed(match: dict, key_events: list[dict] | None = None) -> discord.Embed:
    """Build a rich embed for a match (pre/live/post)."""
    state = match["status"]["state"]
    home = match["home"]
    away = match["away"]
    status_emoji = STATUS_EMOJI.get(state, "📋")
    color = _outcome_color(match)
    if state == "pre":
        try:
            match_dt = _parse_match_datetime(match.get("date"))
            if not match_dt:
                raise ValueError("invalid match date")
            ts = int(match_dt.timestamp())
            title = f"{status_emoji} Upcoming: {home['abbreviation']} vs {away['abbreviation']}"
            description = f"{home['name']} vs {away['name']}\n{CALENDAR_EMOJI} <t:{ts}:F> (<t:{ts}:R>)"
        except (ValueError, KeyError):
            title = f"{status_emoji} Upcoming Match"
            description = f"{home['name']} vs {away['name']}"
    elif state == "in":
        clock = match["status"]["clock"]
        period = match["status"].get("period", 1)
        half = "1st Half" if period == 1 else "2nd Half" if period == 2 else f"ET P{period}"
        title = f"{LIVE_EMOJI} LIVE — {_short_score_line(home, away)}"
        description = f"{CLOCK_EMOJI} {clock} ({half})\n{home['name']} vs {away['name']}"
    else:
        detail = match["status"].get("detail", "Full Time")
        title = f"{status_emoji} Final — {_short_score_line(home, away)}"
        description = f"{home['name']} vs {away['name']}\n_{detail}_"
    embed = discord.Embed(title=title, description=description, color=color)
    if state != "pre":
        embed.add_field(
            name="Score",
            value=f"**{home['name']}** `{home['score']}` — `{away['score']}` **{away['name']}**",
            inline=False,
        )
    venue = match.get("venue")
    if venue:
        embed.add_field(name="Venue", value=venue, inline=True)
    if key_events:
        event_lines = []
        for ev in key_events[:10]:
            etype = ev.get("type", "").lower()
            clock = ev.get("clock", "")
            team_abbr = ev.get("team_abbr", "")
            participants = ev.get("participants", [])
            player_name = participants[0]["name"] if participants else ev.get("text", "")
            if "goal" in etype or "score" in etype:
                emoji = GOAL_EMOJI
            elif "yellow" in etype:
                emoji = CARD_YELLOW
            elif "red" in etype:
                emoji = CARD_RED
            elif "substitut" in etype:
                emoji = SUB_EMOJI
            else:
                emoji = "•"
            event_lines.append(f"{emoji} `{clock}` **{team_abbr}** — {player_name}")
        if event_lines:
            embed.add_field(name="Key Events", value=_safe_field("\n".join(event_lines)), inline=False)
    embed.set_footer(text=f"{FLAG_CANADA} Vancouver Whitecaps FC • Data: ESPN")
    embed.timestamp = datetime.now(timezone.utc)
    if home.get("logo"):
        embed.set_thumbnail(url=home["logo"])
    return embed


def build_schedule_embed(matches: list[dict], max_matches: int = 8) -> discord.Embed:
    """Build an embed showing the upcoming/recent schedule."""
    embed = discord.Embed(
        title=f"{CALENDAR_EMOJI} {FLAG_CANADA} Whitecaps Schedule",
        color=WHITECAPS_BLUE,
    )
    now = datetime.now(timezone.utc)
    upcoming = []
    recent = []
    for m in matches:
        try:
            match_dt = _parse_match_datetime(m.get("date"))
            if not match_dt:
                continue
            if match_dt >= now or m["status"]["state"] in ("in", "pre"):
                upcoming.append((match_dt, m))
            else:
                recent.append((match_dt, m))
        except KeyError:
            continue
    upcoming.sort(key=lambda x: x[0])
    recent.sort(key=lambda x: x[0], reverse=True)
    def _match_line(dt: datetime, m: dict) -> str:
        state = m["status"]["state"]
        home = m["home"]
        away = m["away"]
        opp = away if m["is_whitecaps_home"] else home
        opp_abbr = opp.get("abbreviation", opp["name"][:6])
        h_or_a = "🏠" if m["is_whitecaps_home"] else "✈️"
        if state == "in":
            clock = m["status"]["clock"]
            return f"{LIVE_EMOJI} {h_or_a} vs **{opp_abbr}** {home['score']}-{away['score']} `{clock}`"
        elif state == "post":
            wc = home if m["is_whitecaps_home"] else away
            opp_side = away if m["is_whitecaps_home"] else home
            if wc.get("winner"):
                result_icon = "🟢"
            elif opp_side.get("winner"):
                result_icon = "🔴"
            else:
                result_icon = "⚪"
            score = f"{home['score']}-{away['score']}"
            return f"{result_icon} {h_or_a} vs **{opp_abbr}** {score}"
        else:
            ts = int(dt.timestamp())
            return f"📋 {h_or_a} vs **{opp_abbr}** — <t:{ts}:d> <t:{ts}:t>"
    if upcoming:
        lines = [_match_line(dt, m) for dt, m in upcoming[:max_matches]]
        embed.add_field(name=f"Upcoming ({len(upcoming)} total)", value=_safe_field("\n".join(lines)), inline=False)
    if recent:
        recent_limit = max_matches if not upcoming else max_matches // 2
        lines = [_match_line(dt, m) for dt, m in recent[:recent_limit]]
        embed.add_field(name="Recent Results", value=_safe_field("\n".join(lines)), inline=False)
    embed.set_footer(text=f"{FLAG_CANADA} Vancouver Whitecaps FC • Data: ESPN")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def build_standings_embed(standings: dict) -> discord.Embed:
    """Build an embed showing MLS standings with Whitecaps highlighted."""
    embed = discord.Embed(
        title=f"{TROPHY_EMOJI} MLS Standings",
        color=WHITECAPS_BLUE,
    )
    for conf_name, entries in standings.items():
        if not entries:
            continue
        header = f"`{'Pos':>3} {'Team':<10} {'GP':>2} {'W':>2} {'L':>2} {'D':>2} {'Pts':>3} {'PPG':>4}`"
        rows = [header]
        for i, entry in enumerate(entries[:12], start=1):
            name = entry["abbreviation"] or entry["name"][:10]
            stats = entry.get("stats", {})
            def s(k: str) -> str:
                v = stats.get(k, "-")
                return str(v) if v != "-" else "-"
            line = (
                f"`{'*' if entry['is_whitecaps'] else ' ':>1}{i:>2}. "
                f"{name:<10} "
                f"{s('gamesPlayed'):>2} "
                f"{s('wins'):>2} "
                f"{s('losses'):>2} "
                f"{s('ties'):>2} "
                f"{s('points'):>3} "
                f"{s('pointsPerGame'):>4}`"
            )
            if entry["is_whitecaps"]:
                line = f"**{line}** {FLAG_CANADA}"
            rows.append(line)
        embed.add_field(name=conf_name, value=_safe_field("\n".join(rows)), inline=False)
    embed.set_footer(text=f"{FLAG_CANADA} Vancouver Whitecaps FC • Data: ESPN • * = Whitecaps")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def build_goal_alert_embed(match: dict, event: dict) -> discord.Embed:
    """Build a goal alert embed for a live match."""
    home = match["home"]
    away = match["away"]
    participants = event.get("participants", [])
    scorer = participants[0]["name"] if participants else "Unknown"
    assister = participants[1]["name"] if len(participants) > 1 else None
    clock = event.get("clock", "")
    team = event.get("team", "")
    is_wc_goal = "Whitecaps" in team or "Vancouver" in team
    color = WIN_GREEN if is_wc_goal else LOSS_RED
    title = f"{GOAL_EMOJI} GOAL! — {_short_score_line(home, away)}"
    desc_lines = [f"**{scorer}** scores for **{team}**!"]
    if assister:
        desc_lines.append(f"Assist: {assister}")
    desc_lines.append(f"{CLOCK_EMOJI} {clock}")
    embed = discord.Embed(title=title, description="\n".join(desc_lines), color=color)
    embed.set_footer(text=f"{FLAG_CANADA} Vancouver Whitecaps FC • Data: ESPN")
    embed.timestamp = datetime.now(timezone.utc)
    return embed
