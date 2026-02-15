"""Floe web UI - minimal Flask app for configuration and sync."""

import logging
import threading

from flask import Flask, jsonify, redirect, render_template, request

from src.config import (
    is_setup_done,
    load_activity_log,
    load_env,
    load_last_report,
    load_playlists,
    load_schedule,
    save_activity_log,
    save_playlists,
    save_schedule,
    slugify,
)
from src.main import ensure_playlists, run_sync
from src.services.ytmusic import YTMusicService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = Flask(__name__, template_folder="templates")

sync_state = {"running": False, "result": None}


# ── Pages ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not is_setup_done():
        return redirect("/setup")
    return redirect("/dashboard")


@app.route("/setup")
def setup_page():
    return render_template("setup.html")


@app.route("/dashboard")
def dashboard_page():
    playlists = load_playlists()
    schedule = load_schedule()
    activity_log = load_activity_log()
    last_report = load_last_report()

    # Get song counts per playlist
    try:
        config = load_env()
        ytmusic = YTMusicService(config["auth_file"])
        for p in playlists:
            pid = p.get("ytmusic_playlist_id")
            if pid:
                p["song_count"] = len(ytmusic.get_playlist_video_ids(pid))
            else:
                p["song_count"] = 0
    except Exception:
        for p in playlists:
            p["song_count"] = "?"

    return render_template(
        "dashboard.html",
        playlists=playlists,
        schedule=schedule,
        activity_log=activity_log[-10:],
        last_report=last_report,
        sync_running=sync_state["running"],
    )


# ── API: Setup ───────────────────────────────────────────────────────────────

@app.route("/api/setup", methods=["POST"])
def api_setup():
    data = request.json

    # Build playlists
    playlists = []
    for p in data.get("playlists", []):
        name = p.get("name", "").strip()
        if not name:
            continue
        emoji = p.get("emoji", "").strip()
        display_name = f"{emoji} {name}" if emoji else name
        playlists.append({
            "key": slugify(name),
            "name": display_name,
            "description": p.get("description", "").strip(),
            "ytmusic_playlist_id": None,
        })

    if not playlists:
        return jsonify({"error": "At least one playlist is required."}), 400

    # Build schedule
    activities = []
    for a in data.get("activities", []):
        name = a.get("name", "").strip()
        if not name or not a.get("days") or not a.get("windows") or not a.get("playlist"):
            continue
        activities.append({
            "name": name,
            "playlist": a["playlist"],
            "days": a["days"],
            "windows": a["windows"],
        })

    schedule = {
        "activities": activities,
        "default_playlist": data.get("default_playlist", playlists[0]["key"]),
        "initial_scan_depth": data.get("initial_scan_depth", 100),
    }

    save_playlists(playlists)
    save_schedule(schedule)
    save_activity_log([])

    # Create playlists on YT Music
    try:
        config = load_env()
        ytmusic = YTMusicService(config["auth_file"])
        playlists = ensure_playlists(ytmusic, playlists)
    except Exception as e:
        return jsonify({"error": f"YT Music error: {e}"}), 500

    return jsonify({"success": True})


# ── API: Add playlist ────────────────────────────────────────────────────────

@app.route("/api/playlist", methods=["POST"])
def api_add_playlist():
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name is required."}), 400

    playlists = load_playlists()
    key = slugify(name)
    if any(p["key"] == key for p in playlists):
        return jsonify({"error": "A playlist with that name already exists."}), 400

    emoji = data.get("emoji", "").strip()
    display_name = f"{emoji} {name}" if emoji else name
    description = data.get("description", "").strip()

    new_playlist = {
        "key": key,
        "name": display_name,
        "description": description,
        "ytmusic_playlist_id": None,
    }

    # Create on YT Music immediately
    try:
        config = load_env()
        ytmusic = YTMusicService(config["auth_file"])
        pid = ytmusic.find_playlist_by_name(display_name)
        if not pid:
            pid = ytmusic.create_playlist(display_name, f"Auto-curated by Floe - {description}")
        new_playlist["ytmusic_playlist_id"] = pid
    except Exception as e:
        return jsonify({"error": f"YT Music error: {e}"}), 500

    playlists.append(new_playlist)
    save_playlists(playlists)
    return jsonify({"success": True, "playlist": new_playlist})


# ── API: Add activity ────────────────────────────────────────────────────────

@app.route("/api/activity", methods=["POST"])
def api_add_activity():
    data = request.json
    name = data.get("name", "").strip()
    if not name or not data.get("days") or not data.get("windows") or not data.get("playlist"):
        return jsonify({"error": "All fields are required."}), 400

    schedule = load_schedule()
    schedule["activities"].append({
        "name": name,
        "playlist": data["playlist"],
        "days": data["days"],
        "windows": data["windows"],
    })
    save_schedule(schedule)
    return jsonify({"success": True})


# ── API: Log one-off activity ────────────────────────────────────────────────

@app.route("/api/log", methods=["POST"])
def api_log_activity():
    data = request.json
    date = data.get("date", "").strip()
    start = data.get("start", "").strip()
    end = data.get("end", "").strip()
    playlist = data.get("playlist", "").strip()

    if not all([date, start, end, playlist]):
        return jsonify({"error": "All fields are required."}), 400

    log = load_activity_log()
    log.append({
        "playlist": playlist,
        "start": f"{date}T{start}",
        "end": f"{date}T{end}",
        "note": data.get("note", "").strip(),
    })
    save_activity_log(log)
    return jsonify({"success": True})


# ── API: Sync ────────────────────────────────────────────────────────────────

@app.route("/api/sync", methods=["POST"])
def api_sync():
    if sync_state["running"]:
        return jsonify({"error": "Sync already in progress."}), 409

    limit = request.json.get("limit")
    if limit:
        limit = int(limit) if int(limit) > 0 else None
    else:
        limit = None

    sync_state["running"] = True
    sync_state["result"] = None

    def do_sync():
        try:
            sync_state["result"] = run_sync(song_limit=limit)
        except Exception as e:
            sync_state["result"] = {"status": "error", "error": str(e)}
        finally:
            sync_state["running"] = False

    threading.Thread(target=do_sync, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/sync/status")
def api_sync_status():
    return jsonify({
        "running": sync_state["running"],
        "result": sync_state["result"],
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
