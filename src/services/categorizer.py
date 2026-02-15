"""Claude-powered song categorization with dynamic, user-configured playlists."""

import json
import logging
from datetime import datetime

import anthropic

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """\
You are analyzing songs to categorize them into the user's custom playlists.

Available Playlists:
{playlists_section}

User's Recurring Schedule:
{schedule_section}

Recent Activity Log (one-off entries that override the recurring schedule):
{activity_log_section}

Default playlist (when no schedule matches): "{default_playlist}"

For each song, consider:
- Play time is a strong signal (60% weight): match it against the schedule/activity log above
- Song characteristics (40% weight): use the playlist descriptions to judge fit
- If a one-off activity log entry covers the play time, it takes priority over the recurring schedule
- If confidence < 0.6, assign to the default playlist

Analyze each song below and return a JSON array. For each song, return:
{{
  "videoId": "<the videoId>",
  "energy_level": <1-10>,
  "tempo": "slow|medium|fast",
  "mood": "<one word>",
  "best_playlist": "<playlist key from the list above>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>"
}}

Songs to analyze:
{songs_json}

Return ONLY a valid JSON array, no markdown fencing.
"""


def build_playlists_section(playlists: list[dict]) -> str:
    """Build the playlists portion of the prompt from config."""
    lines = []
    for p in playlists:
        lines.append(f'- "{p["key"]}": {p["name"]} - {p["description"]}')
    return "\n".join(lines) if lines else "No playlists configured."


def build_schedule_section(schedule: dict) -> str:
    """Build the schedule portion of the prompt from config."""
    activities = schedule.get("activities", [])
    if not activities:
        return "No recurring schedule configured."

    day_labels = {
        "mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu",
        "fri": "Fri", "sat": "Sat", "sun": "Sun",
    }
    lines = []
    for act in activities:
        days = ", ".join(day_labels.get(d, d) for d in act.get("days", []))
        windows = ", ".join(
            f'{w["start"]}-{w["end"]}' for w in act.get("windows", [])
        )
        lines.append(
            f'- {days} {windows}: {act["name"]} → playlist "{act["playlist"]}"'
        )
    return "\n".join(lines)


def build_activity_log_section(activity_log: list[dict], today: str) -> str:
    """Build the activity log portion, filtering to recent entries."""
    if not activity_log:
        return "No recent activity logged."

    # Include entries from the last 2 days
    recent = []
    for entry in activity_log:
        entry_date = entry.get("start", "")[:10]
        if entry_date >= today[:8] + "00":  # same month, rough filter
            recent.append(entry)

    if not recent:
        return "No recent activity logged."

    lines = []
    for entry in recent[-20:]:  # cap at 20 entries
        lines.append(
            f'- {entry["start"]} to {entry["end"]}: '
            f'playlist "{entry["playlist"]}"'
            f'{" (" + entry["note"] + ")" if entry.get("note") else ""}'
        )
    return "\n".join(lines)


class Categorizer:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def categorize(
        self,
        songs: list[dict],
        playlists: list[dict],
        schedule: dict,
        activity_log: list[dict],
    ) -> list[dict]:
        """Categorize songs using Claude with the user's playlist/schedule config."""
        if not songs:
            return []

        today = datetime.now().strftime("%Y-%m-%d")
        playlists_section = build_playlists_section(playlists)
        schedule_section = build_schedule_section(schedule)
        activity_log_section = build_activity_log_section(activity_log, today)
        default_playlist = schedule.get("default_playlist", playlists[0]["key"] if playlists else "unknown")

        # Strip songs to just what Claude needs
        songs_for_prompt = [
            {
                "videoId": s["videoId"],
                "title": s["title"],
                "artist": s["artist"],
                "album": s["album"],
                "played_at": s.get("played_at", ""),
            }
            for s in songs
        ]

        # Process in batches of 20
        all_results = []
        batch_size = 20
        for i in range(0, len(songs_for_prompt), batch_size):
            batch = songs_for_prompt[i : i + batch_size]
            prompt = PROMPT_TEMPLATE.format(
                playlists_section=playlists_section,
                schedule_section=schedule_section,
                activity_log_section=activity_log_section,
                default_playlist=default_playlist,
                songs_json=json.dumps(batch, indent=2),
            )
            results = self._call_claude(prompt)
            all_results.extend(results)

        return all_results

    def _call_claude(self, prompt: str) -> list[dict]:
        """Send prompt to Claude and parse the JSON response."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()

            # Strip markdown fencing if Claude adds it
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text[: text.rfind("```")]
                text = text.strip()

            results = json.loads(text)
            if not isinstance(results, list):
                results = [results]
            logger.info("Claude categorized %d songs", len(results))
            return results

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response as JSON: %s", e)
            return []
        except anthropic.APIError as e:
            logger.error("Claude API error: %s", e)
            return []
