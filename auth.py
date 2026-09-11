import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_USERS_FILE = Path(__file__).parent / "users.json"

#: How long a login stays valid, in seconds (default 12 hours).
TOKEN_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS") or 12 * 60 * 60)

_cache: Dict[str, Any] = {"path": None, "mtime": None, "users": {}}


def users_file_path() -> Path:
    """Path to the credentials file, honouring the USERS_FILE override."""
    return Path(os.getenv("USERS_FILE") or DEFAULT_USERS_FILE)


def hash_password(password: str) -> str:
    """Hex SHA-256 digest, for use in a ``password_sha256`` entry."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _parse_entries(raw: Any) -> Dict[str, Dict[str, Any]]:
    """Turn the parsed JSON into a {lowercased username: account} mapping."""
    if isinstance(raw, dict):
        entries = raw.get("users", [])
    else:
        entries = raw

    if not isinstance(entries, list):
        raise ValueError("Expected a list of users, or an object with a 'users' list")

    users: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            logger.warning("Skipping credential entry that is not an object: %r", entry)
            continue

        username = str(entry.get("username", "")).strip()
        password = entry.get("password")
        password_sha256 = entry.get("password_sha256")

        if not username:
            logger.warning("Skipping credential entry without a username")
            continue
        if not password and not password_sha256:
            logger.warning("Skipping user %r: no password or password_sha256", username)
            continue

        users[username.lower()] = {
            "username": username,
            "name": str(entry.get("name") or username),
            "password": password,
            "password_sha256": (
                str(password_sha256).strip().lower() if password_sha256 else None
            ),
        }

    return users


def load_users(force: bool = False) -> Dict[str, Dict[str, Any]]:
    """Load the credentials file, re-reading it whenever it changes on disk.

    Editing users.json takes effect on the next login — no restart needed.
    """
    path = users_file_path()

    try:
        mtime = path.stat().st_mtime
    except OSError:
        if _cache["path"] != path or _cache["users"]:
            logger.error("Credentials file not found: %s — no one can log in", path)
        _cache.update({"path": path, "mtime": None, "users": {}})
        return {}

    if not force and _cache["path"] == path and _cache["mtime"] == mtime:
        return _cache["users"]

    try:
        with path.open("r", encoding="utf-8") as handle:
            users = _parse_entries(json.load(handle))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Could not parse %s: %s — no one can log in", path, exc)
        _cache.update({"path": path, "mtime": mtime, "users": {}})
        return {}

    logger.info("Loaded %d account(s) from %s", len(users), path)
    _cache.update({"path": path, "mtime": mtime, "users": users})
    return users


def verify_credentials(username: str, password: str) -> Optional[Dict[str, str]]:
    """Return {"username", "name"} on a match, or None when the login is bad."""
    if not username or not password:
        return None

    account = load_users().get(username.strip().lower())
    if account is None:
        return None

    if account["password_sha256"]:
        matched = hmac.compare_digest(
            account["password_sha256"], hash_password(password)
        )
    else:
        matched = hmac.compare_digest(str(account["password"]), password)

    if not matched:
        return None

    return {"username": account["username"], "name": account["name"]}


def _load_secret() -> bytes:
    """Signing key for session tokens.

    Falls back to a per-process random key so a misconfigured deployment fails
    closed (tokens simply stop working after a restart) rather than falling back
    to a guessable constant.
    """
    configured = os.getenv("SESSION_SECRET")
    if configured:
        return configured.encode("utf-8")

    logger.warning(
        "SESSION_SECRET is not set — using a random key. Logins will be "
        "invalidated on restart and will not work across multiple workers."
    )
    return secrets.token_bytes(32)


_SECRET = _load_secret()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(body: str) -> str:
    digest = hmac.new(_SECRET, body.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def create_token(
    username: str, name: str, ttl_seconds: int = TOKEN_TTL_SECONDS
) -> Dict[str, Any]:
    """Mint a signed token for a user who has just proven their password."""
    expires_at = int(time.time()) + ttl_seconds
    payload = {"sub": username, "name": name, "exp": expires_at}
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return {
        "token": f"{body}.{_sign(body)}",
        "expires_at": expires_at,
    }


def verify_token(token: str) -> Optional[Dict[str, str]]:
    """Return {"username", "name"} for a valid token, else None.

    Rejects anything with a bad shape, a bad signature, or a passed expiry.
    """
    if not token:
        return None

    body, _, signature = token.partition(".")
    if not body or not signature:
        return None

    if not hmac.compare_digest(_sign(body), signature):
        return None

    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    username = payload.get("sub")
    expires_at = payload.get("exp")
    if not username or not isinstance(expires_at, (int, float)):
        return None

    if time.time() >= expires_at:
        return None

    return {"username": str(username), "name": str(payload.get("name") or username)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python auth.py <password>", file=sys.stderr)
        raise SystemExit(1)
    print(hash_password(sys.argv[1]))
