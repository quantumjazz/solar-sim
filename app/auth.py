"""Accounts and login for the multi-user solar-sim app.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib `hashlib`), with a
per-user random salt. Nothing here needs a third-party dependency.

The stored hash is a single string:

    pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>

`register_user` and `authenticate` are the two functions the UI calls; both
take a `db.Database`. Account-shaped errors raise `AuthError` with a
human-readable message.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from db import Database

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 200_000
_SALT_BYTES = 16
_MIN_PASSWORD_LEN = 8

#: How long a cookie-backed session stays valid before the user must log in.
SESSION_DURATION = timedelta(days=7)
#: Cookie name carrying the session token in the browser.
SESSION_COOKIE = "solar_sim_session"

#: Environment variable that, when set non-empty, gates instructor
#: registration: a new instructor account must present the matching token.
#: Unset (the default) → registration is open, as before.
INSTRUCTOR_TOKEN_ENV = "SOLAR_SIM_INSTRUCTOR_TOKEN"

ROLES = ("instructor", "student")


def instructor_token_required() -> bool:
    """True if the deployment has configured an instructor-registration token."""
    return bool(os.environ.get(INSTRUCTOR_TOKEN_ENV))


class AuthError(Exception):
    """A registration or login problem with a message safe to show a user."""


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Return a self-describing PBKDF2 hash string for `password`."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _ITERATIONS
    )
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check `password` against a stored hash string; constant-time compare."""
    try:
        algorithm, iterations_s, salt_hex, digest_hex = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return secrets.compare_digest(actual, expected)


# ---------------------------------------------------------------------------
# Register / authenticate
# ---------------------------------------------------------------------------


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def register_user(
    db: Database,
    email: str,
    display_name: str,
    password: str,
    role: str,
    instructor_token: Optional[str] = None,
) -> int:
    """Create a new account; return its user id.

    Raises `AuthError` if the email is taken, the role is unknown, a
    field fails a basic sanity check, or the deployment has configured
    `SOLAR_SIM_INSTRUCTOR_TOKEN` and the caller asks for `role="instructor"`
    without presenting the matching token.
    """
    email = _normalise_email(email)
    display_name = display_name.strip()

    if "@" not in email or "." not in email.split("@")[-1]:
        raise AuthError("Enter a valid email address.")
    if not display_name:
        raise AuthError("Enter a display name.")
    if len(password) < _MIN_PASSWORD_LEN:
        raise AuthError(
            f"Password must be at least {_MIN_PASSWORD_LEN} characters."
        )
    if role not in ROLES:
        raise AuthError(f"Unknown role {role!r}.")

    if role == "instructor":
        configured = os.environ.get(INSTRUCTOR_TOKEN_ENV) or ""
        if configured:
            supplied = (instructor_token or "").strip()
            if not supplied or not secrets.compare_digest(supplied, configured):
                raise AuthError(
                    "Instructor registration requires a valid token. "
                    "Ask the administrator for the current value of "
                    f"${INSTRUCTOR_TOKEN_ENV}."
                )

    if db.get_user_by_email(email) is not None:
        raise AuthError("An account with that email already exists.")

    try:
        return db.create_user(email, display_name, hash_password(password), role)
    except sqlite3.IntegrityError:
        # A concurrent registration won the unique-email race.
        raise AuthError("An account with that email already exists.")


def authenticate(
    db: Database, email: str, password: str
) -> Optional[sqlite3.Row]:
    """Return the user row if the credentials are valid, otherwise None."""
    user = db.get_user_by_email(_normalise_email(email))
    if user is None:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


# ---------------------------------------------------------------------------
# Cookie-backed sessions
# ---------------------------------------------------------------------------


def create_session(db: Database, user_id: int) -> str:
    """Mint a random session token for `user_id` and persist it.

    Returns the token string. The caller puts it in a browser cookie; the
    record in the database includes the user id and an expiry timestamp
    (now + `SESSION_DURATION`).
    """
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + SESSION_DURATION).isoformat()
    db.create_session(token, user_id, expires_at)
    return token


def lookup_session(db: Database, token: str) -> Optional[sqlite3.Row]:
    """Return the user row backing `token` if the session is valid, else None.

    Expired session rows are pruned opportunistically on lookup.
    """
    db.purge_expired_sessions()
    row = db.lookup_session(token)
    if row is None:
        return None
    return db.get_user(int(row["user_id"]))


def end_session(db: Database, token: str) -> None:
    """Invalidate a session token (the database row is deleted)."""
    db.delete_session(token)
