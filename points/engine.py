"""
Points engine: applies rules.yaml to a list of Strava club activities
and returns per-athlete leaderboard data.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import yaml

RULES_FILE = os.path.join(os.path.dirname(__file__), "rules.yaml")

# Strava reports swim distance in metres, everything else in metres too —
# but swim pace is very different so it gets its own per_km rate.
# No special unit conversion needed; we just divide by 1000 for km.
SWIM_TYPE = "Swim"


class PointsEngine:
    def __init__(self, rules_path: str = RULES_FILE):
        with open(rules_path) as f:
            self.rules = yaml.safe_load(f)

        comp = self.rules["competition"]
        self.start = datetime.fromisoformat(comp["start_date"]).replace(
            tzinfo=timezone.utc
        )
        self.end = datetime.fromisoformat(comp["end_date"]).replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def process(self, activities: list[dict]) -> dict[str, Any]:
        """
        Process a list of raw Strava club activities.

        Returns a dict with:
          competition   – metadata (name, dates)
          leaderboard   – list of athletes sorted by total points (desc)
          activities    – all scored activities (for an activity feed)
          generated_at  – ISO timestamp
        """
        scored = [self._score(a) for a in activities]
        scored = [a for a in scored if a is not None]  # filter excluded

        # Aggregate per athlete
        athletes: dict[str, dict] = {}
        for activity in scored:
            key = activity["athlete_key"]
            if key not in athletes:
                athletes[key] = {
                    "name": activity["athlete_name"],
                    "total_points": 0,
                    "activity_count": 0,
                    "total_distance_km": 0.0,
                    "total_elevation_m": 0.0,
                    "by_type": {},
                }
            a = athletes[key]
            a["total_points"] += activity["points"]
            a["activity_count"] += 1
            a["total_distance_km"] += activity["distance_km"]
            a["total_elevation_m"] += activity["elevation_m"]

            sport = activity["sport_type"]
            if sport not in a["by_type"]:
                a["by_type"][sport] = {"count": 0, "points": 0, "distance_km": 0.0}
            a["by_type"][sport]["count"] += 1
            a["by_type"][sport]["points"] += activity["points"]
            a["by_type"][sport]["distance_km"] += activity["distance_km"]

        # Build set of all assigned athlete keys from teams config
        teams_config = self.rules.get("teams", [])
        assigned_keys = {
            m.lower().replace(" ", "_")
            for team in teams_config
            for m in team.get("members", [])
        }

        # If teams are defined, only include assigned athletes in the leaderboard
        athletes_to_rank = {
            k: v for k, v in athletes.items()
            if not assigned_keys or k in assigned_keys
        }

        leaderboard = sorted(
            athletes_to_rank.values(), key=lambda x: x["total_points"], reverse=True
        )
        # Add rank
        for i, entry in enumerate(leaderboard, start=1):
            entry["rank"] = i
            entry["total_points"] = round(entry["total_points"], 1)
            entry["total_distance_km"] = round(entry["total_distance_km"], 2)
            entry["total_elevation_m"] = round(entry["total_elevation_m"], 0)

        # Filter activities to assigned athletes only, then sort newest-first
        scored = [a for a in scored if not assigned_keys or a["athlete_key"] in assigned_keys]
        scored.sort(key=lambda a: a["start_date"] or "", reverse=True)

        # Aggregate per team
        teams_config = self.rules.get("teams", [])
        team_totals = []
        for team in teams_config:
            team_name = team["name"]
            member_keys = {m.lower().replace(" ", "_") for m in team.get("members", [])}
            team_points = 0.0
            team_distance = 0.0
            team_activities = 0
            team_members = []
            for athlete in athletes.values():
                key = athlete["name"].lower().replace(" ", "_")
                if key in member_keys:
                    team_points += athlete["total_points"]
                    team_distance += athlete["total_distance_km"]
                    team_activities += athlete["activity_count"]
                    team_members.append(athlete["name"])
            team_totals.append({
                "name": team_name,
                "total_points": round(team_points, 1),
                "total_distance_km": round(team_distance, 2),
                "activity_count": team_activities,
                "members": team_members,
            })
        team_totals.sort(key=lambda t: t["total_points"], reverse=True)
        for i, t in enumerate(team_totals, start=1):
            t["rank"] = i

        # Build daily team rankings (cumulative, using _fetched_date)
        daily_rankings = []
        all_dates = sorted({
            a["_fetched_date"] for a in scored if a.get("_fetched_date")
        })
        if all_dates:
            for day in all_dates:
                # Cumulative: all scored activities up to and including this day
                acts_to_day = [a for a in scored if (a.get("_fetched_date") or "") <= day]
                day_team_points: dict[str, float] = {}
                for team in teams_config:
                    team_name = team["name"]
                    member_keys = {m.lower().replace(" ", "_") for m in team.get("members", [])}
                    day_team_points[team_name] = round(
                        sum(a["points"] for a in acts_to_day if a["athlete_key"] in member_keys), 1
                    )
                ranked_teams = sorted(day_team_points.items(), key=lambda x: x[1], reverse=True)
                daily_rankings.append({
                    "date": day,
                    "rankings": {name: i + 1 for i, (name, _) in enumerate(ranked_teams)},
                    "points": dict(ranked_teams),
                })

        comp = self.rules["competition"]
        return {
            "competition": {
                "name": comp["name"],
                "start_date": comp["start_date"],
                "end_date": comp["end_date"],
            },
            "teams": team_totals,
            "daily_rankings": daily_rankings,
            "leaderboard": leaderboard,
            "activities": scored,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score(self, raw: dict) -> dict | None:
        """Score a single activity. Returns None if the activity is excluded."""
        sport_type = raw.get("sport_type") or raw.get("type", "")
        included = self.rules.get("included_activity_types", [])
        if sport_type not in included:
            return None

        # Date filter (club activities endpoint does not return dates,
        # so we skip this check when the field is absent)
        start_date_str = raw.get("start_date_local") or raw.get("start_date", "")
        start_date = None
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(
                    start_date_str.replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        if start_date is not None and not (self.start <= start_date <= self.end):
            return None

        # Minimum duration filter
        moving_time = raw.get("moving_time", 0)
        min_dur = self.rules.get("min_duration_seconds", 0)
        if moving_time < min_dur:
            return None

        # Distance (always in metres from Strava)
        distance_m = raw.get("distance", 0)
        distance_km = distance_m / 1000.0

        # Elevation
        elevation_m = raw.get("total_elevation_gain", 0) or 0

        # Points calculation
        rates = self.rules.get("points_per_km", {})
        rate = rates.get(sport_type, rates.get("default", 0))
        points = distance_km * rate

        elev_bonus_per_100m = self.rules.get("elevation_bonus_per_100m", 0)
        if elev_bonus_per_100m:
            points += (elevation_m / 100.0) * elev_bonus_per_100m

        cap = self.rules.get("max_points_per_activity")
        if cap is not None:
            points = min(points, cap)

        athlete = raw.get("athlete", {})
        firstname = athlete.get("firstname", "")
        lastname = athlete.get("lastname", "")
        athlete_name = f"{firstname} {lastname}".strip() or "Unknown"
        # Use name as key since club activities don't expose athlete ID
        athlete_key = athlete_name.lower().replace(" ", "_")

        return {
            "athlete_key": athlete_key,
            "athlete_name": athlete_name,
            "name": raw.get("name", ""),
            "sport_type": sport_type,
            "start_date": start_date_str or None,
            "_fetched_date": raw.get("_fetched_date"),
            "distance_km": round(distance_km, 2),
            "elevation_m": round(elevation_m, 1),
            "moving_time_s": moving_time,
            "points": round(points, 1),
        }
