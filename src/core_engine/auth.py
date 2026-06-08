from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

# Self-contained auth using only the stdlib (no PyJWT/passlib dependency), so the
# whole auth path is unit-testable on a bare host and adds zero runtime deps.
# - Tokens are standard HS256 JWTs, signed by hand.
# - Passwords use PBKDF2-HMAC-SHA256 with a per-password random salt.

PBKDF2_ITERATIONS = 200_000


# --- base64url helpers ----------------------------------------------------


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- password hashing -----------------------------------------------------


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64u(salt)}${_b64u(dk)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _b64u_decode(salt_b64), int(iters)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(_b64u(dk), hash_b64)


# --- JWT (HS256) ----------------------------------------------------------


def create_token(claims: dict[str, Any], secret: str, *, ttl_seconds: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {**claims, "iat": now, "exp": now + ttl_seconds}
    segment = (
        _b64u(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64u(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = _b64u(hmac.new(secret.encode("utf-8"), segment.encode("ascii"), hashlib.sha256).digest())
    return f"{segment}.{signature}"


def verify_token(token: str, secret: str) -> dict[str, Any] | None:
    try:
        header_b64, payload_b64, signature = token.split(".")
    except (ValueError, AttributeError):
        return None
    segment = f"{header_b64}.{payload_b64}"
    expected = _b64u(hmac.new(secret.encode("utf-8"), segment.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64u_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
