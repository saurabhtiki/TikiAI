import os
import sqlite3
from typing import Optional, Tuple

import streamlit as st


DEFAULT_DB_PATH = os.path.join("data", "coinai.db")


def _get_db_path() -> str:
    # Allow overriding for local setups; Streamlit-hosted apps should keep it writable.
    return os.environ.get("TIKITAR_AUTH_DB_PATH", DEFAULT_DB_PATH)


def init_db(db_path: Optional[str] = None) -> str:
    db_path = db_path or _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                user_type TEXT NOT NULL CHECK(user_type IN ('admin','user')),
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()

    return db_path


def _get_user_type_from_db(conn: sqlite3.Connection, email: str) -> Optional[str]:
    cur = conn.execute("SELECT user_type FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    return row[0] if row else None


def get_user_type(email: str, db_path: Optional[str] = None) -> Optional[str]:
    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        return _get_user_type_from_db(conn, email)


def is_db_empty(db_path: Optional[str] = None) -> bool:
    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT COUNT(1) FROM users")
        (count,) = cur.fetchone()
        return count == 0


def seed_from_streamlit_secrets_if_empty(db_path: Optional[str] = None) -> Tuple[bool, int]:
    """Returns (seeded, inserted_count). Seed only when the DB is empty."""
    db_path = init_db(db_path)

    if not is_db_empty(db_path):
        return (False, 0)

    authorized_users = st.secrets.get("authorized_users", [])
    authorized_admins = st.secrets.get("authorized_admins", [])

    users = []
    for email in authorized_admins:
        if isinstance(email, str):
            e = email.strip().lower()
            if e:
                users.append((e, "admin"))

    for email in authorized_users:
        if isinstance(email, str):
            e = email.strip().lower()
            if e:
                users.append((e, "user"))

    # If you have overlaps (same email in both lists), admins win.
    final = {}
    for e, t in users:
        final[e] = t

    # Ensure admin overrides user.
    for email in authorized_admins:
        if isinstance(email, str):
            e = email.strip().lower()
            if e:
                final[e] = "admin"

    rows = list(final.items())
    inserted_count = 0

    with sqlite3.connect(db_path) as conn:
        for email, user_type in rows:
            conn.execute(
                "INSERT OR REPLACE INTO users (email, user_type) VALUES (?, ?)",
                (email, user_type),
            )
            inserted_count += 1
        conn.commit()

    return (True, inserted_count)

