import hashlib
import hmac
import os
import sqlite3
from typing import Optional


DEFAULT_DB_PATH = os.path.join("data", "coinai.db")
DEFAULT_SUPER_EMAIL = "super@user.com"
DEFAULT_SUPER_NAME = "Super User"
DEFAULT_SUPER_PASSWORD = "nimda"
USER_TYPES = ("admin", "user", "Super-admin")
MANAGED_USER_TYPES = ("admin", "user")
PBKDF2_ITERATIONS = 260_000


def _get_db_path() -> str:
    return os.environ.get("TIKITAR_AUTH_DB_PATH", DEFAULT_DB_PATH)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"
        f"{salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False

        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_text),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (AttributeError, TypeError, ValueError):
        return False


def init_db(db_path: Optional[str] = None) -> str:
    db_path = db_path or _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                user_type TEXT NOT NULL CHECK(user_type IN ('admin','user','Super-admin')),
                name TEXT NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO users (email, user_type, name, password)
            VALUES (?, ?, ?, ?)
            """,
            (
                DEFAULT_SUPER_EMAIL,
                "Super-admin",
                DEFAULT_SUPER_NAME,
                hash_password(DEFAULT_SUPER_PASSWORD),
            ),
        )
        conn.commit()

    return db_path


def get_user(email: str, db_path: Optional[str] = None) -> Optional[dict]:
    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT email, user_type, name, password, created_at
            FROM users
            WHERE email = ?
            """,
            (normalize_email(email),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_type(email: str, db_path: Optional[str] = None) -> Optional[str]:
    user = get_user(email, db_path)
    return user["user_type"] if user else None


def authenticate_user(email: str, password: str, db_path: Optional[str] = None) -> Optional[dict]:
    user = get_user(email, db_path)
    if not user or not verify_password(password, user["password"]):
        return None

    return {
        "email": user["email"],
        "user_type": user["user_type"],
        "name": user["name"],
    }


def change_password(email: str, new_password: str, db_path: Optional[str] = None) -> tuple[bool, str]:
    if not new_password:
        return False, "Password cannot be blank"

    db_path = init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE users SET password = ? WHERE email = ?",
            (hash_password(new_password), normalize_email(email)),
        )
        rowcount = cursor.rowcount
        conn.commit()

    if rowcount == 0:
        return False, "User not found"

    return True, "Password changed successfully"


def seed_from_streamlit_secrets_if_empty(db_path: Optional[str] = None) -> tuple[bool, int]:
    """Compatibility shim. Fresh databases are seeded with the default Super-admin."""
    init_db(db_path)
    return (False, 0)
