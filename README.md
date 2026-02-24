# Whitecaps_scores_bot

Discord bot that posts **live Vancouver Whitecaps match updates** to your server, including:
- live score updates
- substitution alerts

## Requirements

- Python 3.11+
- A Discord bot token
- No API key is required for ESPN live data (primary source)
- Optional: An [API-Football](https://www.api-football.com/) API key as fallback for fixture/events

## Setup

1. Install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure environment variables:

   ```bash
   cp .env.example .env
   ```

   Fill in values in `.env`:
   - `DISCORD_TOKEN` (Railway-friendly; `DISCORD_BOT_TOKEN` also supported)
   - `ESPN_TEAM_ID` (default `9720` for Vancouver Whitecaps)
   - `ESPN_TEAM_NAME` (default `Vancouver Whitecaps`)
   - optional: `API_FOOTBALL_KEY` (fallback provider if ESPN is unavailable)
   - optional: `CHANNEL_ID` (fallback text channel for updates)
   - optional: `FORUM_CHANNEL_ID` (forum channel for auto-created match-day threads)
   - optional: `WHITECAPS_TEAM_ID` (default `1613`, API-Football fallback team id)
   - optional: `POLL_INTERVAL_SECONDS` (default `30`)
   - optional: `COMMAND_PREFIX` (default `!`)

3. Run the bot:

   ```bash
   python -m whitecaps_bot.bot
   ```

## Discord commands

- `!whitecapslive` — start posting live updates in the current channel
- `!whitecapsstop` — stop live updates
- `!whitecapsstatus` — fetch current live score once

## Notes

- ESPN public endpoints are used first (based on the Public-ESPN-API endpoint patterns).
- `ESPN_TEAM_ID` and `ESPN_TEAM_NAME` let you override team matching if ESPN data changes.
- The bot only posts while a Whitecaps fixture is live.
- It deduplicates substitution posts so each event is only sent once.

## Railway deployment notes

If you host on Railway, set these service variables:
- `DISCORD_TOKEN`
- `CHANNEL_ID`
- `FORUM_CHANNEL_ID` (optional)
- `ESPN_TEAM_ID`
- `ESPN_TEAM_NAME`
- `API_FOOTBALL_KEY` (optional fallback provider key)

The bot reads `DISCORD_TOKEN` first and falls back to `DISCORD_BOT_TOKEN` for backward compatibility.
