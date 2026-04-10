"""User management: JSON file-based user store with PBKDF2 password hashing and JWT tokens."""

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional

import jwt

from .config import settings

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_JWT_SECRET = os.getenv("CODEX_JWT_SECRET", "")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_SECONDS = int(os.getenv("CODEX_JWT_EXPIRE_SECONDS", "86400"))  # 24h default

_PBKDF2_ITERATIONS = 260_000
_HASH_ALGORITHM = "sha256"
_SALT_LENGTH = 32

# Default admin credentials (used only on first run when no users exist)
_DEFAULT_ADMIN_USER = os.getenv("CODEX_ADMIN_USER", "admin")
_DEFAULT_ADMIN_PASS = os.getenv("CODEX_ADMIN_PASS", "admin")


def _jwt_secret() -> str:
    """Return a stable JWT secret, generating one lazily if not configured."""
    global _JWT_SECRET
    if _JWT_SECRET:
        return _JWT_SECRET
    secret_path = _users_file().parent / ".jwt_secret"
    if secret_path.is_file():
        _JWT_SECRET = secret_path.read_text(encoding="utf-8").strip()
    if not _JWT_SECRET:
        _JWT_SECRET = secrets.token_hex(32)
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(_JWT_SECRET, encoding="utf-8")
    return _JWT_SECRET


# ---------------------------------------------------------------------------
# User store (JSON file)
# ---------------------------------------------------------------------------

def _users_file() -> Path:
    """Path to the users.json file stored alongside the workspace root."""
    workspace_root = Path(settings.codex_workdir).expanduser()
    return workspace_root.parent / "users.json"


def _load_users() -> dict[str, dict[str, Any]]:
    path = _users_file()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_users(users: dict[str, dict[str, Any]]) -> None:
    path = _users_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_LENGTH)
    dk = hashlib.pbkdf2_hmac(_HASH_ALGORITHM, password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac(_HASH_ALGORITHM, password.encode(), salt, _PBKDF2_ITERATIONS)
    return secrets.compare_digest(dk, expected)


# ---------------------------------------------------------------------------
# Bootstrap (ensure at least one admin exists)
# ---------------------------------------------------------------------------

def ensure_default_admin() -> None:
    users = _load_users()
    if users:
        return  # at least one user exists
    users[_DEFAULT_ADMIN_USER] = {
        "password": _hash_password(_DEFAULT_ADMIN_PASS),
        "role": "admin",
    }
    _save_users(users)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def authenticate(username: str, password: str) -> Optional[dict[str, Any]]:
    """Verify credentials. Returns user dict (without password) or None."""
    users = _load_users()
    user = users.get(username)
    if not user:
        return None
    if not _verify_password(password, user.get("password", "")):
        return None
    return {"username": username, "role": user.get("role", "user")}


def create_user(username: str, password: str, role: str = "user") -> dict[str, Any]:
    """Create a new user. Raises ValueError if username already taken."""
    if not username or not username.strip():
        raise ValueError("Username is required.")
    if not password or len(password) < 4:
        raise ValueError("Password must be at least 4 characters.")
    if role not in ("admin", "user"):
        raise ValueError("Role must be 'admin' or 'user'.")
    users = _load_users()
    if username in users:
        raise ValueError(f"User '{username}' already exists.")
    users[username] = {
        "password": _hash_password(password),
        "role": role,
    }
    _save_users(users)
    return {"username": username, "role": role}


def change_password(username: str, old_password: str, new_password: str) -> None:
    """Change password for a user. Requires the old password."""
    if not new_password or len(new_password) < 4:
        raise ValueError("New password must be at least 4 characters.")
    users = _load_users()
    user = users.get(username)
    if not user:
        raise ValueError("User not found.")
    if not _verify_password(old_password, user.get("password", "")):
        raise ValueError("Current password is incorrect.")
    user["password"] = _hash_password(new_password)
    _save_users(users)


def admin_reset_password(target_username: str, new_password: str) -> None:
    """Admin resets another user's password without knowing the old one."""
    if not new_password or len(new_password) < 4:
        raise ValueError("New password must be at least 4 characters.")
    users = _load_users()
    if target_username not in users:
        raise ValueError(f"User '{target_username}' not found.")
    users[target_username]["password"] = _hash_password(new_password)
    _save_users(users)


def list_users() -> list[dict[str, str]]:
    """Return list of users (without passwords)."""
    users = _load_users()
    return [{"username": name, "role": info.get("role", "user")} for name, info in users.items()]


def get_user(username: str) -> Optional[dict[str, Any]]:
    """Get a user by username (without password)."""
    users = _load_users()
    user = users.get(username)
    if not user:
        return None
    return {"username": username, "role": user.get("role", "user")}


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + _JWT_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    """Decode and validate a JWT token. Returns user dict or None."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return get_user(username)
