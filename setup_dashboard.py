"""
Set up dashboard login credentials. Run once before starting the dashboard.

    python setup_dashboard.py
"""

import getpass
import secrets
import sys

from dashboard.auth import hash_password
from db.store import ConfigStore


def main():
    store = ConfigStore()
    print("=== CGRC Dashboard — credential setup ===\n")

    current = store.get("DASHBOARD_USERNAME")
    if current:
        print(f"  Existing username: {current}")
        if input("  Overwrite? [y/N]: ").strip().lower() != "y":
            print("Aborted.")
            return

    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)
    if getpass.getpass("Confirm password: ") != password:
        print("Passwords do not match.")
        sys.exit(1)

    store.set("DASHBOARD_USERNAME", username)
    store.set("DASHBOARD_PASSWORD_HASH", hash_password(password))

    if not store.get("DASHBOARD_SESSION_SECRET"):
        store.set("DASHBOARD_SESSION_SECRET", secrets.token_hex(32))

    print("\n  ✓ Credentials saved")
    print("  ✓ Session secret generated")
    print("\nStart the dashboard with:")
    print("  uvicorn dashboard.app:app --host 0.0.0.0 --port 8000")
    store.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
