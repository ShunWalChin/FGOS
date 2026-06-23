from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def upsert_contact(
    session: AsyncSession,
    *,
    agency_id: str,
    channel: str,
    sender: str,
) -> str:
    """Find a contact by its external id for the channel, or create one."""

    found = await session.execute(
        text(
            """
            select id from contacts
            where agency_id = :agency_id and external_ids->>:channel = :sender
            limit 1
            """
        ),
        {"agency_id": agency_id, "channel": channel, "sender": sender},
    )
    row = found.first()
    if row:
        return str(row[0])

    created = await session.execute(
        text(
            """
            insert into contacts(agency_id, external_ids)
            values (:agency_id, jsonb_build_object(:channel, :sender))
            returning id
            """
        ),
        {"agency_id": agency_id, "channel": channel, "sender": sender},
    )
    return str(created.scalar_one())


async def get_or_create_session(
    session: AsyncSession,
    *,
    agency_id: str,
    contact_id: str,
    channel: str,
) -> dict[str, Any]:
    """Return the live chat session for a contact+channel (creating it as a bot)."""

    found = await session.execute(
        text(
            """
            select id, current_node_id, context, mode
            from chat_sessions
            where contact_id = :contact_id and channel = :channel
            order by updated_at desc
            limit 1
            """
        ),
        {"contact_id": contact_id, "channel": channel},
    )
    row = found.mappings().first()
    if row:
        return dict(row)

    created = await session.execute(
        text(
            """
            insert into chat_sessions(agency_id, contact_id, channel)
            values (:agency_id, :contact_id, :channel)
            returning id, current_node_id, context, mode
            """
        ),
        {"agency_id": agency_id, "contact_id": contact_id, "channel": channel},
    )
    return dict(created.mappings().one())


async def get_session(
    session: AsyncSession,
    *,
    session_id: str,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            select id, agency_id, contact_id, channel, current_node_id, context, mode
            from chat_sessions where id = :id
            """
        ),
        {"id": session_id},
    )
    row = result.mappings().first()
    if not row:
        return None
    data = dict(row)
    data["id"] = str(data["id"])
    data["agency_id"] = str(data["agency_id"])
    data["contact_id"] = str(data["contact_id"])
    return data


async def insert_message(
    session: AsyncSession,
    *,
    session_id: str,
    direction: str,
    body: str,
    provider_msg_id: str | None = None,
) -> str | None:
    """Persist a message. Returns None when it's a duplicate webhook (dedupe by
    provider_msg_id via the partial unique index)."""

    result = await session.execute(
        text(
            """
            insert into messages(session_id, direction, body, provider_msg_id)
            values (:session_id, :direction, :body, :provider_msg_id)
            on conflict (provider_msg_id) where provider_msg_id is not null do nothing
            returning id
            """
        ),
        {
            "session_id": session_id,
            "direction": direction,
            "body": body,
            "provider_msg_id": provider_msg_id or None,
        },
    )
    row = result.first()
    return str(row[0]) if row else None


async def update_session_state(
    session: AsyncSession,
    *,
    session_id: str,
    current_node_id: str,
    context: str,
) -> None:
    await session.execute(
        text(
            """
            update chat_sessions
            set current_node_id = :node, context = cast(:context as jsonb), updated_at = now()
            where id = :id
            """
        ),
        {"id": session_id, "node": current_node_id, "context": context},
    )


async def set_session_mode(
    session: AsyncSession,
    *,
    session_id: str,
    mode: str,
) -> None:
    await session.execute(
        text(
            "update chat_sessions set mode = :mode, updated_at = now() where id = :id"
        ),
        {"id": session_id, "mode": mode},
    )
