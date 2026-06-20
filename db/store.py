"""
Encrypted SQLite config and token store.

All sensitive values (tokens, secrets) are encrypted with Fernet
(AES-128-CBC + HMAC-SHA256) before being written to the database.
The master key lives in `secret.key` (or the path set by the CGRC_KEY_FILE
env var). If the key file does not exist on first run a new key is generated
and saved there automatically.
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

            -- Club members. strava_firstname/lastname are matched against the
            -- Strava API athlete object (e.g. firstname="Jason", lastname="M.").
            CREATE TABLE IF NOT EXISTS members (
                strava_athlete_id  INTEGER PRIMARY KEY,
                display_name       TEXT NOT NULL,
                strava_firstname   TEXT NOT NULL DEFAULT '',
                strava_lastname    TEXT NOT NULL DEFAULT '',
                message            TEXT NOT NULL
            );

            -- One row per processed run. Deduplication key is
            -- (firstname, lastname, moving_time, distance_m) since the Strava
            -- club activities endpoint returns no activity ID or start date.
            -- logged_at is used for year scoping in leaderboard queries.
            CREATE TABLE IF NOT EXISTS run_log (
                strava_firstname  TEXT NOT NULL,
                strava_lastname   TEXT NOT NULL,
                moving_time       INTEGER NOT NULL,
                distance_m        INTEGER NOT NULL,
                distance_miles    REAL NOT NULL,
                logged_at         TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (strava_firstname, strava_lastname, moving_time, distance_m)
            );
        """)

        # Add name columns if upgrading from old schema
        for col, definition in [
            ("strava_firstname", "TEXT NOT NULL DEFAULT ''"),
            ("strava_lastname",  "TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                self._conn.execute(f"ALTER TABLE members ADD COLUMN {col} {definition}")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

        # Replace old run_log schema (had strava_athlete_id + start_date PK)
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(run_log)").fetchall()
        }
        if "strava_athlete_id" in cols:
            self._conn.executescript("""
                DROP TABLE run_log;
                CREATE TABLE run_log (
                    strava_firstname  TEXT NOT NULL,
                    strava_lastname   TEXT NOT NULL,
                    moving_time       INTEGER NOT NULL,
                    distance_m        INTEGER NOT NULL,
                    distance_miles    REAL NOT NULL,
                    logged_at         TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (strava_firstname, strava_lastname, moving_time, distance_m)
                );
            """)
            self._conn.commit()

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
    # Strava bot token (single bot account, refreshed automatically)
    # ------------------------------------------------------------------

    def get_bot_token(self) -> dict | None:
        access = self.get("STRAVA_ACCESS_TOKEN")
        refresh = self.get("STRAVA_REFRESH_TOKEN")
        expires = self.get("STRAVA_TOKEN_EXPIRES_AT")
        if not access or not refresh or not expires:
            return None
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_at": int(expires),
        }

    def set_bot_token(self, access_token: str, refresh_token: str, expires_at: int) -> None:
        self.set("STRAVA_ACCESS_TOKEN", access_token)
        self.set("STRAVA_REFRESH_TOKEN", refresh_token)
        self.set("STRAVA_TOKEN_EXPIRES_AT", str(expires_at))

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    def get_all_members(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM members ORDER BY display_name"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_member_by_strava_name(self, firstname: str, lastname: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM members WHERE strava_firstname = ? AND strava_lastname = ?",
            (firstname, lastname),
        ).fetchone()
        return dict(row) if row else None

    def get_member(self, strava_athlete_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM members WHERE strava_athlete_id = ?",
            (strava_athlete_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_member(
        self,
        strava_athlete_id: int,
        display_name: str,
        message: str,
        strava_firstname: str = "",
        strava_lastname: str = "",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO members
                (strava_athlete_id, display_name, strava_firstname, strava_lastname, message)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(strava_athlete_id) DO UPDATE SET
                display_name     = excluded.display_name,
                strava_firstname = excluded.strava_firstname,
                strava_lastname  = excluded.strava_lastname,
                message          = excluded.message
            """,
            (strava_athlete_id, display_name, strava_firstname, strava_lastname, message),
        )
        self._conn.commit()

    def update_member(self, strava_athlete_id: int, display_name: str, message: str) -> None:
        self._conn.execute(
            "UPDATE members SET display_name = ?, message = ? WHERE strava_athlete_id = ?",
            (display_name, message, strava_athlete_id),
        )
        self._conn.commit()

    def delete_member(self, strava_athlete_id: int) -> None:
        self._conn.execute(
            "DELETE FROM members WHERE strava_athlete_id = ?", (strava_athlete_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Run log
    # ------------------------------------------------------------------

    def has_activity(
        self,
        firstname: str,
        lastname: str,
        moving_time: int,
        distance_m: int,
    ) -> bool:
        row = self._conn.execute(
            """SELECT 1 FROM run_log
               WHERE strava_firstname = ? AND strava_lastname = ?
                 AND moving_time = ? AND distance_m = ?""",
            (firstname, lastname, moving_time, distance_m),
        ).fetchone()
        return row is not None

    def log_activity(
        self,
        firstname: str,
        lastname: str,
        moving_time: int,
        distance_m: int,
        distance_miles: float,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO run_log
                (strava_firstname, strava_lastname, moving_time, distance_m, distance_miles)
            VALUES (?, ?, ?, ?, ?)
            """,
            (firstname, lastname, moving_time, distance_m, distance_miles),
        )
        self._conn.commit()

    def set_manual_miles(self, strava_firstname: str, strava_lastname: str, miles: float) -> None:
        """Wipe all existing run_log entries for this member and set a single
        baseline entry. Real runs from polling will accumulate on top."""
        self._conn.execute(
            "DELETE FROM run_log WHERE strava_firstname=? AND strava_lastname=?",
            (strava_firstname, strava_lastname),
        )
        self._conn.execute(
            """INSERT INTO run_log
                   (strava_firstname, strava_lastname, moving_time, distance_m, distance_miles)
               VALUES (?, ?, 0, -1, ?)""",
            (strava_firstname, strava_lastname, miles),
        )
        self._conn.commit()

    def get_yearly_miles(self, year: int) -> list[dict]:
        """Total miles per member for the given year, all members included (0 if none logged)."""
        rows = self._conn.execute(
            """
            SELECT m.display_name,
                   COALESCE(SUM(r.distance_miles), 0.0) AS total_miles
            FROM members m
            LEFT JOIN run_log r
                ON m.strava_firstname = r.strava_firstname
               AND m.strava_lastname  = r.strava_lastname
               AND strftime('%Y', r.logged_at) = ?
            GROUP BY m.strava_athlete_id, m.display_name
            ORDER BY total_miles DESC
            """,
            (str(year),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_runs(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT
                COALESCE(m.display_name,
                         r.strava_firstname || ' ' || r.strava_lastname) AS display_name,
                r.distance_miles,
                r.moving_time,
                r.logged_at
            FROM run_log r
            LEFT JOIN members m
                ON  m.strava_firstname = r.strava_firstname
                AND m.strava_lastname  = r.strava_lastname
            WHERE r.distance_m != -1
            ORDER BY r.logged_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
