"""
Match tracker: polls ESPN API for live Whitecaps matches and detects new events.

Runs as a background asyncio task. When a live match is detected:
  - Sends/updates a live embed in the configured channel
  - Posts goal alerts as separate messages
  - Marks the match as complete when it ends
"""

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
import discord

import espn_api
from embeds import build_match_embed, build_goal_alert_embed

log = logging.getLogger(__name__)

POLL_INTERVAL_LIVE = 30      # seconds during a live match
POLL_INTERVAL_IDLE = 300     # seconds when no match is active (5 min)
GOAL_EVENT_TYPES = {"goal", "score", "penalty goal", "own goal"}


def _is_goal(event: dict) -> bool:
    return any(g in event.get("type", "").lower() for g in GOAL_EVENT_TYPES)


class MatchTracker:
    """
    Tracks live Whitecaps matches and posts updates to a Discord channel.

    Usage:
        tracker = MatchTracker(bot, channel_id=123456)
        tracker.start()   # call after bot is ready
        tracker.stop()    # call on shutdown
    """

    def __init__(self, bot: discord.Client, channel_id: int):
        self.bot = bot
        self.channel_id = channel_id

        # Per-match state
        self._live_message: discord.Message | None = None
        self._current_match_id: str | None = None
        self._seen_events: set[str] = set()
        self._match_over: bool = False

        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public control API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="match_tracker")
            log.info("Match tracker started.")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            log.info("Match tracker stopped.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _channel(self) -> discord.TextChannel | None:
        return self.bot.get_channel(self.channel_id)

    def _reset_state(self) -> None:
        self._live_message = None
        self._current_match_id = None
        self._seen_events = set()
        self._match_over = False

    def _event_key(self, event: dict) -> str:
        return f"{event.get('type')}:{event.get('clock')}:{event.get('team_abbr')}:{event.get('participants', [{}])[0].get('name', '')}"

    async def _post_or_update_live(self, match: dict, summary: dict | None) -> None:
        """Post a new live embed or edit the existing one."""
        channel = self._channel()
        if channel is None:
            return

        key_events = summary.get("key_events", []) if summary else []
        embed = build_match_embed(match, key_events=key_events)

        if self._live_message is None:
            try:
                self._live_message = await channel.send(embed=embed)
                log.info("Posted new live embed for match %s", match["id"])
            except discord.HTTPException as e:
                log.warning("Failed to send live embed: %s", e)
        else:
            try:
                await self._live_message.edit(embed=embed)
                log.debug("Updated live embed for match %s", match["id"])
            except discord.HTTPException as e:
                log.warning("Failed to edit live embed: %s", e)

    async def _handle_new_events(self, match: dict, key_events: list[dict]) -> None:
        """Detect and announce new goals/events since last poll."""
        channel = self._channel()
        if channel is None:
            return

        for event in key_events:
            key = self._event_key(event)
            if key in self._seen_events:
                continue
            self._seen_events.add(key)

            if _is_goal(event):
                embed = build_goal_alert_embed(match, event)
                try:
                    await channel.send(embed=embed)
                    log.info("Posted goal alert: %s", event)
                except discord.HTTPException as e:
                    log.warning("Failed to send goal alert: %s", e)

    async def _post_final(self, match: dict, summary: dict | None) -> None:
        """Edit the live message to a final/post-match embed."""
        channel = self._channel()
        if channel is None:
            return

        key_events = summary.get("key_events", []) if summary else []
        embed = build_match_embed(match, key_events=key_events)

        if self._live_message:
            try:
                await self._live_message.edit(embed=embed)
                log.info("Posted final result for match %s", match["id"])
            except discord.HTTPException as e:
                log.warning("Failed to edit final embed: %s", e)
        else:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException as e:
                log.warning("Failed to send final embed: %s", e)

    # ------------------------------------------------------------------
    # Main polling loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        await self.bot.wait_until_ready()
        log.info("Match tracker loop running.")

        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    interval = await self._tick(session)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.exception("Unhandled error in tracker tick: %s", exc)
                    interval = POLL_INTERVAL_IDLE

                await asyncio.sleep(interval)

    async def _tick(self, session: aiohttp.ClientSession) -> int:
        """
        One polling cycle. Returns the number of seconds to sleep before the next tick.
        """
        matches = await espn_api.get_scoreboard(session)

        if not matches:
            # No matches today — check less frequently
            if self._current_match_id is not None:
                # Match we were tracking disappeared (finished, cancelled, etc.)
                log.info("No matches found; resetting tracker state.")
                self._reset_state()
            return POLL_INTERVAL_IDLE

        # Pick the first match (Whitecaps typically play one game per day)
        match = matches[0]
        match_id = match["id"]
        state = match["status"]["state"]

        # ---- Match just started / newly detected ----
        if match_id != self._current_match_id:
            self._reset_state()
            self._current_match_id = match_id
            log.info("Tracking match %s (state=%s)", match_id, state)

            if state == "pre":
                # Announce upcoming match
                channel = self._channel()
                if channel:
                    embed = build_match_embed(match)
                    try:
                        await channel.send(embed=embed)
                    except discord.HTTPException as e:
                        log.warning("Failed to send pre-match embed: %s", e)
                return POLL_INTERVAL_IDLE

        # ---- Live match ----
        if state == "in":
            summary = await espn_api.get_match_summary(session, match_id)
            key_events = summary.get("key_events", []) if summary else []

            await self._handle_new_events(match, key_events)
            await self._post_or_update_live(match, summary)
            return POLL_INTERVAL_LIVE

        # ---- Match just finished ----
        if state == "post" and not self._match_over:
            self._match_over = True
            summary = await espn_api.get_match_summary(session, match_id)
            await self._post_final(match, summary)
            return POLL_INTERVAL_IDLE

        return POLL_INTERVAL_IDLE
