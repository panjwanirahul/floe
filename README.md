# Floe

Automated YouTube Music playlist curator. Floe analyzes your listening history daily using Claude AI, figures out what you were doing when you listened (gym, commute, work, chill), and sorts songs into the right playlists — automatically.

You define the playlists. You map your schedule. Floe handles the rest every night.

## What it does

- Connects to your YouTube Music account and pulls listening history
- Uses Claude to analyze each song's energy, tempo, and mood against your schedule
- Categorizes songs into your custom playlists (you create as many as you want)
- Caches results so the same song isn't re-analyzed
- Auto-refreshes YouTube Music auth from your Chrome browser cookies
- Runs daily via cron — set it and forget it

## Prerequisites

- Python 3.10+
- Google Chrome with YouTube Music logged in
- An [Anthropic API key](https://console.anthropic.com/)

## Running locally

**1. Clone and install**

```bash
git clone https://github.com/panjwanirahul/floe.git
cd floe
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Set up API keys**

```bash
cp config/.env.example config/.env
```

Open `config/.env` and paste your Anthropic API key.

**3. YouTube Music auth**

No manual setup needed. Floe automatically extracts cookies from Chrome every time it runs. Just make sure you're logged into [YouTube Music](https://music.youtube.com) in Chrome.

On macOS, you'll get a Keychain prompt the first time — click **Always Allow** so it doesn't ask again.

**4. Launch Floe**

```bash
python setup.py
```

This opens a web UI at `http://localhost:5050` where you:
- Create your playlists (name, emoji, vibe description)
- Map your weekly schedule (work hours, gym, commute, etc.)
- Choose how far back to scan your history on the first sync
- Hit **Save & Create Playlists**

You'll land on a dashboard where you can trigger syncs, add playlists, log activities, and see stats.

**5. Automate it**

Add a cron job to sync every night at 11 PM:

```bash
crontab -e
```

```
0 23 * * * cd /path/to/floe && /path/to/venv/bin/python -m src.main
```

## Project structure

```
floe/
├── src/
│   ├── app.py                 # Flask web UI
│   ├── main.py                # Sync engine (cron entry point)
│   ├── config.py              # Config I/O
│   ├── templates/             # Setup + dashboard pages
│   └── services/
│       ├── ytmusic.py         # YT Music API + auto cookie refresh
│       └── categorizer.py     # Claude-powered song analysis
├── config/
│   └── .env.example           # API key template
├── setup.py                   # Launches the web UI
└── requirements.txt
```

## Stack

- **ytmusicapi** — YouTube Music API
- **anthropic** — Claude AI for categorization
- **flask** — Minimal web UI
- **pycookiecheat** — Auto-refresh Chrome cookies for YT Music auth
- **python-dotenv** — Config management
