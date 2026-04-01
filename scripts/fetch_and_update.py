"""
Main pipeline: fetch club activities from Strava → merge into archive → calculate points → write docs/data.json

The archive (docs/activities_archive.json) grows over time so the full
competition history is preserved beyond Strava's 200-activity rolling window.

Run locally:
    python scripts/fetch_and_update.py

Or automatically via GitHub Actions (see .github/workflows/refresh.yml).
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strava_client import StravaClient
from points import PointsEngine

OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")
ARCHIVE_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "activities_archive.json")


def fingerprint(a: dict) -> str:
    """Stable unique key for an activity (no ID exposed by club endpoint)."""
    athlete = a.get("athlete", {})
    key = "|".join([
        athlete.get("firstname", ""),
        athlete.get("lastname", ""),
        a.get("name", ""),
        str(a.get("distance", 0)),
        str(a.get("moving_time", 0)),
        a.get("sport_type", "") or a.get("type", ""),
    ])
    return hashlib.md5(key.encode()).hexdigest()


def load_archive() -> dict:
    """Load existing archive, or return an empty one."""
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"fingerprints": [], "activities": []}


def merge_archive(archive: dict, fetched: list[dict]) -> int:
    """
    Prepend any new activities to the archive.

    Walks fetched activities newest-first and stops as soon as it hits
    a fingerprint already in the archive — this prevents pre-competition
    activities from ever being added.

    Returns the number of newly added activities.
    """
    known = set(archive["fingerprints"])
    new_activities = []
    new_fingerprints = []

    for activity in fetched:
        fp = fingerprint(activity)
        if fp in known:
            # Reached activities we've already archived — stop here
            break
        new_activities.append(activity)
        new_fingerprints.append(fp)

    if new_activities:
        archive["activities"]    = new_activities + archive["activities"]
        archive["fingerprints"]  = new_fingerprints + archive["fingerprints"]

    return len(new_activities)


def save_archive(archive: dict):
    os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def main():
    print("Loading activity archive...")
    archive = load_archive()
    print(f"  → {len(archive['activities'])} activities in archive")

    print("Fetching latest club activities from Strava...")
    client = StravaClient()
    fetched = client.get_club_activities()
    print(f"  → {len(fetched)} activities fetched")

    new_count = merge_archive(archive, fetched)
    print(f"  → {new_count} new activities added to archive")
    save_archive(archive)
    print(f"  → Archive now holds {len(archive['activities'])} activities total")

    print("Calculating points...")
    engine = PointsEngine()
    data = engine.process(archive["activities"])

    leaderboard = data["leaderboard"]
    print(f"  → {len(leaderboard)} athletes on the leaderboard")
    for entry in leaderboard:
        print(f"     #{entry['rank']} {entry['name']}  —  {entry['total_points']} pts")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nData written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
