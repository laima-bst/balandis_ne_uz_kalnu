"""
Main pipeline: fetch club activities from Strava → calculate points → write docs/data.json

Run locally:
    python scripts/fetch_and_update.py

Or automatically via GitHub Actions (see .github/workflows/refresh.yml).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strava_client import StravaClient
from points import PointsEngine

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")


def main():
    print("Fetching club activities from Strava...")
    client = StravaClient()
    activities = client.get_club_activities()
    print(f"  → {len(activities)} activities fetched")

    print("Calculating points...")
    engine = PointsEngine()
    data = engine.process(activities)

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
