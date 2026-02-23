# Vancouver Whitecaps FC Discord Bot

A Discord bot that tracks live Vancouver Whitecaps FC MLS matches, posts goal alerts, and provides schedule/standings information. Data is sourced from the ESPN public API.

---

## Features

- **Live match tracking** — auto-posts a live embed that updates every 30 seconds during a match
- **Goal + substitution alerts** — near-live notifications for major match events
- **Kickoff/final whistle alerts** — explicit start/end match announcements
- **Post-match summary** — final result embed with key events
- **Commands** — `!score`, `!next`, `!schedule`, `!standings`

---

## Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd Whitecaps_scores_bot
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Create a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create a **New Application**, then add a **Bot**
3. Under **Bot → Privileged Gateway Intents**, enable **Message Content Intent**
4. Copy the bot **Token**
5. Invite the bot to your server with the `bot` scope and `Send Messages`, `Embed Links`, `Read Message History` permissions

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
DISCORD_TOKEN=your_bot_token_here
CHANNEL_ID=your_channel_id_here
COMMAND_PREFIX=!          # optional, defaults to !
LOG_LEVEL=INFO            # optional
```

To get the channel ID: enable Developer Mode in Discord → right-click the channel → **Copy ID**.

### 5. Run the bot

```bash
python bot.py
```

---

## Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `!score` | `!live`, `!s` | Today's Whitecaps match score/status |
| `!next` | `!upcoming`, `!n` | Next scheduled Whitecaps match |
| `!schedule` | `!fixtures`, `!sch` | Season schedule with recent results |
| `!standings` | `!table`, `!st` | Current MLS standings |
| `!help` | `!commands`, `!h` | Show this help message |

---

## Project Structure

```
Whitecaps_scores_bot/
├── bot.py          # Discord bot entry point and commands
├── tracker.py      # Background live match polling and event detection
├── embeds.py       # Discord embed builders (match, schedule, standings, goal alert)
├── espn_api.py     # ESPN public API client
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## How Live Tracking Works

1. When the bot starts, `MatchTracker` launches as a background asyncio task.
2. It polls the ESPN scoreboard every **5 minutes** when there is no active match.
3. If a match is scheduled (`pre`), poll interval tightens to **60 seconds** to catch kickoff quickly.
4. When a live match is detected, the poll interval drops to **30 seconds**.
5. Each tick it:
   - Fetches the match summary (key events)
   - Compares events against a seen-events set to detect new goals/cards
   - Posts goal alert embeds for new goals
   - Edits the pinned live embed with the current score and clock
6. When the match ends it posts a final result embed and returns to idle polling.

---

## Requirements

- Python 3.11+
- `discord.py >= 2.3.0`
- `aiohttp >= 3.9.0`
- `python-dotenv >= 1.0.0`
