"""
Run this to move the bot to a different Discord server without touching
any miles data, member data, or Strava config.

    python update_server.py
"""

from db.store import ConfigStore


def main():
    store = ConfigStore()

    current_guild = store.get("DISCORD_GUILD_ID", "not set")
    current_channel = store.get("NOTIFY_CHANNEL_ID", "not set")

    print("=== Update Discord Server ===\n")
    print(f"  Current guild ID:   {current_guild}")
    print(f"  Current channel ID: {current_channel}\n")

    guild_id = input("New Discord guild/server ID: ").strip()
    if not guild_id:
        print("No guild ID entered — nothing changed.")
        return

    store.set("DISCORD_GUILD_ID", guild_id)
    store.set("NOTIFY_CHANNEL_ID", "")

    print(f"\n  ✓ Guild ID updated to {guild_id}")
    print("  ✓ Notify channel cleared — run /notify setchannel in the new server")
    print("\nRestart the bot and run /notify setchannel in your new Discord server.")

    store.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
