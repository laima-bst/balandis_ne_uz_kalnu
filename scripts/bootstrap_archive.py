"""
One-time bootstrap: seed the activity archive with the first N activities.

Run this once at the start of the competition to capture the opening
activities before the rolling 200-activity window moves on.

Usage:
    python scripts/bootstrap_archive.py --count 20
"""

import json
import os
import sys
import hashlib
import argparse
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strava_client import StravaClient

ARCHIVE_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "activities_archive.json")


def fingerprint(a: dict) -> str:
    """Stable unique key for an activity (no ID available from club endpoint).
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


def main():
    parser = argparse.ArgumentParser(description="Seed the activity archive.")
    parser.add_argument(
        "--count", type=int, required=True,
        help="Number of activities to include, counted newest-first (e.g. 20)"
    )
    args = parser.parse_args()

    print("Fetching club activities...")
    client = StravaClient()
    activities = client.get_club_activities()
    print(f"  → {len(activities)} fetched")

    selected = activities[: args.count]
    today = date.today().isoformat()
    for a in selected:
        a["_fetched_date"] = today

    archive = {
        "fingerprints": [fingerprint(a) for a in selected],
        "activities": selected,
    }

    os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    print(f"  → Archive seeded with {len(selected)} activities")
    print(f"  → Saved to {ARCHIVE_FILE}")


if __name__ == "__main__":
    main()
