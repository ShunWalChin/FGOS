from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from core_engine import repository as repo
from core_engine.auth import hash_password
from core_engine.db import create_session_factory, session_scope
from core_engine.settings import Settings, get_settings

SEED_FILE = Path(".seed.json")
DEFAULT_AGENCY_ID = UUID("00000000-0000-0000-0000-000000000001")
DEV_EMAIL = "dev@fgos.local"
DEV_PASSWORD = "fgosdev"


async def seed(settings: Settings | None = None) -> dict[str, str]:
    settings = settings or get_settings()
    session_factory = create_session_factory(settings.database_url)

    async with session_scope(session_factory) as session:
        await session.execute(
            text(
                """
                insert into agencies(id, name, slug, plan, branding)
                values (:id, 'Development Agency', 'dev', 'trial',
                        cast(:branding as jsonb))
                on conflict (id) do update
                  set slug = coalesce(agencies.slug, 'dev'),
                      branding = case when agencies.branding = '{}'::jsonb
                                      then excluded.branding else agencies.branding end
                """
            ),
            {
                "id": str(DEFAULT_AGENCY_ID),
                "branding": json.dumps(
                    {
                        "display_name": "Development Agency",
                        "primary_color": "#00f0ff",
                        "secondary_color": "#ff2d78",
                        "accent_color": "#a855f7",
                        "logo_url": "",
                    }
                ),
            },
        )

        pipeline_id = await _get_or_create(
            session,
            "select id from pipelines where agency_id = :agency_id and name = :name",
            "insert into pipelines(agency_id, name) values (:agency_id, :name) returning id",
            {"agency_id": str(DEFAULT_AGENCY_ID), "name": "Vendas"},
        )

        stage_ids = {}
        for index, (name, is_won, is_lost) in enumerate(
            [("Lead", False, False), ("Proposta", False, False), ("Fechado", True, False)]
        ):
            stage_ids[name] = await _get_or_create(
                session,
                "select id from stages where pipeline_id = :pipeline_id and name = :name",
                """
                insert into stages(pipeline_id, name, sort_order, is_won, is_lost)
                values (:pipeline_id, :name, :sort_order, :is_won, :is_lost)
                returning id
                """,
                {
                    "pipeline_id": pipeline_id,
                    "name": name,
                    "sort_order": float(index),
                    "is_won": is_won,
                    "is_lost": is_lost,
                },
            )

        workspace_id = await _get_or_create(
            session,
            "select id from workspaces where agency_id = :agency_id and name = :name",
            "insert into workspaces(agency_id, name) values (:agency_id, :name) returning id",
            {"agency_id": str(DEFAULT_AGENCY_ID), "name": "Workspace Inicial"},
        )

        list_id = await _get_or_create(
            session,
            "select id from lists where workspace_id = :workspace_id and name = :name",
            """
            insert into lists(workspace_id, name, sort_order)
            values (:workspace_id, :name, 0)
            returning id
            """,
            {"workspace_id": workspace_id, "name": "Backlog"},
        )

        user_id = await repo.create_user(
            session,
            agency_id=str(DEFAULT_AGENCY_ID),
            email=DEV_EMAIL,
            password_hash=hash_password(DEV_PASSWORD),
            full_name="Dev User",
            role="owner",
        )

    result = {
        "agency_id": str(DEFAULT_AGENCY_ID),
        "pipeline_id": pipeline_id,
        "stage_lead_id": stage_ids["Lead"],
        "stage_proposta_id": stage_ids["Proposta"],
        "stage_fechado_id": stage_ids["Fechado"],
        "workspace_id": workspace_id,
        "list_id": list_id,
        "user_id": user_id,
        "login": f"{DEV_EMAIL} / {DEV_PASSWORD}",
    }
    SEED_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


async def _get_or_create(session, select_sql: str, insert_sql: str, params: dict) -> str:
    existing = await session.execute(text(select_sql), params)
    row = existing.first()
    if row:
        return str(row[0])
    created = await session.execute(text(insert_sql), params)
    return str(created.scalar_one())
