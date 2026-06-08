from __future__ import annotations

from typing import TYPE_CHECKING

from core_engine.providers.social_base import DryRunProvider, SocialProvider

if TYPE_CHECKING:
    from core_engine.settings import Settings

SUPPORTED_PLATFORMS = ("meta", "tiktok", "linkedin", "youtube")


def get_provider(platform: str, settings: "Settings") -> SocialProvider:
    """Return the publisher for a platform.

    In dev (`SOCIAL_LIVE=false`) every platform uses the DryRunProvider, so the
    whole pipeline — claim, publish, events, BI mirror — is exercisable with no
    real OAuth app. Flip SOCIAL_LIVE=true (and provide client credentials) to
    swap in the real adapter once it exists.
    """

    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"unsupported platform: {platform}")

    if not settings.social_live:
        return DryRunProvider(platform)

    # Real adapters plug in here as they are implemented, e.g.:
    #   if platform == "meta": return MetaGraphProvider(settings)
    # Until then, live mode falls back to dry-run so nothing crashes silently.
    return DryRunProvider(platform)


def oauth_authorize_url(platform: str, state: str, settings: "Settings") -> str:
    """Build the provider's OAuth consent URL. Endpoints are the public, stable
    authorize endpoints; the token exchange happens in the callback handler."""

    redirect_uri = f"{settings.oauth_redirect_base}/api/oauth/{platform}/callback"
    endpoints = {
        "meta": "https://www.facebook.com/v21.0/dialog/oauth",
        "tiktok": "https://www.tiktok.com/v2/auth/authorize/",
        "linkedin": "https://www.linkedin.com/oauth/v2/authorization",
        "youtube": "https://accounts.google.com/o/oauth2/v2/auth",
    }
    client_id = getattr(settings, f"{platform}_client_id", "")
    base = endpoints.get(platform)
    if not base:
        raise ValueError(f"unsupported platform: {platform}")

    from urllib.parse import urlencode

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    return f"{base}?{urlencode(params)}"
