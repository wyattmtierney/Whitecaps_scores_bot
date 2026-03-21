from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv

from whitecaps_bot.apifootball import MatchState, with_retry
from whitecaps_bot.config import Settings
from whitecaps_bot.provider import ScoreProvider
from whitecaps_bot.tracker import MatchTracker


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("whitecaps_bot")


class WhitecapsBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=settings.command_prefix, intents=intents, help_command=None)

        self.settings = settings
        self.api = ScoreProvider(
            settings.api_football_key,
            settings.espn_team_id,
            settings.espn_team_name,
        )
        self.tracker = MatchTracker()
        self.update_task: asyncio.Task | None = None
        self.target_channel_id: int | None = settings.channel_id

    async def setup_hook(self) -> None:
        @self.hybrid_command(name="live", description="Start live Whitecaps match updates in this channel")
        async def cmd_live(ctx: commands.Context):
            self.target_channel_id = ctx.channel.id
            if self.update_task and not self.update_task.done():
                await ctx.send("Already tracking live updates.")
                return

            self.update_task = asyncio.create_task(self._live_update_loop())
            await ctx.send("Started live Whitecaps updates (scores, cards & substitutions).")

        @self.hybrid_command(name="stop", description="Stop live Whitecaps match updates")
        async def cmd_stop(ctx: commands.Context):
            if self.update_task and not self.update_task.done():
                self.update_task.cancel()
                self.update_task = None
            await ctx.send("Stopped live Whitecaps updates.")

        @self.hybrid_command(name="status", description="Show current Whitecaps match status")
        async def cmd_status(ctx: commands.Context):
            match = await with_retry(lambda: self.api.get_current_or_next_whitecaps_fixture(self.settings.whitecaps_team_id))
            if not match:
                await ctx.send("No Whitecaps fixture available right now.")
                return
            await ctx.send(self._score_line(match))

        @self.hybrid_command(name="upcoming", description="Show upcoming Whitecaps matches")
        async def cmd_upcoming(ctx: commands.Context):
            await ctx.defer()
            try:
                matches = await with_retry(lambda: self.api.get_upcoming_fixtures())
            except RuntimeError:
                logger.exception("Failed to fetch upcoming fixtures")
                await ctx.send("Could not fetch upcoming matches. Try again later.")
                return
            if not matches:
                await ctx.send("No upcoming Whitecaps matches found.")
                return
            await ctx.send(embed=self.tracker.build_upcoming_embed(matches))

        @self.hybrid_command(name="standings", description="Show MLS standings")
        async def cmd_standings(ctx: commands.Context):
            await ctx.defer()
            try:
                entries = await with_retry(lambda: self.api.get_standings())
            except RuntimeError:
                logger.exception("Failed to fetch MLS standings")
                await ctx.send("Could not fetch MLS standings. Try again later.")
                return
            if not entries:
                await ctx.send("MLS standings not available right now.")
                return
            await ctx.send(embed=self.tracker.build_standings_embed(entries))

        @self.hybrid_command(name="help", description="Show available bot commands")
        async def cmd_help(ctx: commands.Context):
            await ctx.send(embed=self.tracker.build_help_embed(self.settings.command_prefix))

        # Sync slash commands to Discord
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

        if self.settings.channel_id or self.settings.forum_channel_id:
            self.update_task = asyncio.create_task(self._live_update_loop())

    @staticmethod
    def _score_line(match: MatchState) -> str:
        minute = f"{match.elapsed}'" if match.elapsed is not None else "-"
        return f"\u26bd **{match.home_name} {match.home_goals} - {match.away_goals} {match.away_name}** ({minute}, {match.long_status})"

    async def _live_update_loop(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await self._update_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Live update loop failed; continuing")

            await asyncio.sleep(self.settings.poll_interval_seconds)

    async def _update_once(self) -> None:
        match = await with_retry(lambda: self.api.get_current_or_next_whitecaps_fixture(self.settings.whitecaps_team_id))
        if not match:
            return

        fixture_changed = self.tracker.current_fixture_id != match.fixture_id

        if fixture_changed:
            logger.info(
                "Fixture changed: %s → %s (%s vs %s, state=%s)",
                self.tracker.current_fixture_id, match.fixture_id,
                match.home_name, match.away_name, match.state,
            )
            self.tracker.reset_for_new_fixture(match.fixture_id)

        # Create a match thread when the kickoff window opens.
        # Skip the check entirely once a thread is already established for this fixture.
        if self.tracker.match_thread_id is None and self.tracker.should_create_thread(match):
            destination = await self.tracker.ensure_match_thread(
                self,
                match,
                forum_channel_id=self.settings.forum_channel_id,
                fallback_channel_id=self.target_channel_id,
            )
            await destination.send("\U0001f514 Match thread is live. Updates will be posted here.")

        if self.tracker.match_thread_id is None:
            return

        destination = self.get_channel(self.tracker.match_thread_id)
        if destination is None:
            # Cache miss — the thread was likely created hours ago and evicted
            # from Discord.py's internal cache.  Fall back to an API fetch.
            try:
                destination = await self.fetch_channel(self.tracker.match_thread_id)
                logger.info(
                    "Thread %s recovered via fetch_channel (was missing from cache)",
                    self.tracker.match_thread_id,
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Match thread %s is unreachable; skipping update",
                    self.tracker.match_thread_id,
                )
                return

        # If the thread was auto-archived (e.g. created far before kickoff),
        # unarchive it now so subsequent sends don't require MANAGE_THREADS.
        if isinstance(destination, discord.Thread) and destination.archived:
            try:
                await destination.edit(archived=False)
                logger.info("Unarchived match thread %s", self.tracker.match_thread_id)
            except discord.HTTPException:
                logger.warning(
                    "Could not unarchive thread %s; posts may fail",
                    self.tracker.match_thread_id,
                )

        # Track score changes and state transitions
        score = (match.home_goals, match.away_goals)
        prev_score = self.tracker.last_score
        prev_state = self.tracker.last_state
        score_changed = match.state == "in" and score != prev_score
        # Kickoff: state transitioned to "in" (regardless of score value from API)
        is_kickoff = match.state == "in" and prev_state != "in"
        total = (score[0] or 0) + (score[1] or 0)
        prev_total = ((prev_score[0] or 0) + (prev_score[1] or 0)) if prev_score else 0
        score_increased = score_changed and total > prev_total

        self.tracker.last_state = match.state

        if score_changed:
            self.tracker.last_score = score

        if is_kickoff:
            await destination.send(embed=self.tracker.build_kickoff_embed(match))

        # Key events — goals, cards, subs, penalties, VAR, etc.
        goal_from_events = False
        if match.state == "in":
            try:
                events = await with_retry(lambda: self.api.get_key_events(match.fixture_id))
                for event in events:
                    if event.dedupe_key in self.tracker.posted_event_keys:
                        # Already posted — but still counts as "covered" for
                        # the fallback check so we don't double-post.
                        if event.event_type in ("goal", "penalty_goal", "own_goal"):
                            goal_from_events = True
                        continue
                    self.tracker.posted_event_keys.add(event.dedupe_key)
                    if event.event_type in ("goal", "penalty_goal", "own_goal"):
                        goal_from_events = True
                    await destination.send(embed=self.tracker.build_key_event_embed(event, match))
            except RuntimeError:
                logger.warning("Key events fetch failed for fixture %s", match.fixture_id)

        # Fallback: score increased but key events didn't report a goal —
        # post a generic GOOOAL so goals are never silently missed.
        if score_increased and not goal_from_events:
            await destination.send(embed=self.tracker.build_score_embed(match))

        # Periodic score update every 15 minutes during live play so users
        # see the bot is alive even in a scoreless match.
        if match.state == "in" and not match.is_halftime:
            now = datetime.now(timezone.utc)
            last_post = self.tracker.last_score_post_time
            if last_post is None or (now - last_post) >= timedelta(minutes=15):
                self.tracker.last_score_post_time = now
                await destination.send(embed=self.tracker.build_score_embed(match))

        # Half-time alert
        if match.is_halftime and not self.tracker.halftime_posted:
            self.tracker.halftime_posted = True
            await destination.send(embed=self.tracker.build_halftime_embed(match))

        # Full-time alert (only once)
        if match.state == "post" and not self.tracker.fulltime_posted:
            self.tracker.fulltime_posted = True
            await destination.send(embed=self.tracker.build_final_embed(match))


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    bot = WhitecapsBot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
