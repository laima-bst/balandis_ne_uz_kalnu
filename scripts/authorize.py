"""
One-time OAuth setup script.

Run this once from your machine to get an access token + refresh token:

    python scripts/authorize.py

It will open your browser, ask you to authorize the Strava app, then save
the tokens to your .env file. You never need to run this again — tokens
are refreshed automatically.

Prerequisites:
  1. Create a Strava API app at https://www.strava.com/settings/api
     - Set "Authorization Callback Domain" to: localhost
  2. Copy .env.example to .env and fill in CLIENT_ID and CLIENT_SECRET.
"""

import sys
import os

# Make sure the project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from strava_client import StravaAuth


def main():
    print("=== Strava OAuth Setup ===")
    auth = StravaAuth()
    auth.run_initial_auth()


if __name__ == "__main__":
    main()
