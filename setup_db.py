"""
Interactive setup script — run once to initialise the encrypted config database.

    python setup_db.py

After setup, run `python authenticate.py` to connect the bot's Strava account.
"""

import json
import sys
from pathlib import Path

from dotenv import dotenv_values

from db.store import ConfigStore

ENV_PATH = Path(".env")
MEMBERS_PATH = Path("members.json")

REQUIRED_KEYS = [
    ("DISCORD_TOKEN", "Discord bot token"),
    (
        "DISCORD_GUILD_ID",
        "Discord guild/server ID (leave blank for global slash commands)",
    ),
    ("STRAVA_CLIENT_ID", "Strava application Client ID"),
    ("STRAVA_CLIENT_SECRET", "Strava application Client Secret"),
    ("STRAVA_CLUB_ID", "Strava Club ID"),
]

OPTIONAL_KEYS = [
    ("LOG_LEVEL", "Log level (DEBUG/INFO/WARNING/ERROR)", "INFO"),
]


def prompt(label: str, default: str | None, required: bool) -> str | None:
    suffix = (
        f" [{default}]"
        if default
        else (" (required)" if required else " (optional, Enter to skip)")
    )
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        if not required:
            return None
        print("  This field is required.")


def seed_members(store: ConfigStore) -> None:
    if not MEMBERS_PATH.exists():
        print(f"\n  No {MEMBERS_PATH} found — skipping member seeding.")
        print(f"  Copy members.example.json → members.json, fill in your club members,")
        print(f"  then re-run this script to seed them.")
        return

    with open(MEMBERS_PATH) as f:
        data = json.load(f)

    members = data.get("members", [])
    print(f"\n  Seeding {len(members)} member(s) from {MEMBERS_PATH}...")
    for m in members:
        store.set_member(
            strava_athlete_id=m["strava_athlete_id"],
            display_name=m["display_name"],
            message=m["message"],
            strava_firstname=m.get("strava_firstname", ""),
            strava_lastname=m.get("strava_lastname", ""),
        )
        print(f"    ✓ {m['display_name']} (athlete ID: {m['strava_athlete_id']})")


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

    seed_members(store)

    print("\nSetup complete. Config stored in cgrc.db (encrypted).")
    print("Keep secret.key safe — losing it means losing access to your config.")
    print("\nNext step: run `python authenticate.py` to connect your Strava account.")

    if ENV_PATH.exists():
        ans = (
            input("\nDelete .env now that values are in the database? [y/N]: ")
            .strip()
            .lower()
        )
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
