from __future__ import annotations

from zoneinfo import ZoneInfo

import discord

from whitecaps_bot.apifootball import MatchState

PST = ZoneInfo("America/Vancouver")


def _abbrev(name: str) -> str:
    """Return a short team abbreviation from the team name."""
    words = [w for w in name.split() if w.lower() not in ("fc", "sc", "cf", "the")]
    if len(words) >= 2:
        return "".join(w[0] for w in words[-2:]).upper()
    return name[:3].upper()


def _fmt_kickoff(starts_at) -> str:
    """Format a kickoff datetime in PST as a human-friendly string."""
    local = starts_at.astimezone(PST)
    day = str(local.day)
    day_name = local.strftime("%A")
    month = local.strftime("%B")
    year = local.strftime("%Y")
    time_str = local.strftime("%H:%M")
    return f"{day_name}, {month} {day}, {year} at {time_str} PST"


class MatchTracker:
    def __init__(self):
        self.current_fixture_id: int | None = None
        self.match_thread_id: int | None = None
        self.last_score: tuple[int | None, int | None] | None = None
        self.posted_sub_keys: set[str] = set()

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

        if match.home_name.lower() == "vancouver whitecaps":
            return f"{match.away_name} @ Vancouver Whitecaps - {date_text}"
        return f"Vancouver Whitecaps @ {match.home_name} - {date_text}"

    @staticmethod
    def build_prematch_embed(match: MatchState) -> discord.Embed:
        home_abbr = _abbrev(match.home_name)
        away_abbr = _abbrev(match.away_name)

        embed = discord.Embed(
            title=f"📅 Upcoming: {home_abbr} vs {away_abbr}",
            color=0x002F6C,  # Whitecaps navy blue
        )
        embed.description = f"{match.home_name} vs {match.away_name}"

        if match.starts_at:
            kickoff_str = _fmt_kickoff(match.starts_at)
            embed.add_field(name="📅 Kickoff", value=kickoff_str, inline=False)

        if getattr(match, "venue", None):
            embed.add_field(name="Venue", value=match.venue, inline=False)

        return embed

    @staticmethod
    def build_score_embed(match: MatchState) -> discord.Embed:
        minute = f"{match.elapsed}'" if match.elapsed is not None else "-"
        embed = discord.Embed(title="⚽ Live Score Update", color=discord.Color.green())
        embed.description = f"**{match.home_name} {match.home_goals} - {match.away_goals} {match.away_name}**"
        embed.add_field(name="Minute", value=minute)
        embed.add_field(name="Status", value=match.long_status or match.short_status)
        return embed

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

        if forum_channel_id:
            forum_channel = bot.get_channel(forum_channel_id)
            if isinstance(forum_channel, discord.ForumChannel):
                created = await forum_channel.create_thread(
                    name=self.build_thread_title(match),
                    content="Match day! 🇨🇦 Let's get it started — drop your predictions below!",
                    embed=self.build_prematch_embed(match),
                )
                thread = getattr(created, "thread", None) or created
                self.match_thread_id = thread.id
                return thread

        if fallback_channel_id is None:
            raise RuntimeError("Neither FORUM_CHANNEL_ID nor CHANNEL_ID is configured.")

        fallback_channel = bot.get_channel(fallback_channel_id)
        if fallback_channel is None:
            raise RuntimeError(f"Fallback channel {fallback_channel_id} not found.")

        if isinstance(fallback_channel, discord.TextChannel):
            await fallback_channel.send(
                "Match day! 🇨🇦 Let's get it started — drop your predictions below!",
                embed=self.build_prematch_embed(match),
            )
            self.match_thread_id = fallback_channel.id
            return fallback_channel
