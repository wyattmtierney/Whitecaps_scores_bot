# Whitecaps Scores Bot

A Discord bot built for **Vancouver Whitecaps FC** fans. Get live match updates, upcoming schedules, MLS standings, and more — all delivered straight to your Discord server.

## Features

| Command | Description |
|---------|-------------|
| `/live` | Start posting live match updates in the current channel |
| `/stop` | Stop live updates |
| `/status` | Show the current or next Whitecaps match |
| `/upcoming` | Show the next 5 upcoming Whitecaps matches |
| `/standings` | Show the MLS league table |

All commands work as both **slash commands** (`/live`) and **prefix commands** (`!live`).

### Live match notifications

When live tracking is active, the bot automatically posts:

- **Goal alerts** — score change embeds with live minute and match status
- **Yellow & red card alerts** — player name, team, and minute
- **Substitution alerts** — player on/off with minute
- **Half-time embed** — score summary at the break
- **Full-time embed** — final score with win/loss/draw colour coding

### Match-day threads

The bot auto-creates a match-day thread in your configured forum channel **24 hours before kickoff**. All live updates are posted inside the thread to keep your server organized.

## Data sources

- **ESPN** (primary) — free public API, no key required
- **API-Football** (optional fallback) — used if ESPN is unavailable

## Setup

### 1. Install

```bash
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
```

Fill in your `.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_TOKEN` | Yes | — | Discord bot token |
| `DISCORD_GUILD_ID` | Recommended | — | Server ID (enables instant slash command sync) |
| `FORUM_CHANNEL_ID` | Recommended | — | Forum channel for auto-created match-day threads |
| `CHANNEL_ID` | No | — | Fallback text channel for updates |
| `ESPN_TEAM_ID` | No | `9727` | ESPN team ID for Vancouver Whitecaps |
| `ESPN_TEAM_NAME` | No | `Vancouver Whitecaps` | ESPN team name for matching |
| `API_FOOTBALL_KEY` | No | — | API-Football key (fallback provider) |
| `WHITECAPS_TEAM_ID` | No | `1613` | API-Football team ID |
| `POLL_INTERVAL_SECONDS` | No | `30` | How often to poll for live updates (seconds) |
| `COMMAND_PREFIX` | No | `!` | Prefix for text commands |

### 3. Run

```bash
python -m whitecaps_bot.bot
```

## Deployment

### Railway (recommended)

A `railway.toml` is included for one-click deployment. Set your environment variables as Railway service variables:

- `DISCORD_TOKEN`
- `DISCORD_GUILD_ID`
- `FORUM_CHANNEL_ID`
- `CHANNEL_ID`

The bot will auto-start live tracking on boot if `CHANNEL_ID` or `FORUM_CHANNEL_ID` is set.

### Running tests

```bash
pip install -e .
pytest
```
