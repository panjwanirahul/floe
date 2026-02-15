"""Floe sync engine - fetches history, categorizes songs, updates playlists."""

import json
import logging
import sys
from datetime import datetime

from src.config import (
    DATA_DIR,
    LOGS_DIR,
    load_activity_log,
    load_env,
    load_playlists,
    load_schedule,
    load_song_cache,
    save_playlists,
    save_song_cache,
)
from src.services.categorizer import Categorizer
from src.services.ytmusic import YTMusicService

logger = logging.getLogger(__name__)


def ensure_playlists(ytmusic: YTMusicService, playlists: list[dict]) -> list[dict]:
    """Create any playlists on YT Music that don't have an ID yet."""
    changed = False
    for p in playlists:
        if p.get("ytmusic_playlist_id"):
            continue
        existing_id = ytmusic.find_playlist_by_name(p["name"])
        if existing_id:
            p["ytmusic_playlist_id"] = existing_id
        else:
            p["ytmusic_playlist_id"] = ytmusic.create_playlist(
                p["name"], f"Auto-curated by Floe - {p['description']}"
            )
        changed = True
    if changed:
        save_playlists(playlists)
    return playlists


def run_sync(song_limit: int | None = None) -> dict:
    """Run the full sync pipeline. Returns a report dict.

    Args:
        song_limit: Max songs to process. None = all available.
                    On first run (empty cache), uses schedule's initial_scan_depth.
    """
    config = load_env()
    if not config["anthropic_key"]:
        raise RuntimeError("ANTHROPIC_API_KEY not set in config/.env")

    playlists = load_playlists()
    schedule = load_schedule()
    activity_log = load_activity_log()

    if not playlists:
        raise RuntimeError("No playlists configured. Run setup first.")

    logger.info("=== Floe Sync Started ===")

    ytmusic = YTMusicService(config["auth_file"])
    categorizer = Categorizer(api_key=config["anthropic_key"])

    playlists = ensure_playlists(ytmusic, playlists)
    playlist_id_map = {p["key"]: p["ytmusic_playlist_id"] for p in playlists}

    # Fetch history
    songs = ytmusic.get_history()
    if not songs:
        logger.info("No listening history found.")
        return {"status": "empty", "songs_fetched": 0, "total_added": 0}

    # On first run with empty cache, use initial_scan_depth
    cache = load_song_cache()
    if not cache and song_limit is None:
        song_limit = schedule.get("initial_scan_depth", 100)

    if song_limit:
        songs = songs[:song_limit]

    logger.info("Processing %d songs", len(songs))

    # Split into cached vs new
    new_songs = [s for s in songs if s["videoId"] not in cache]
    cached_results = [cache[s["videoId"]] for s in songs if s["videoId"] in cache]
    logger.info("%d new, %d cached", len(new_songs), len(cached_results))

    # Categorize new songs with Claude
    new_results = []
    if new_songs:
        new_results = categorizer.categorize(new_songs, playlists, schedule, activity_log)
        for cat in new_results:
            vid = cat.get("videoId")
            if vid:
                cache[vid] = cat
        save_song_cache(cache)

    all_results = cached_results + new_results

    # Group by playlist and add
    playlist_songs: dict[str, list[str]] = {}
    for cat in all_results:
        key = cat.get("best_playlist", schedule.get("default_playlist", ""))
        vid = cat.get("videoId")
        if vid and key:
            playlist_songs.setdefault(key, []).append(vid)

    breakdown = {}
    total_added = 0
    for key, vids in playlist_songs.items():
        pid = playlist_id_map.get(key)
        if not pid:
            logger.warning("No YT playlist for key: %s", key)
            continue
        added = ytmusic.add_songs_to_playlist(pid, vids)
        pname = next((p["name"] for p in playlists if p["key"] == key), key)
        breakdown[key] = {"name": pname, "attempted": len(vids), "added": added}
        total_added += added

    # Build report
    report = {
        "status": "success",
        "date": datetime.now().isoformat(),
        "songs_fetched": len(songs),
        "new_categorizations": len(new_results),
        "cached": len(cached_results),
        "total_added": total_added,
        "breakdown": breakdown,
    }

    logger.info("Sync complete: %d fetched, %d added", len(songs), total_added)

    # Save report
    LOGS_DIR.mkdir(exist_ok=True)
    report_file = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}_report.json"
    report_file.write_text(json.dumps(report, indent=2))

    return report


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        result = run_sync()
        print(json.dumps(result, indent=2))
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
