from __future__ import annotations

import asyncio
import logging

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
        super().__init__(command_prefix=settings.command_prefix, intents=intents)

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
        @self.command(name="whitecapslive")
        async def whitecaps_live(ctx: commands.Context):
            self.target_channel_id = ctx.channel.id
            if self.update_task and not self.update_task.done():
                await ctx.send("Already tracking live updates.")
                return

            self.update_task = asyncio.create_task(self._live_update_loop())
            await ctx.send("Started live Whitecaps updates (scores + substitutions).")

        @self.command(name="whitecapsstop")
        async def whitecaps_stop(ctx: commands.Context):
            if self.update_task and not self.update_task.done():
                self.update_task.cancel()
                self.update_task = None
            await ctx.send("Stopped live Whitecaps updates.")

        @self.command(name="whitecapsstatus")
        async def whitecaps_status(ctx: commands.Context):
            match = await with_retry(lambda: self.api.get_current_or_next_whitecaps_fixture(self.settings.whitecaps_team_id))
            if not match:
                await ctx.send("No Whitecaps fixture available right now.")
                return
            await ctx.send(self._score_line(match))

        if self.settings.channel_id or self.settings.forum_channel_id:
            self.update_task = asyncio.create_task(self._live_update_loop())

    @staticmethod
    def _score_line(match: MatchState) -> str:
        minute = f"{match.elapsed}'" if match.elapsed is not None else "-"
        return f"⚽ **{match.home_name} {match.home_goals} - {match.away_goals} {match.away_name}** ({minute}, {match.long_status})"

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
        thread_required = match.state in {"pre", "in"}

        if fixture_changed:
            self.tracker.current_fixture_id = match.fixture_id
            self.tracker.last_score = None
            self.tracker.posted_sub_keys.clear()
            self.tracker.match_thread_id = None

        if fixture_changed and thread_required:
            destination = await self.tracker.ensure_match_thread(
                self,
                match,
                forum_channel_id=self.settings.forum_channel_id,
                fallback_channel_id=self.target_channel_id,
            )
            await destination.send("🔔 New match thread is live. Updates will be posted here.")

        if self.tracker.match_thread_id is None:
            return

        destination = self.get_channel(self.tracker.match_thread_id)
        if destination is None:
            return

        score = (match.home_goals, match.away_goals)
        if match.state == "in" and score != self.tracker.last_score:
            self.tracker.last_score = score
            await destination.send(embed=self.tracker.build_score_embed(match))

        if match.state == "in":
            substitutions = await with_retry(lambda: self.api.get_substitutions(match.fixture_id))
            for sub in substitutions:
                if sub.dedupe_key in self.tracker.posted_sub_keys:
                    continue
                self.tracker.posted_sub_keys.add(sub.dedupe_key)
                minute = f"{sub.elapsed}'" if sub.elapsed is not None else "?"
                await destination.send(
                    f"🔁 **Substitution ({minute})** {sub.team_name}: "
                    f"{sub.player_out} ⬇️ / {sub.player_in} ⬆️"
                )

        if match.state == "post":
            await destination.send(f"🏁 Final: {self._score_line(match)}")


def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    bot = WhitecapsBot(settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
