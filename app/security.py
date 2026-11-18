"""Пароли и сессионные cookie без внешних зависимостей."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

PBKDF2_ITERATIONS = 120_000
SESSION_TTL_SECONDS = 12 * 60 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, hash_b64 = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(hash_b64.encode())
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


def validate_password(password: str) -> str | None:
    if len(password) < 6:
        return "Пароль должен быть не короче 6 символов"
    if len(password) > 128:
        return "Пароль слишком длинный"
    return None


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def password_tag(stored_hash: str) -> str:
    return hashlib.sha256(stored_hash.encode("utf-8")).hexdigest()[:16]


def create_session(
    user_id: int,
    role: str,
    secret: str,
    tag: str = "",
    ttl: int = SESSION_TTL_SECONDS,
) -> str:
    payload = json.dumps(
        {
            "uid": int(user_id),
            "role": role,
            "pv": tag,
            "exp": int(time.time()) + ttl,
        },
        separators=(",", ":"),
    )
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode().rstrip("=")
    return f"{encoded}.{_sign(encoded, secret)}"


def read_session(token: str | None, secret: str) -> dict[str, object] | None:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(encoded, secret), signature):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, TypeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if payload.get("role") not in ("admin", "teamlead", "employee"):
        return None
    return payload
