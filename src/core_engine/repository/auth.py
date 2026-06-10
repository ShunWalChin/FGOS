from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def slug_exists(session: AsyncSession, *, slug: str) -> bool:
    result = await session.execute(
        text("select 1 from agencies where slug = :slug limit 1"),
        {"slug": slug},
    )
    return result.first() is not None


async def create_agency_with_owner(
    session: AsyncSession,
    *,
    agency_name: str,
    slug: str,
    owner_email: str,
    owner_password_hash: str,
    branding_json: str,
    owner_name: str | None = None,
    plan: str = "trial",
) -> dict[str, Any]:
    """Self-service provisioning: create an agency, its owner, and the default
    CRM pipeline + workspace so the tenant is operable on first login."""

    agency_row = await session.execute(
        text(
            """
            insert into agencies(name, slug, plan, branding)
            values (:name, :slug, :plan, cast(:branding as jsonb))
            returning id
            """
        ),
        {"name": agency_name, "slug": slug, "plan": plan, "branding": branding_json},
    )
    agency_id = str(agency_row.scalar_one())

    user_id = await create_user(
        session,
        agency_id=agency_id,
        email=owner_email,
        password_hash=owner_password_hash,
        full_name=owner_name,
        role="owner",
    )

    pipeline_id = str(
        (
            await session.execute(
                text(
                    "insert into pipelines(agency_id, name) values (:a, 'Vendas') returning id"
                ),
                {"a": agency_id},
            )
        ).scalar_one()
    )
    for index, (name, is_won) in enumerate(
        [("Lead", False), ("Proposta", False), ("Fechado", True)]
    ):
        await session.execute(
            text(
                """
                insert into stages(pipeline_id, name, sort_order, is_won)
                values (:p, :n, :o, :w)
                """
            ),
            {"p": pipeline_id, "n": name, "o": float(index), "w": is_won},
        )

    workspace_id = str(
        (
            await session.execute(
                text(
                    "insert into workspaces(agency_id, name) values (:a, 'Workspace') returning id"
                ),
                {"a": agency_id},
            )
        ).scalar_one()
    )
    await session.execute(
        text("insert into lists(workspace_id, name, sort_order) values (:w, 'Backlog', 0)"),
        {"w": workspace_id},
    )

    return {
        "agency_id": agency_id,
        "user_id": user_id,
        "pipeline_id": pipeline_id,
        "workspace_id": workspace_id,
    }


async def get_branding_by_slug(session: AsyncSession, *, slug: str) -> dict[str, Any] | None:
    result = await session.execute(
        text("select id, name, slug, plan, branding from agencies where slug = :slug"),
        {"slug": slug},
    )
    row = result.mappings().first()
    if not row:
        return None
    data = dict(row)
    data["id"] = str(data["id"])
    return data


async def update_branding(
    session: AsyncSession, *, agency_id: str, branding_json: str
) -> bool:
    result = await session.execute(
        text(
            "update agencies set branding = cast(:b as jsonb) where id = :id returning id"
        ),
        {"id": agency_id, "b": branding_json},
    )
    return result.first() is not None


async def create_user(
    session: AsyncSession,
    *,
    agency_id: str,
    email: str,
    password_hash: str,
    full_name: str | None = None,
    role: str = "member",
) -> str:
    result = await session.execute(
        text(
            """
            insert into app_users(agency_id, email, full_name, role, password_hash)
            values (:agency_id, :email, :full_name, :role, :password_hash)
            on conflict (agency_id, email) do update
              set password_hash = excluded.password_hash,
                  full_name = coalesce(excluded.full_name, app_users.full_name)
            returning id
            """
        ),
        {
            "agency_id": agency_id,
            "email": email,
            "full_name": full_name,
            "role": role,
            "password_hash": password_hash,
        },
    )
    return str(result.scalar_one())


async def get_user_by_email(
    session: AsyncSession,
    *,
    email: str,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            select id, agency_id, email, full_name, role, password_hash
            from app_users where email = :email
            limit 1
            """
        ),
        {"email": email},
    )
    row = result.mappings().first()
    if not row:
        return None
    data = dict(row)
    data["id"] = str(data["id"])
    data["agency_id"] = str(data["agency_id"])
    return data
