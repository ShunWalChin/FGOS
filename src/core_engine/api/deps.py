from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core_engine.auth import verify_token
from core_engine.settings import Settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    agency_id: UUID
    email: str | None
    role: str


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    """Resolve the caller from a Bearer token.

    When auth_required is False (dev/smoke), a missing/invalid token falls back to
    the development agency so existing flows keep working. In production
    (auth_required=True) a valid token is mandatory.
    """

    settings = _settings(request)
    payload = verify_token(creds.credentials, settings.auth_secret) if creds else None

    if payload is None:
        if settings.auth_required:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing or invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return Principal(
            user_id=None,
            agency_id=settings.default_agency_id,
            email=None,
            role="dev",
        )

    return Principal(
        user_id=payload.get("sub"),
        agency_id=UUID(payload["agency_id"]),
        email=payload.get("email"),
        role=payload.get("role", "member"),
    )
