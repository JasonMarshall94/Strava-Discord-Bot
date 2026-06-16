"""
Bot configuration — all secrets are loaded from the encrypted SQLite store.
Run `python setup_db.py` once to populate the database before starting the bot.
"""

from db.store import ConfigStore

# Shared store instance used across the application
store = ConfigStore()


def _get(key: str, default: str | None = None) -> str | None:
    return store.get(key, default)


DISCORD_TOKEN = _get("DISCORD_TOKEN")
DISCORD_GUILD_ID = int(_get("DISCORD_GUILD_ID", "0")) or None

STRAVA_CLIENT_ID = _get("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = _get("STRAVA_CLIENT_SECRET")
STRAVA_REDIRECT_URI = _get("STRAVA_REDIRECT_URI", "http://localhost:8080/callback")
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_WEBHOOK_VERIFY_TOKEN = _get("STRAVA_WEBHOOK_VERIFY_TOKEN")

WEBHOOK_HOST = _get("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(_get("WEBHOOK_PORT", "8080"))

LOG_LEVEL = _get("LOG_LEVEL", "INFO")
