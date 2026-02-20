"""
Vancouver Whitecaps FC Discord Bot
====================================
Commands (prefix: !)
  !score      — Today's match status / score
  !next       — Next upcoming Whitecaps match
  !schedule   — Full season schedule (up to 8 matches)
  !standings  — MLS standings (Western Conference highlighted)

The bot also runs a background tracker that auto-posts live updates and
goal alerts to the configured CHANNEL_ID.
"""

import asyncio
import logging
import os
import sys

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

import espn_api
from embeds import build_match_embed, build_schedule_embed, build_standings_embed
from tracker import MatchTracker

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
FORUM_CHANNEL_ID = int(os.getenv("FORUM_CHANNEL_ID", "0"))
PREFIX = os.getenv("COMMAND_PREFIX", "!")

if not TOKEN:
    log.error("DISCORD_TOKEN is not set. Please add it to your .env file.")
    sys.exit(1)

if CHANNEL_ID == 0:
    log.warning("CHANNEL_ID is not set — live updates will be disabled.")

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
tracker: MatchTracker | None = None


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@bot.event
async def on_ready() -> None:
    global tracker
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)

    if CHANNEL_ID or FORUM_CHANNEL_ID:
        tracker = MatchTracker(
            bot,
            channel_id=CHANNEL_ID,
            forum_channel_id=FORUM_CHANNEL_ID or None,
        )
        tracker.start()
    else:
        log.warning("No CHANNEL_ID or FORUM_CHANNEL_ID set; skipping live match tracker.")


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument. Use `{PREFIX}help` for usage.")
        return
    log.exception("Unhandled command error: %s", error)
    await ctx.send("An unexpected error occurred. Please try again later.")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@bot.command(name="score", aliases=["s", "live"])
async def cmd_score(ctx: commands.Context) -> None:
    """Show today's Whitecaps match score / status."""
    async with ctx.typing():
        async with aiohttp.ClientSession() as session:
            matches = await espn_api.get_scoreboard(session)

    if not matches:
        await ctx.send("No Whitecaps match today. Try `!schedule` to see upcoming games.")
        return

    match = matches[0]
    state = match["status"]["state"]

    async with aiohttp.ClientSession() as session:
        summary = await espn_api.get_match_summary(session, match["id"]) if state != "pre" else None

    embed = build_match_embed(match, key_events=summary.get("key_events", []) if summary else None)
    await ctx.send(embed=embed)


@bot.command(name="next", aliases=["n", "upcoming"])
async def cmd_next(ctx: commands.Context) -> None:
    """Show the next upcoming Whitecaps match."""
    async with ctx.typing():
        async with aiohttp.ClientSession() as session:
            match = await espn_api.get_next_match(session)

    if not match:
        await ctx.send("No upcoming matches found.")
        return

    embed = build_match_embed(match)
    await ctx.send(embed=embed)


@bot.command(name="schedule", aliases=["sch", "fixtures"])
async def cmd_schedule(ctx: commands.Context) -> None:
    """Show the Whitecaps upcoming schedule."""
    async with ctx.typing():
        async with aiohttp.ClientSession() as session:
            matches = await espn_api.get_schedule(session)

    if not matches:
        await ctx.send("Could not retrieve schedule at this time.")
        return

    embed = build_schedule_embed(matches)
    await ctx.send(embed=embed)


@bot.command(name="standings", aliases=["table", "st"])
async def cmd_standings(ctx: commands.Context) -> None:
    """Show MLS standings."""
    async with ctx.typing():
        async with aiohttp.ClientSession() as session:
            standings = await espn_api.get_standings(session)

    if not standings:
        await ctx.send("Could not retrieve standings at this time.")
        return

    embed = build_standings_embed(standings)
    await ctx.send(embed=embed)


@bot.command(name="help", aliases=["h", "commands"])
async def cmd_help(ctx: commands.Context) -> None:
    """Show available commands."""
    embed = discord.Embed(
        title="🇨🇦 Whitecaps Bot — Commands",
        description="Track the Vancouver Whitecaps FC live!",
        color=0x002F6C,
    )
    embed.add_field(
        name=f"`{PREFIX}score` / `{PREFIX}live`",
        value="Today's match score and status.",
        inline=False,
    )
    embed.add_field(
        name=f"`{PREFIX}next` / `{PREFIX}upcoming`",
        value="Next upcoming Whitecaps match.",
        inline=False,
    )
    embed.add_field(
        name=f"`{PREFIX}schedule` / `{PREFIX}fixtures`",
        value="Season schedule with recent results.",
        inline=False,
    )
    embed.add_field(
        name=f"`{PREFIX}standings` / `{PREFIX}table`",
        value="Current MLS standings.",
        inline=False,
    )
    embed.set_footer(text="Data provided by ESPN • Vancouver Whitecaps FC")
    await ctx.send(embed=embed)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        bot.run(TOKEN, log_handler=None)
    except KeyboardInterrupt:
        log.info("Shutting down.")
    except discord.LoginFailure:
        log.error("Invalid DISCORD_TOKEN. Please check your .env file.")
        sys.exit(1)
    finally:
        if tracker:
            tracker.stop()


if __name__ == "__main__":
    main()
