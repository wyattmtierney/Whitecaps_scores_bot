from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    discord_token: str
    discord_guild_id: int | None
    channel_id: int | None
    forum_channel_id: int | None
    api_football_key: str
    whitecaps_team_id: int
    poll_interval_seconds: int
    command_prefix: str

    @staticmethod
    def from_env() -> "Settings":
        discord_token = os.getenv("DISCORD_BOT_TOKEN", "")
        api_football_key = os.getenv("API_FOOTBALL_KEY", "")

        if not discord_token:
            raise ValueError("Missing DISCORD_BOT_TOKEN environment variable.")
        if not api_football_key:
            raise ValueError("Missing API_FOOTBALL_KEY environment variable.")

        guild_id = os.getenv("DISCORD_GUILD_ID")
        channel_id = os.getenv("CHANNEL_ID")
        forum_channel_id = os.getenv("FORUM_CHANNEL_ID")
        return Settings(
            discord_token=discord_token,
            discord_guild_id=int(guild_id) if guild_id else None,
            channel_id=int(channel_id) if channel_id else None,
            forum_channel_id=int(forum_channel_id) if forum_channel_id else None,
            api_football_key=api_football_key,
            whitecaps_team_id=int(os.getenv("WHITECAPS_TEAM_ID", "1613")),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "30")),
            command_prefix=os.getenv("COMMAND_PREFIX", "!"),
        )
