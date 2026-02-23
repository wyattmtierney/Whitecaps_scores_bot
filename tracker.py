"""
Match tracker: polls ESPN API for live Whitecaps matches and detects new events.

Runs as a background asyncio task. When a live match is detected:
  - Creates a forum thread in the configured forum channel (if set)
  - Sends/updates a live embed in the thread (or fallback channel)
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
POLL_INTERVAL_PRE = 60       # seconds when a match is scheduled but not started
POLL_INTERVAL_IDLE = 300     # seconds when no match is active (5 min)
GOAL_EVENT_TYPES = {"goal", "score", "penalty goal", "own goal"}
SUB_EVENT_TYPES = {"substitution", "sub"}


def _is_goal(event: dict) -> bool:
    return any(g in event.get("type", "").lower() for g in GOAL_EVENT_TYPES)


def _is_substitution(event: dict) -> bool:
    return any(s in event.get("type", "").lower() for s in SUB_EVENT_TYPES)


def _format_thread_title(match: dict) -> str:
    """Build a forum thread title like 'Away @ Home - Feb. 18, 2026'."""
    away_name = match["away"]["name"]
    home_name = match["home"]["name"]

    try:
        dt = datetime.fromisoformat(match["date"].replace("Z", "+00:00"))
        date_str = dt.strftime("%b. %d, %Y").replace(" 0", " ")
    except (ValueError, KeyError):
        date_str = "TBD"

    return f"{away_name} @ {home_name} - {date_str}"


class MatchTracker:
    """
    Tracks live Whitecaps matches and posts updates to a Discord channel.

    When ``forum_channel_id`` is provided the tracker creates a new forum
    thread for each match and posts all updates inside it.  If not set, it
    falls back to posting directly in the regular ``channel_id``.

    Usage:
        tracker = MatchTracker(bot, channel_id=123, forum_channel_id=456)
        tracker.start()   # call after bot is ready
        tracker.stop()    # call on shutdown
    """

    def __init__(
        self,
        bot: discord.Client,
        channel_id: int = 0,
        forum_channel_id: int | None = None,
    ):
        self.bot = bot
        self.channel_id = channel_id
        self.forum_channel_id = forum_channel_id

        # Per-match state
        self._live_message: discord.Message | None = None
        self._current_match_id: str | None = None
        self._seen_events: set[str] = set()
        self._match_over: bool = False
        self._thread: discord.Thread | None = None
        self._last_state: str | None = None

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

    def _fallback_channel(self) -> discord.TextChannel | None:
        if self.channel_id:
            return self.bot.get_channel(self.channel_id)
        return None

    def _target_channel(self) -> discord.Thread | discord.TextChannel | None:
        """Return the forum thread if one exists, otherwise the fallback channel."""
        if self._thread is not None:
            return self._thread
        return self._fallback_channel()

    def _reset_state(self) -> None:
        self._live_message = None
        self._current_match_id = None
        self._seen_events = set()
        self._match_over = False
        self._thread = None
        self._last_state = None

    def _event_key(self, event: dict) -> str:
        return (
            f"{event.get('type')}:{event.get('clock')}:{event.get('team_abbr')}"
            f":{event.get('participants', [{}])[0].get('name', '')}:{event.get('text', '')}"
        )

    async def _create_forum_thread(self, match: dict) -> discord.Thread | None:
        """Create a new thread in the forum channel for this match."""
        if not self.forum_channel_id:
            return None

        forum = self.bot.get_channel(self.forum_channel_id)
        if not isinstance(forum, discord.ForumChannel):
            log.warning(
                "FORUM_CHANNEL_ID %s is not a ForumChannel (got %s); "
                "falling back to regular channel.",
                self.forum_channel_id,
                type(forum).__name__ if forum else "None",
            )
            return None

        title = _format_thread_title(match)
        embed = build_match_embed(match)

        try:
            result = await forum.create_thread(
                name=title,
                content=(
                    "Match day! \U0001f1e8\U0001f1e6 "
                    "Let's get it started \u2014 drop your predictions below!"
                ),
                embed=embed,
            )
            # discord.py returns a ThreadWithMessage namedtuple
            thread = result.thread if hasattr(result, "thread") else result
            log.info("Created forum thread '%s' (id=%s)", title, thread.id)
            return thread
        except discord.HTTPException as e:
            log.warning("Failed to create forum thread: %s", e)
            return None

    async def _post_or_update_live(self, match: dict, summary: dict | None) -> None:
        """Post a new live embed or edit the existing one."""
        channel = self._target_channel()
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
        """Detect and announce new goals/substitutions since last poll."""
        channel = self._target_channel()
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
            elif _is_substitution(event):
                clock = event.get("clock", "")
                team = event.get("team_abbr") or event.get("team") or ""
                text = event.get("text", "Substitution")
                try:
                    await channel.send(f"🔄 **Substitution** `{clock}` {team} — {text}")
                    log.info("Posted substitution alert: %s", event)
                except discord.HTTPException as e:
                    log.warning("Failed to send substitution alert: %s", e)

    async def _post_match_started(self, match: dict) -> None:
        channel = self._target_channel()
        if channel is None:
            return

        home = match["home"]["abbreviation"]
        away = match["away"]["abbreviation"]
        try:
            await channel.send(f"🔴 **Kickoff:** {home} vs {away} is underway!")
            log.info("Posted kickoff alert for match %s", match["id"])
        except discord.HTTPException as e:
            log.warning("Failed to post kickoff alert: %s", e)

    async def _post_match_finished(self, match: dict) -> None:
        channel = self._target_channel()
        if channel is None:
            return

        home = match["home"]
        away = match["away"]
        detail = match["status"].get("detail", "Full Time")
        try:
            await channel.send(
                f"✅ **Final:** {home['abbreviation']} {home['score']} - {away['score']} {away['abbreviation']} ({detail})"
            )
            log.info("Posted final whistle alert for match %s", match["id"])
        except discord.HTTPException as e:
            log.warning("Failed to post final whistle alert: %s", e)

    async def _post_final(self, match: dict, summary: dict | None) -> None:
        """Edit the live message to a final/post-match embed."""
        channel = self._target_channel()
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
            self._last_state = state
            log.info("Tracking match %s (state=%s)", match_id, state)

            # Try to create a forum thread for this match
            self._thread = await self._create_forum_thread(match)

            if state == "in":
                await self._post_match_started(match)
            elif state == "post":
                await self._post_match_finished(match)

            if state == "pre":
                # If we didn't create a forum thread, post in fallback channel
                if self._thread is None:
                    channel = self._fallback_channel()
                    if channel:
                        embed = build_match_embed(match)
                        try:
                            await channel.send(embed=embed)
                        except discord.HTTPException as e:
                            log.warning("Failed to send pre-match embed: %s", e)
                return POLL_INTERVAL_PRE

        # Status transitions can be missed if the bot restarts mid-match, so
        # announce kickoff/final whenever we observe a state change.
        if self._last_state != state:
            if state == "in":
                await self._post_match_started(match)
            elif state == "post":
                await self._post_match_finished(match)
            self._last_state = state

        # ---- Live match ----
        if state == "in":
            # If we haven't created a thread yet (e.g. bot started mid-match),
            # try now so live updates go into the thread.
            if self._thread is None and self.forum_channel_id:
                self._thread = await self._create_forum_thread(match)

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
