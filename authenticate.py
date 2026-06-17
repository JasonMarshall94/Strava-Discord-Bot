"""
One-time Strava OAuth authorization for the bot account.

Run this script once after `python setup_db.py` to authorize the bot's
Strava account. Tokens are stored in the encrypted DB and refreshed
automatically by the bot at runtime.

    python authenticate.py
"""

import asyncio
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import aiohttp

import config

SCOPE = "read,activity:read_all"
REDIRECT_URI = "http://localhost:8080/callback"

_auth_code: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            _auth_code = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Authorization complete. You can close this tab and return to the terminal.")

    def log_message(self, format, *args):
        pass  # suppress request logs


async def exchange_code(code: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            config.STRAVA_TOKEN_URL,
            data={
                "client_id": config.STRAVA_CLIENT_ID,
                "client_secret": config.STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Token exchange failed ({resp.status}): {text}")
            return await resp.json()


async def main():
    if not config.STRAVA_CLIENT_ID or not config.STRAVA_CLIENT_SECRET:
        print("ERROR: STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET are not set.")
        print("Run `python setup_db.py` first.")
        sys.exit(1)

    auth_url = (
        "https://www.strava.com/oauth/authorize"
        f"?client_id={config.STRAVA_CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        "&response_type=code"
        f"&scope={SCOPE}"
        "&approval_prompt=auto"
    )

    print("Starting local callback server on http://localhost:8080 ...")
    server = HTTPServer(("localhost", 8080), _CallbackHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("\nOpening Strava authorization in your browser...")
    print(f"If it doesn't open automatically, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for authorization...")
    while _auth_code is None:
        await asyncio.sleep(0.5)

    server.shutdown()

    print("Code received. Exchanging for tokens...")
    token_data = await exchange_code(_auth_code)

    config.store.set_bot_token(
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
        expires_at=token_data["expires_at"],
    )

    athlete = token_data.get("athlete", {})
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    print(f"\n✅ Strava connected! Authorized as: {name or 'Unknown athlete'}")
    print("Tokens stored in cgrc.db. The bot will refresh them automatically.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
