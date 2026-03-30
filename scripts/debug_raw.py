"""Prints the first 3 raw activities from Strava so we can inspect field names."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from strava_client import StravaClient

client = StravaClient()
activities = client.get_club_activities()
print(f"Total fetched: {len(activities)}\n")
for a in activities[:3]:
    print(json.dumps(a, indent=2))
    print("---")
