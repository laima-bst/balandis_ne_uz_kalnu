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
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strava_client import StravaClient
from points import PointsEngine

OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")
ARCHIVE_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "activities_archive.json")


def fingerprint(a: dict) -> str:
    """Stable unique key for an activity (no ID exposed by club endpoint).
    Name is intentionally excluded so renamed activities are not double-counted.
    """
    athlete = a.get("athlete", {})
    key = "|".join([
        athlete.get("firstname", ""),
        athlete.get("lastname", ""),
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
    return {"fingerprints": [], "activities": [], "run_log": []}


def merge_archive(archive: dict, fetched: list[dict]) -> int:
    """
    Prepend any new activities to the archive.

    Finds the deepest position of any known activity in the fetched list,
    then adds all unknown activities that appear before that position.
    This handles cases where new activities are interspersed among known
    ones (e.g. late Strava syncs), while still preventing pre-competition
    activities (which sit below all known ones) from ever being added.

    Returns the number of newly added activities.
    """
    known = set(archive["fingerprints"])

    # Find the index of the deepest known activity in the fetched list
    last_known_pos = -1
    fps = [fingerprint(a) for a in fetched]
    for i, fp in enumerate(fps):
        if fp in known:
            last_known_pos = i

    if last_known_pos == -1:
        # No known activities found at all — don't add anything (safety guard)
        return 0

    # Add all unknown activities that appear before the last known position
    today = date.today().isoformat()
    new_activities = []
    new_fingerprints = []

    for i, activity in enumerate(fetched[:last_known_pos]):
        fp = fps[i]
        if fp not in known:
            activity["_fetched_date"] = today
            new_activities.append(activity)
            new_fingerprints.append(fp)

    if new_activities:
        archive["activities"]   = new_activities + archive["activities"]
        archive["fingerprints"] = new_fingerprints + archive["fingerprints"]

    return new_activities


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

    new_activities = merge_archive(archive, fetched)
    new_count = len(new_activities)
    print(f"  → {new_count} new activities added to archive")

    # Build run log entry
    run_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "new_count": new_count,
        "activities": [
            {
                "athlete": f"{a.get('athlete', {}).get('firstname', '')} {a.get('athlete', {}).get('lastname', '')}".strip(),
                "sport":   a.get("sport_type", ""),
                "distance_km": round(a.get("distance", 0) / 1000, 2),
                "name":    a.get("name", ""),
            }
            for a in new_activities
        ],
    }
    if "run_log" not in archive:
        archive["run_log"] = []
    archive["run_log"].insert(0, run_entry)
    archive["run_log"] = archive["run_log"][:50]  # keep last 50 runs

    save_archive(archive)
    print(f"  → Archive now holds {len(archive['activities'])} activities total")

    print("Calculating points...")
    engine = PointsEngine()
    data = engine.process(archive["activities"])
    data["run_log"] = archive["run_log"]

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
