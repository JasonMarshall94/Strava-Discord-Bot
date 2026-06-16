"""
Encrypted SQLite config and token store.

All values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before being
written to the database. The master key lives in `secret.key` (or the path set
by the CGRC_KEY_FILE env var). If the key file does not exist on first run a
new key is generated and saved there automatically.
"""

import os
import sqlite3
import logging
from pathlib import Path
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).parent.parent / "cgrc.db"
DEFAULT_KEY_PATH = Path(__file__).parent.parent / "secret.key"


def _load_or_create_key(key_path: Path) -> bytes:
    if key_path.exists():
        return key_path.read_bytes().strip()
    logger.info(f"No key file found at {key_path} — generating a new one.")
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    logger.info(f"New encryption key saved to {key_path}. Back this file up securely.")
    return key


class ConfigStore:
    """Thread-safe, encrypted SQLite store for bot config and Strava tokens."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        key_path: Path | str | None = None,
    ):
        self._db_path = Path(db_path or os.getenv("CGRC_DB_PATH", DEFAULT_DB_PATH))
        key_path = Path(key_path or os.getenv("CGRC_KEY_FILE", DEFAULT_KEY_PATH))
        self._fernet = Fernet(_load_or_create_key(key_path))
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS config (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS strava_tokens (
                discord_user_id  INTEGER PRIMARY KEY,
                access_token     TEXT NOT NULL,
                refresh_token    TEXT NOT NULL,
                expires_at       INTEGER NOT NULL,
                updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
            );

            -- Maps a Strava athlete ID to a Discord user ID so incoming
            -- webhook events can be routed to the right Discord member.
            CREATE TABLE IF NOT EXISTS strava_athletes (
                strava_athlete_id  INTEGER PRIMARY KEY,
                discord_user_id    INTEGER NOT NULL UNIQUE
            );


        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    def _encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()

    # ------------------------------------------------------------------
    # Config key/value API
    # ------------------------------------------------------------------

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM config WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        return self._decrypt(row["value"])

    def set(self, key: str, value: str) -> None:
        encrypted = self._encrypt(value)
        self._conn.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, encrypted),
        )
        self._conn.commit()

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM config WHERE key = ?", (key,))
        self._conn.commit()

    def all_keys(self) -> list[str]:
        rows = self._conn.execute("SELECT key FROM config ORDER BY key").fetchall()
        return [r["key"] for r in rows]

    # ------------------------------------------------------------------
    # Strava token API
    # ------------------------------------------------------------------

    def get_strava_token(self, discord_user_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM strava_tokens WHERE discord_user_id = ?",
            (discord_user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "access_token": self._decrypt(row["access_token"]),
            "refresh_token": self._decrypt(row["refresh_token"]),
            "expires_at": row["expires_at"],
        }

    def set_strava_token(
        self,
        discord_user_id: int,
        access_token: str,
        refresh_token: str,
        expires_at: int,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO strava_tokens
                (discord_user_id, access_token, refresh_token, expires_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(discord_user_id) DO UPDATE SET
                access_token  = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at    = excluded.expires_at,
                updated_at    = excluded.updated_at
            """,
            (
                discord_user_id,
                self._encrypt(access_token),
                self._encrypt(refresh_token),
                expires_at,
            ),
        )
        self._conn.commit()

    def delete_strava_token(self, discord_user_id: int) -> None:
        self._conn.execute(
            "DELETE FROM strava_tokens WHERE discord_user_id = ?", (discord_user_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Strava athlete ↔ Discord user mapping
    # ------------------------------------------------------------------

    def set_athlete_map(self, strava_athlete_id: int, discord_user_id: int) -> None:
        self._conn.execute(
            """
            INSERT INTO strava_athletes (strava_athlete_id, discord_user_id)
            VALUES (?, ?)
            ON CONFLICT(strava_athlete_id) DO UPDATE SET
                discord_user_id = excluded.discord_user_id
            """,
            (strava_athlete_id, discord_user_id),
        )
        self._conn.commit()

    def get_discord_user_for_athlete(self, strava_athlete_id: int) -> int | None:
        row = self._conn.execute(
            "SELECT discord_user_id FROM strava_athletes WHERE strava_athlete_id = ?",
            (strava_athlete_id,),
        ).fetchone()
        return row["discord_user_id"] if row else None

    def get_athlete_id_for_discord_user(self, discord_user_id: int) -> int | None:
        row = self._conn.execute(
            "SELECT strava_athlete_id FROM strava_athletes WHERE discord_user_id = ?",
            (discord_user_id,),
        ).fetchone()
        return row["strava_athlete_id"] if row else None

    def close(self) -> None:
        self._conn.close()
