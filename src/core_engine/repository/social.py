from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def claim_next_social_post(
    session: AsyncSession,
    *,
    worker_id: str,
    encryption_key: str,
) -> dict[str, Any] | None:
    """Claim one due post whose account is publishable.

    Skips accounts that are disconnected or under a per-account rate-limit
    cooldown. `FOR UPDATE OF pq SKIP LOCKED` keeps two workers from grabbing
    the same post. The account token is decrypted (pgcrypto) and returned so
    the worker never reads ciphertext.
    """

    result = await session.execute(
        text(
            """
            update posts_queue p
            set status = 'processing',
                locked_at = now(),
                locked_by = :worker_id,
                attempts = attempts + 1
            from social_accounts sa
            where sa.id = p.social_account_id
              and p.id = (
                select pq.id from posts_queue pq
                join social_accounts s2 on s2.id = pq.social_account_id
                where pq.status = 'pending'
                  and pq.scheduled_at <= now()
                  and (pq.next_attempt_at is null or pq.next_attempt_at <= now())
                  and s2.status <> 'disconnected'
                  and (s2.rate_limited_until is null or s2.rate_limited_until <= now())
                order by pq.scheduled_at
                for update of pq skip locked
                limit 1
              )
            returning p.id, p.agency_id, p.social_account_id, p.payload, p.attempts,
                      sa.platform as platform,
                      sa.external_account_id as external_account_id,
                      pgp_sym_decrypt(sa.access_token_enc, :key) as token
            """
        ),
        {"worker_id": worker_id, "key": encryption_key},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def mark_social_post_published(
    session: AsyncSession,
    *,
    post_id: str,
    platform_post_id: str | None = None,
) -> None:
    await session.execute(
        text(
            """
            update posts_queue
            set status = 'published',
                published_at = now(),
                platform_post_id = :platform_post_id,
                locked_at = null,
                locked_by = null,
                last_error = null
            where id = :post_id
            """
        ),
        {"post_id": post_id, "platform_post_id": platform_post_id},
    )


async def mark_social_post_failed(
    session: AsyncSession,
    *,
    post_id: str,
    error: str,
    max_attempts: int = 5,
    terminal: bool = False,
) -> None:
    """Backoff a failed post (exponential), or dead-letter it when `terminal`."""

    await session.execute(
        text(
            """
            update posts_queue
            set status = case
                  when :terminal then 'failed'
                  when attempts >= :max_attempts then 'failed'
                  else 'pending' end,
                next_attempt_at = now() + (interval '1 minute' * power(3, attempts)),
                last_error = :error,
                locked_at = null,
                locked_by = null
            where id = :post_id
            """
        ),
        {
            "post_id": post_id,
            "error": error,
            "max_attempts": max_attempts,
            "terminal": terminal,
        },
    )


async def insert_social_account(
    session: AsyncSession,
    *,
    agency_id: str,
    platform: str,
    external_account_id: str,
    access_token: str,
    encryption_key: str,
    client_id: str | None = None,
    refresh_token: str | None = None,
    expires_at: str | None = None,
    scopes: list[str] | None = None,
) -> str:
    """Store an OAuth account with its tokens encrypted at rest (pgcrypto)."""

    result = await session.execute(
        text(
            """
            insert into social_accounts(
                agency_id, client_id, platform, external_account_id,
                access_token_enc, refresh_token_enc, expires_at, scopes, status)
            values (
                :agency_id, :client_id, :platform, :external_account_id,
                pgp_sym_encrypt(cast(:access_token as text), :key),
                case when cast(:refresh_token as text) is null then null
                     else pgp_sym_encrypt(cast(:refresh_token as text), :key) end,
                :expires_at, :scopes, 'active')
            on conflict (platform, external_account_id) do update
              set access_token_enc = excluded.access_token_enc,
                  refresh_token_enc = excluded.refresh_token_enc,
                  expires_at = excluded.expires_at,
                  scopes = excluded.scopes,
                  status = 'active',
                  rate_limited_until = null,
                  updated_at = now()
            returning id
            """
        ),
        {
            "agency_id": agency_id,
            "client_id": client_id,
            "platform": platform,
            "external_account_id": external_account_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "key": encryption_key,
            "expires_at": expires_at,
            "scopes": scopes or [],
        },
    )
    return str(result.scalar_one())


async def list_social_accounts(
    session: AsyncSession,
    *,
    agency_id: str,
) -> list[dict[str, Any]]:
    """List accounts WITHOUT ever exposing the token columns."""

    result = await session.execute(
        text(
            """
            select id, platform, external_account_id, status, scopes,
                   expires_at, rate_limited_until, updated_at
            from social_accounts
            where agency_id = :agency_id
            order by updated_at desc
            """
        ),
        {"agency_id": agency_id},
    )
    return [dict(r) for r in result.mappings().all()]


async def enqueue_post(
    session: AsyncSession,
    *,
    agency_id: str,
    social_account_id: str,
    payload: str,
    scheduled_at: datetime,
    repost_frequency: int | None = None,
    repost_until: datetime | None = None,
) -> str:
    result = await session.execute(
        text(
            """
            insert into posts_queue(
                agency_id, social_account_id, payload, scheduled_at,
                repost_frequency, repost_until)
            values (:agency_id, :social_account_id, cast(:payload as jsonb),
                    :scheduled_at, :repost_frequency, :repost_until)
            returning id
            """
        ),
        {
            "agency_id": agency_id,
            "social_account_id": social_account_id,
            "payload": payload,
            "scheduled_at": scheduled_at,
            "repost_frequency": repost_frequency,
            "repost_until": repost_until,
        },
    )
    return str(result.scalar_one())


async def reschedule_repost(
    session: AsyncSession,
    *,
    post_id: str,
) -> str | None:
    """If the just-published post is a recurring repost (repost_frequency set and the next
    occurrence still falls within repost_until), clone it into a fresh pending row scheduled
    at now()+frequency. Returns the new post id, or None when the series is over.

    Absorbed from Stackposts (sp_posts.repost_frequency / repost_until). The clone carries
    payload, account, caption and the repost window so the series self-perpetuates until the
    deadline passes — no extra worker state required.
    """

    result = await session.execute(
        text(
            """
            insert into posts_queue(
                agency_id, social_account_id, payload, scheduled_at,
                repost_frequency, repost_until, caption_id)
            select agency_id, social_account_id, payload,
                   now() + (repost_frequency * interval '1 second'),
                   repost_frequency, repost_until, caption_id
            from posts_queue
            where id = :post_id
              and repost_frequency is not null
              and repost_until is not null
              and now() + (repost_frequency * interval '1 second') <= repost_until
            returning id
            """
        ),
        {"post_id": post_id},
    )
    row = result.first()
    return str(row[0]) if row else None


async def list_posts(
    session: AsyncSession,
    *,
    agency_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    result = await session.execute(
        text(
            """
            select id, social_account_id, status, scheduled_at, attempts,
                   platform_post_id, last_error, published_at
            from posts_queue
            where agency_id = :agency_id
            order by scheduled_at desc
            limit :limit
            """
        ),
        {"agency_id": agency_id, "limit": limit},
    )
    return [dict(r) for r in result.mappings().all()]


async def set_account_rate_limited(
    session: AsyncSession,
    *,
    account_id: str,
    cooldown_seconds: int,
) -> None:
    await session.execute(
        text(
            """
            update social_accounts
            set status = 'rate_limited',
                rate_limited_until = now() + (:cooldown * interval '1 second'),
                updated_at = now()
            where id = :id
            """
        ),
        {"id": account_id, "cooldown": cooldown_seconds},
    )


async def set_account_active(
    session: AsyncSession,
    *,
    account_id: str,
) -> None:
    await session.execute(
        text(
            """
            update social_accounts
            set status = 'active', rate_limited_until = null, updated_at = now()
            where id = :id and status = 'rate_limited'
            """
        ),
        {"id": account_id},
    )


async def set_account_disconnected(
    session: AsyncSession,
    *,
    account_id: str,
) -> dict[str, Any] | None:
    result = await session.execute(
        text(
            """
            update social_accounts
            set status = 'disconnected', updated_at = now()
            where id = :id
            returning agency_id, platform, external_account_id
            """
        ),
        {"id": account_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def create_reconnect_task(
    session: AsyncSession,
    *,
    agency_id: str,
    platform: str,
    external_account_id: str,
) -> dict[str, Any] | None:
    """Drop a task in the agency's first list asking the team to re-OAuth a
    disconnected account. Returns the created item, or None if no list exists."""

    found = await session.execute(
        text(
            """
            select l.id from lists l
            join workspaces w on w.id = l.workspace_id
            where w.agency_id = :agency_id
            order by l.sort_order
            limit 1
            """
        ),
        {"agency_id": agency_id},
    )
    list_row = found.first()
    if not list_row:
        return None
    list_id = str(list_row[0])

    title = f"Reconectar conta {platform} ({external_account_id})"
    result = await session.execute(
        text(
            """
            insert into items(list_id, agency_id, title, status, fields)
            values (:list_id, :agency_id, :title, 'open', cast(:fields as jsonb))
            returning id
            """
        ),
        {
            "list_id": list_id,
            "agency_id": agency_id,
            "title": title,
            "fields": f'{{"reason":"oauth_disconnected","platform":"{platform}"}}',
        },
    )
    return {"item_id": str(result.scalar_one()), "list_id": list_id, "title": title}
