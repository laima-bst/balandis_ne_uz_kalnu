"""
Strava API client.

Covers everything needed for the competition dashboard:
  - Club activities (the main data source)
  - Club member list
  - Individual athlete info (for display names / avatars)
"""

import os
import time
from typing import Iterator

import requests
from dotenv import load_dotenv

from .auth import StravaAuth

BASE_URL = "https://www.strava.com/api/v3"
# Strava rate limits: 100 requests / 15 min, 1000 / day
_REQUEST_DELAY = 0.2  # seconds between requests (conservative)

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")


class StravaClient:
    def __init__(self):
        load_dotenv(ENV_FILE)
        self.club_id = os.environ["STRAVA_CLUB_ID"]
        self._auth = StravaAuth()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_club_activities(self, per_page: int = 200) -> list[dict]:
        """
        Fetch recent activities for all members of the club.

        Strava's club activities endpoint returns up to 200 activities per
        page and does NOT support filtering by date on the API side — we do
        that in the pipeline. Pagination is supported but Strava caps the
        total depth at ~200 activities for clubs, so one page is usually
        sufficient.

        Fields returned per activity:
          athlete: {firstname, lastname}
          name, distance, moving_time, elapsed_time,
          total_elevation_gain, type, sport_type,
          workout_type, start_date_local
        """
        activities = []
        page = 1
        while True:
            batch = self._get(
                f"/clubs/{self.club_id}/activities",
                params={"per_page": per_page, "page": page},
            )
            if not batch:
                break
            activities.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
            time.sleep(_REQUEST_DELAY)
        return activities

    def get_club_members(self) -> list[dict]:
        """Return all members of the club."""
        members = []
        page = 1
        per_page = 200
        while True:
            batch = self._get(
                f"/clubs/{self.club_id}/members",
                params={"per_page": per_page, "page": page},
            )
            if not batch:
                break
            members.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
            time.sleep(_REQUEST_DELAY)
        return members

    def get_authenticated_athlete(self) -> dict:
        """Return profile of the authenticated athlete (the app owner)."""
        return self._get("/athlete")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        token = self._auth.get_valid_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(BASE_URL + path, headers=headers, params=params or {})

        if resp.status_code == 429:
            # Rate limited — surface a clear error rather than silently failing
            raise RuntimeError(
                "Strava rate limit hit (429). Wait 15 minutes and try again."
            )
        resp.raise_for_status()
        return resp.json()
