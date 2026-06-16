"""
Interactive setup script — run once to initialise the encrypted config database.

    python setup_db.py

If a .env file is present its values are offered as defaults. Each key can be
confirmed with Enter or overridden by typing a new value. Blank input on an
optional key skips it.
"""

import os
import sys
from pathlib import Path
from dotenv import dotenv_values
from db.store import ConfigStore

ENV_PATH = Path(".env")

REQUIRED_KEYS = [
    ("DISCORD_TOKEN",        "Discord bot token"),
    ("DISCORD_GUILD_ID",     "Discord guild/server ID (leave blank for global slash commands)"),
    ("STRAVA_CLIENT_ID",     "Strava application Client ID"),
    ("STRAVA_CLIENT_SECRET", "Strava application Client Secret"),
]

OPTIONAL_KEYS = [
    ("STRAVA_REDIRECT_URI",          "Strava OAuth redirect URI",                    "http://localhost:8080/callback"),
    ("STRAVA_WEBHOOK_VERIFY_TOKEN",  "Strava webhook verify token (choose any secret string)", None),
    ("WEBHOOK_HOST",                 "Webhook server host",                          "0.0.0.0"),
    ("WEBHOOK_PORT",                 "Webhook server port",                          "8080"),
    ("LOG_LEVEL",                    "Log level (DEBUG/INFO/WARNING/ERROR)",          "INFO"),
]


def prompt(label: str, default: str | None, required: bool) -> str | None:
    suffix = f" [{default}]" if default else (" (required)" if required else " (optional, Enter to skip)")
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        if not required:
            return None
        print("  This field is required.")


def main():
    print("=== CGRC Bot — encrypted config setup ===\n")

    env_defaults = dict(dotenv_values(ENV_PATH)) if ENV_PATH.exists() else {}
    if env_defaults:
        print(f"Found .env at {ENV_PATH} — values will be used as defaults.\n")

    store = ConfigStore()

    for key, label in REQUIRED_KEYS:
        value = prompt(label, env_defaults.get(key) or store.get(key), required=True)
        store.set(key, value)
        print(f"  ✓ {key} saved\n")

    for key, label, fallback in OPTIONAL_KEYS:
        default = env_defaults.get(key) or store.get(key) or fallback
        value = prompt(label, default, required=False)
        if value:
            store.set(key, value)
            print(f"  ✓ {key} saved\n")
        else:
            print(f"  – {key} skipped\n")

    print("Setup complete. Config stored in cgrc.db (encrypted).")
    print("Keep secret.key safe — losing it means losing access to your config.")

    if ENV_PATH.exists():
        ans = input("\nDelete .env now that values are in the database? [y/N]: ").strip().lower()
        if ans == "y":
            ENV_PATH.unlink()
            print(".env deleted.")

    store.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
