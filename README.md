# Whitecaps_scores_bot

Discord bot that posts **live Vancouver Whitecaps match updates** to your server, including:
- live score updates
- substitution alerts

## Requirements

- Python 3.11+
- A Discord bot token
- An [API-Football](https://www.api-football.com/) API key (for live fixtures + events)

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
   - `DISCORD_BOT_TOKEN`
   - `API_FOOTBALL_KEY`
   - optional: `CHANNEL_ID` (fallback text channel for updates)
   - optional: `FORUM_CHANNEL_ID` (forum channel for auto-created match-day threads)
   - optional: `WHITECAPS_TEAM_ID` (default `1613`)
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

- The bot only posts while a Whitecaps fixture is live.
- It deduplicates substitution posts so each event is only sent once.
