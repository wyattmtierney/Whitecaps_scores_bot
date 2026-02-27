from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import discord

from whitecaps_bot.apifootball import CardEvent, MatchState, StandingsEntry, SubstitutionEvent

PST = ZoneInfo("America/Vancouver")
logger = logging.getLogger("whitecaps_bot.tracker")

# Only create a thread if the match is within this window of kickoff.
THREAD_CREATION_WINDOW = timedelta(hours=24)

WHITECAPS_BLUE = 0x002F6C
WHITECAPS_TEAL = 0x009CDE
WIN_GREEN = 0x2ECC71
LOSS_RED = 0xE74C3C
DRAW_GRAY = 0x95A5A6
YELLOW_CARD_COLOR = 0xFFCC00
RED_CARD_COLOR = 0xFF0000


def _abbrev(name: str) -> str:
    """Return a short team abbreviation from the team name."""
    words = [w for w in name.split() if w.lower() not in ("fc", "sc", "cf", "the")]
    if len(words) >= 2:
        return "".join(w[0] for w in words[-2:]).upper()
    return name[:3].upper()


def _is_whitecaps(name: str) -> bool:
    return "whitecaps" in name.lower() or "vancouver" in name.lower()


class MatchTracker:
    def __init__(self):
        self.current_fixture_id: int | None = None
        self.match_thread_id: int | None = None
        self.last_score: tuple[int | None, int | None] | None = None
        self.posted_sub_keys: set[str] = set()
        self.posted_card_keys: set[str] = set()
        self.halftime_posted: bool = False
        self.fulltime_posted: bool = False
        # Tracks fixture IDs that already have a forum thread (persists across resets)
        self._threads_created_for: set[int] = set()

    @staticmethod
    def build_thread_title(match: MatchState) -> str:
        if match.starts_at is None:
            date_text = "TBD"
        else:
            local_date = match.starts_at.astimezone(PST)
            month = local_date.strftime("%B")
            day = str(local_date.day)
            year = local_date.strftime("%Y")
            date_text = f"{month} {day}, {year}"

        if _is_whitecaps(match.home_name):
            return f"{match.away_name} @ Vancouver Whitecaps - {date_text}"
        return f"Vancouver Whitecaps @ {match.home_name} - {date_text}"

    @staticmethod
    def build_prematch_embed(match: MatchState) -> discord.Embed:
        """Build a match-day thread opening embed styled like official Whitecaps posts."""
        if _is_whitecaps(match.home_name):
            opp_name = match.away_name
            location = "HOME"
        else:
            opp_name = match.home_name
            location = "AWAY"

        embed = discord.Embed(
            title="\U0001f1e8\U0001f1e6  MATCH DAY",
            description=(
                f"**Vancouver Whitecaps FC**\n"
                f"VS\n"
                f"**{opp_name}**"
            ),
            color=WHITECAPS_BLUE,
        )

        if match.starts_at:
            ts = int(match.starts_at.timestamp())
            embed.add_field(
                name="\u23f0  Kickoff",
                value=f"<t:{ts}:F>\n<t:{ts}:R>",
                inline=True,
            )

        if match.venue:
            embed.add_field(name="\U0001f3df\ufe0f  Venue", value=match.venue, inline=True)

        embed.add_field(name="\U0001f4cd  Location", value=location, inline=True)

        if match.broadcasts:
            embed.add_field(
                name="\U0001f4fa  Broadcast",
                value=" / ".join(match.broadcasts),
                inline=False,
            )

        embed.add_field(
            name="\u200b",
            value="Drop your predictions and let's go! **#VWFC**",
            inline=False,
        )

        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    @staticmethod
    def build_score_embed(match: MatchState) -> discord.Embed:
        """Build a prominent goal alert embed."""
        minute = f"{match.elapsed}'" if match.elapsed is not None else "-"

        is_wc_home = _is_whitecaps(match.home_name)
        wc_goals = match.home_goals if is_wc_home else match.away_goals
        opp_goals = match.away_goals if is_wc_home else match.home_goals

        if wc_goals is not None and opp_goals is not None:
            color = WIN_GREEN if wc_goals > opp_goals else LOSS_RED if opp_goals > wc_goals else WHITECAPS_TEAL
        else:
            color = WHITECAPS_TEAL

        embed = discord.Embed(
            title="\u26bd\u26bd\u26bd GOOOAL!",
            color=color,
        )
        embed.description = (
            f"**{match.home_name}** `{match.home_goals}` \u2014 "
            f"`{match.away_goals}` **{match.away_name}**"
        )
        embed.add_field(name="Minute", value=minute, inline=True)
        embed.add_field(name="Status", value=match.long_status or match.short_status, inline=True)
        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    @staticmethod
    def build_sub_embed(sub: SubstitutionEvent) -> discord.Embed:
        """Build a substitution alert embed."""
        minute = f"{sub.elapsed}'" if sub.elapsed is not None else "?"
        embed = discord.Embed(
            title=f"\U0001f504 Substitution \u2014 {sub.team_name}",
            color=WHITECAPS_TEAL,
        )
        embed.description = (
            f"\U0001f7e2 **ON:** {sub.player_in}\n"
            f"\U0001f534 **OFF:** {sub.player_out}"
        )
        embed.add_field(name="\u23f1\ufe0f  Minute", value=minute, inline=True)
        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    @staticmethod
    def build_final_embed(match: MatchState) -> discord.Embed:
        """Build a full time embed."""
        is_wc_home = _is_whitecaps(match.home_name)
        wc_goals = match.home_goals if is_wc_home else match.away_goals
        opp_goals = match.away_goals if is_wc_home else match.home_goals
        if wc_goals is not None and opp_goals is not None:
            color = WIN_GREEN if wc_goals > opp_goals else LOSS_RED if opp_goals > wc_goals else DRAW_GRAY
        else:
            color = DRAW_GRAY
        embed = discord.Embed(
            title="\u2705 Full Time",
            description=(
                f"**{match.home_name}** `{match.home_goals}` \u2014 "
                f"`{match.away_goals}` **{match.away_name}**"
            ),
            color=color,
        )
        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    @staticmethod
    def build_card_embed(card: CardEvent) -> discord.Embed:
        """Build a yellow/red card alert embed."""
        minute = f"{card.elapsed}'" if card.elapsed is not None else "?"
        is_red = card.card_type == "Red Card"
        emoji = "\U0001f7e5" if is_red else "\U0001f7e8"
        color = RED_CARD_COLOR if is_red else YELLOW_CARD_COLOR

        embed = discord.Embed(
            title=f"{emoji} {card.card_type} \u2014 {card.team_name}",
            description=f"**{card.player_name}**",
            color=color,
        )
        embed.add_field(name="\u23f1\ufe0f  Minute", value=minute, inline=True)
        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    @staticmethod
    def build_halftime_embed(match: MatchState) -> discord.Embed:
        """Build a half-time score embed."""
        embed = discord.Embed(
            title="\u23f8\ufe0f Half Time",
            description=(
                f"**{match.home_name}** `{match.home_goals}` \u2014 "
                f"`{match.away_goals}` **{match.away_name}**"
            ),
            color=WHITECAPS_BLUE,
        )
        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    @staticmethod
    def build_upcoming_embed(matches: list[MatchState]) -> discord.Embed:
        """Build an upcoming schedule embed for the next few matches."""
        embed = discord.Embed(
            title="\U0001f4c5 Upcoming Whitecaps Matches",
            color=WHITECAPS_BLUE,
        )

        lines: list[str] = []
        for i, match in enumerate(matches[:5], 1):
            if _is_whitecaps(match.home_name):
                matchup = f"vs **{match.away_name}** (HOME)"
            else:
                matchup = f"@ **{match.home_name}** (AWAY)"

            parts = [f"**{i}.** {matchup}"]

            if match.starts_at:
                ts = int(match.starts_at.timestamp())
                parts.append(f"\u2003\u23f0 <t:{ts}:F> (<t:{ts}:R>)")

            if match.venue:
                parts.append(f"\u2003\U0001f3df\ufe0f {match.venue}")

            if match.broadcasts:
                parts.append(f"\u2003\U0001f4fa {' / '.join(match.broadcasts)}")

            lines.append("\n".join(parts))

        embed.description = "\n\n".join(lines) if lines else "No upcoming matches found."
        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    @staticmethod
    def build_standings_embed(entries: list[StandingsEntry]) -> discord.Embed:
        """Build a compact MLS standings table embed."""
        embed = discord.Embed(
            title="\U0001f3c6 MLS Standings",
            color=WHITECAPS_BLUE,
        )

        header = f"{'#':>2}  {'Team':<20s} {'GP':>2} {'W':>2} {'D':>2} {'L':>2} {'GD':>4} {'Pts':>3}"
        divider = "\u2500" * len(header)
        lines = [header, divider]

        for entry in entries:
            gd = f"+{entry.goal_difference}" if entry.goal_difference > 0 else str(entry.goal_difference)
            marker = "\u25b8" if _is_whitecaps(entry.team_name) else " "
            name = entry.team_name[:20]
            lines.append(
                f"{marker}{entry.rank:>2}  {name:<20s} {entry.played:>2} {entry.wins:>2} "
                f"{entry.draws:>2} {entry.losses:>2} {gd:>4} {entry.points:>3}"
            )

        embed.description = f"```\n{chr(10).join(lines)}\n```"
        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    @staticmethod
    def build_help_embed(prefix: str = "!") -> discord.Embed:
        """Build a help embed listing all available commands."""
        embed = discord.Embed(
            title="\U0001f1e8\U0001f1e6 Whitecaps Bot Commands",
            color=WHITECAPS_BLUE,
        )

        cmds = [
            (f"{prefix}live", "Start live Whitecaps match updates in this channel"),
            (f"{prefix}stop", "Stop live Whitecaps match updates"),
            (f"{prefix}status", "Show current Whitecaps match status"),
            (f"{prefix}upcoming", "Show upcoming Whitecaps matches"),
            (f"{prefix}standings", "Show MLS standings"),
            (f"{prefix}help", "Show this help message"),
        ]

        lines: list[str] = []
        for i, (cmd, desc) in enumerate(cmds, 1):
            parts = [f"**{i}.** \U0001f539 **{cmd}**"]
            parts.append(f"\u2003\U0001f4ac {desc}")
            lines.append("\n".join(parts))

        embed.description = "\n\n".join(lines)
        embed.set_footer(text="\U0001f1e8\U0001f1e6 Vancouver Whitecaps FC \u2022 Data: ESPN")
        embed.timestamp = datetime.now(timezone.utc)
        return embed

    def should_create_thread(self, match: MatchState) -> bool:
        """Check if we should create a thread for this match right now."""
        if match.fixture_id in self._threads_created_for:
            logger.info("Thread already created for fixture %s; skipping.", match.fixture_id)
            return False

        if match.state in ("in", "post"):
            return True

        if match.state == "pre" and match.starts_at:
            time_to_kickoff = match.starts_at - datetime.now(timezone.utc)
            if time_to_kickoff <= THREAD_CREATION_WINDOW:
                return True
            logger.info(
                "Match %s is %s away; outside thread creation window.",
                match.fixture_id, time_to_kickoff,
            )

        return False

    async def _find_existing_thread(
        self, forum: discord.ForumChannel, title: str
    ) -> discord.Thread | None:
        """Check if a thread with this title already exists in the forum."""
        try:
            for thread in forum.threads:
                if thread.name == title:
                    logger.info("Found existing thread '%s' (id=%s)", title, thread.id)
                    return thread
            async for thread in forum.archived_threads(limit=20):
                if thread.name == title:
                    logger.info("Found existing archived thread '%s' (id=%s)", title, thread.id)
                    return thread
        except discord.HTTPException as e:
            logger.warning("Failed to search for existing threads: %s", e)
        return None

    async def ensure_match_thread(
        self,
        bot: discord.Client,
        match: MatchState,
        forum_channel_id: int | None,
        fallback_channel_id: int | None,
    ) -> discord.abc.Messageable:
        if self.match_thread_id:
            thread = bot.get_channel(self.match_thread_id)
            if thread:
                return thread

        title = self.build_thread_title(match)

        if forum_channel_id:
            forum_channel = bot.get_channel(forum_channel_id)
            if isinstance(forum_channel, discord.ForumChannel):
                # Check for an existing thread before creating a new one
                existing = await self._find_existing_thread(forum_channel, title)
                if existing:
                    self.match_thread_id = existing.id
                    self._threads_created_for.add(match.fixture_id)
                    return existing

                embed = self.build_prematch_embed(match)
                created = await forum_channel.create_thread(
                    name=title,
                    embed=embed,
                )
                thread = getattr(created, "thread", None) or created
                self.match_thread_id = thread.id
                self._threads_created_for.add(match.fixture_id)
                logger.info("Created forum thread '%s' (id=%s)", title, thread.id)
                return thread

        if fallback_channel_id is None:
            raise RuntimeError("Neither FORUM_CHANNEL_ID nor CHANNEL_ID is configured.")

        fallback_channel = bot.get_channel(fallback_channel_id)
        if fallback_channel is None:
            raise RuntimeError(f"Fallback channel {fallback_channel_id} not found.")

        if isinstance(fallback_channel, discord.TextChannel):
            embed = self.build_prematch_embed(match)
            await fallback_channel.send(embed=embed)
            self.match_thread_id = fallback_channel.id
            self._threads_created_for.add(match.fixture_id)
            return fallback_channel
