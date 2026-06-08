from __future__ import annotations

import hmac
from hashlib import sha256


def valid_meta_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Validate Meta's x-hub-signature-256 header using constant-time compare."""

    if not raw_body or not signature_header or not app_secret:
        return False

    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        sha256,
    ).hexdigest()

    return hmac.compare_digest(signature_header, expected)
