"""Config I/O for Floe - load/save playlists, schedule, activity log."""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
ENV_PATH = str(CONFIG_DIR / ".env")
PLAYLISTS_FILE = CONFIG_DIR / "playlists.json"
SCHEDULE_FILE = CONFIG_DIR / "schedule.json"
ACTIVITY_LOG_FILE = CONFIG_DIR / "activity_log.json"
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"


def load_env():
    load_dotenv(ENV_PATH)
    return {
        "auth_file": os.getenv("YTMUSIC_AUTH_FILE", "./config/headers_auth.json"),
        "anthropic_key": os.getenv("ANTHROPIC_API_KEY", ""),
    }


def load_playlists() -> list[dict]:
    if PLAYLISTS_FILE.exists():
        return json.loads(PLAYLISTS_FILE.read_text())
    return []


def save_playlists(playlists: list[dict]):
    PLAYLISTS_FILE.write_text(json.dumps(playlists, indent=2))


def load_schedule() -> dict:
    if SCHEDULE_FILE.exists():
        return json.loads(SCHEDULE_FILE.read_text())
    return {"activities": [], "default_playlist": None, "initial_scan_depth": 100}


def save_schedule(schedule: dict):
    SCHEDULE_FILE.write_text(json.dumps(schedule, indent=2))


def load_activity_log() -> list[dict]:
    if ACTIVITY_LOG_FILE.exists():
        return json.loads(ACTIVITY_LOG_FILE.read_text())
    return []


def save_activity_log(log: list[dict]):
    ACTIVITY_LOG_FILE.write_text(json.dumps(log, indent=2))


def load_song_cache() -> dict[str, dict]:
    cache_file = DATA_DIR / "song_cache.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return {}


def save_song_cache(cache: dict[str, dict]):
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "song_cache.json").write_text(json.dumps(cache, indent=2))


def load_last_report() -> dict | None:
    """Load the most recent sync report."""
    LOGS_DIR.mkdir(exist_ok=True)
    reports = sorted(LOGS_DIR.glob("*_report.json"), reverse=True)
    if reports:
        return json.loads(reports[0].read_text())
    return None


def is_setup_done() -> bool:
    return PLAYLISTS_FILE.exists() and len(load_playlists()) > 0


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
