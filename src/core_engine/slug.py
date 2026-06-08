from __future__ import annotations

import re
import unicodedata

DEFAULT_BRANDING: dict[str, str] = {
    "display_name": "",
    "primary_color": "#00f0ff",
    "secondary_color": "#ff2d78",
    "accent_color": "#a855f7",
    "logo_url": "",
}


def slugify(value: str) -> str:
    """Turn an agency name into a URL-safe slug (ASCII, lowercase, hyphenated)."""
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return cleaned or "agencia"


def merge_branding(override: dict | None) -> dict[str, str]:
    """Merge a partial branding override onto the defaults (pure)."""
    result = dict(DEFAULT_BRANDING)
    for key, value in (override or {}).items():
        if key in result and value:
            result[key] = value
    return result
