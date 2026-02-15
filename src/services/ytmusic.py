"""YouTube Music API wrapper for fetching history and managing playlists."""

import logging

from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)


class YTMusicService:
    def __init__(self, auth_file: str):
        self.yt = YTMusic(auth_file)
        logger.info("YTMusic client initialized")

    def get_history(self) -> list[dict]:
        """Fetch recent listening history and return normalized song entries."""
        raw = self.yt.get_history()
        songs = []
        for item in raw:
            try:
                songs.append({
                    "videoId": item.get("videoId"),
                    "title": item.get("title", "Unknown"),
                    "artist": ", ".join(
                        a["name"] for a in item.get("artists", [])
                    ) or "Unknown",
                    "album": (item.get("album") or {}).get("name", "Unknown"),
                    "duration_seconds": _parse_duration(
                        item.get("duration", "0:00")
                    ),
                    "played_at": item.get("played", ""),
                })
            except Exception as e:
                logger.warning("Skipping malformed history entry: %s", e)
        logger.info("Fetched %d songs from history", len(songs))
        return songs

    def create_playlist(self, name: str, description: str) -> str:
        """Create a new playlist and return its ID."""
        pid = self.yt.create_playlist(title=name, description=description)
        logger.info("Created playlist: %s (%s)", name, pid)
        return pid

    def find_playlist_by_name(self, name: str) -> str | None:
        """Search user's library for a playlist with an exact title match."""
        try:
            playlists = self.yt.get_library_playlists(limit=100)
            for pl in playlists:
                if pl.get("title") == name:
                    return pl["playlistId"]
        except Exception as e:
            logger.error("Failed to list playlists: %s", e)
        return None

    def get_playlist_video_ids(self, playlist_id: str) -> set[str]:
        """Get all videoIds currently in a playlist."""
        try:
            playlist = self.yt.get_playlist(playlist_id, limit=None)
            return {
                t["videoId"]
                for t in playlist.get("tracks", [])
                if t.get("videoId")
            }
        except Exception as e:
            logger.error("Failed to fetch playlist %s: %s", playlist_id, e)
            return set()

    def add_songs_to_playlist(
        self, playlist_id: str, video_ids: list[str]
    ) -> int:
        """Add songs to a playlist, skipping duplicates. Returns count added."""
        if not video_ids:
            return 0
        existing = self.get_playlist_video_ids(playlist_id)
        new_ids = [vid for vid in video_ids if vid not in existing]
        if not new_ids:
            return 0
        try:
            self.yt.add_playlist_items(playlist_id, new_ids, duplicates=False)
            logger.info("Added %d songs to playlist %s", len(new_ids), playlist_id)
            return len(new_ids)
        except Exception as e:
            logger.error("Failed adding songs to playlist %s: %s", playlist_id, e)
            return 0


def _parse_duration(duration_str: str) -> int:
    """Parse '3:45' or '1:02:30' to total seconds."""
    parts = duration_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0
