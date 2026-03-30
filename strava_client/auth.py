"""
Strava OAuth2 authentication and token management.

Flow:
  1. Run scripts/authorize.py once to get initial tokens via browser.
  2. Tokens are saved to .env and auto-refreshed on every subsequent run.
"""

import os
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv, set_key

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "read,activity:read"

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")


class StravaAuth:
    def __init__(self):
        load_dotenv(ENV_FILE)
        self.client_id = os.environ["STRAVA_CLIENT_ID"]
        self.client_secret = os.environ["STRAVA_CLIENT_SECRET"]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_valid_access_token(self) -> str:
        """Return a valid access token, refreshing it if expired."""
        expires_at = float(os.environ.get("STRAVA_TOKEN_EXPIRES_AT", 0))
        if time.time() >= expires_at - 60:
            self._refresh_tokens()
        return os.environ["STRAVA_ACCESS_TOKEN"]

    # ------------------------------------------------------------------
    # Initial authorization (run once via scripts/authorize.py)
    # ------------------------------------------------------------------

    def run_initial_auth(self):
        """Open a browser for the user to authorize, capture the code via a
        local callback server, then exchange it for tokens."""
        auth_url = (
            f"{AUTHORIZE_URL}"
            f"?client_id={self.client_id}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&response_type=code"
            f"&approval_prompt=auto"
            f"&scope={SCOPES}"
        )
        print(f"\nOpening browser for Strava authorization...")
        print(f"If it doesn't open automatically, visit:\n  {auth_url}\n")
        webbrowser.open(auth_url)

        code = self._wait_for_callback()
        self._exchange_code(code)
        print("\nAuthorization successful! Tokens saved to .env")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _wait_for_callback(self) -> str:
        """Start a temporary local HTTP server and wait for the OAuth callback."""
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = parse_qs(urlparse(self.path).query)
                if "code" in query:
                    captured["code"] = query["code"][0]
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"<h2>Authorization successful! You can close this tab.</h2>")
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"<h2>Authorization failed. No code received.</h2>")

            def log_message(self, *args):
                pass  # suppress server logs

        server = HTTPServer(("localhost", 8080), Handler)
        print("Waiting for Strava to redirect back... (listening on localhost:8080)")
        server.handle_request()
        server.server_close()

        if "code" not in captured:
            raise RuntimeError("Did not receive an authorization code from Strava.")
        return captured["code"]

    def _exchange_code(self, code: str):
        resp = requests.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        self._save_tokens(resp.json())

    def _refresh_tokens(self):
        refresh_token = os.environ.get("STRAVA_REFRESH_TOKEN")
        if not refresh_token:
            raise RuntimeError(
                "No refresh token found. Run scripts/authorize.py first."
            )
        resp = requests.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })
        resp.raise_for_status()
        self._save_tokens(resp.json())

    def _save_tokens(self, token_data: dict):
        env_path = os.path.abspath(ENV_FILE)
        set_key(env_path, "STRAVA_ACCESS_TOKEN", token_data["access_token"])
        set_key(env_path, "STRAVA_REFRESH_TOKEN", token_data["refresh_token"])
        set_key(env_path, "STRAVA_TOKEN_EXPIRES_AT", str(token_data["expires_at"]))
        # Also update the running process environment
        os.environ["STRAVA_ACCESS_TOKEN"] = token_data["access_token"]
        os.environ["STRAVA_REFRESH_TOKEN"] = token_data["refresh_token"]
        os.environ["STRAVA_TOKEN_EXPIRES_AT"] = str(token_data["expires_at"])
