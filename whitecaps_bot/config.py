from __future__ import annotations

import os
from dataclasses import dataclass


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


@dataclass(frozen=True)
class Settings:
    discord_token: str
    discord_guild_id: int | None
    channel_id: int | None
    forum_channel_id: int | None
    api_football_key: str | None
    espn_team_id: str
    espn_team_name: str
    whitecaps_team_id: int
    poll_interval_seconds: int
    command_prefix: str

    @staticmethod
    def from_env() -> "Settings":
        # Railway-friendly variable names are supported first, with backwards compatibility.
        discord_token = _first_env("DISCORD_TOKEN", "DISCORD_BOT_TOKEN")
        api_football_key = _first_env("API_FOOTBALL_KEY", "APIFOOTBALL_KEY") or None

        if not discord_token:
            raise ValueError("Missing DISCORD_TOKEN (or DISCORD_BOT_TOKEN) environment variable.")

        guild_id = os.getenv("DISCORD_GUILD_ID")
        channel_id = os.getenv("CHANNEL_ID")
        forum_channel_id = os.getenv("FORUM_CHANNEL_ID")
        return Settings(
            discord_token=discord_token,
            discord_guild_id=int(guild_id) if guild_id else None,
            channel_id=int(channel_id) if channel_id else None,
            forum_channel_id=int(forum_channel_id) if forum_channel_id else None,
            api_football_key=api_football_key,
            espn_team_id=os.getenv("ESPN_TEAM_ID", "9720"),
            espn_team_name=os.getenv("ESPN_TEAM_NAME", "Vancouver Whitecaps"),
            whitecaps_team_id=int(os.getenv("WHITECAPS_TEAM_ID", "1613")),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "30")),
            command_prefix=os.getenv("COMMAND_PREFIX", "!"),
        )
