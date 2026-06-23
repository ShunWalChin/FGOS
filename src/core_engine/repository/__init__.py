from __future__ import annotations

# Re-export everything from sub-modules so that
# `from core_engine import repository as repo; repo.some_function()` keeps working.

from core_engine.repository.auth import (
    create_agency_with_owner,
    create_user,
    get_branding_by_slug,
    get_user_by_email,
    slug_exists,
    update_branding,
)
from core_engine.repository.base import (
    mark_event_started,
    record_event_failure,
)
from core_engine.repository.messaging import (
    get_or_create_session,
    get_session,
    insert_message,
    set_session_mode,
    update_session_state,
    upsert_contact,
)
from core_engine.repository.social import (
    claim_next_social_post,
    create_reconnect_task,
    enqueue_post,
    insert_social_account,
    list_posts,
    list_social_accounts,
    mark_social_post_failed,
    mark_social_post_published,
    reschedule_repost,
    set_account_active,
    set_account_disconnected,
    set_account_rate_limited,
)

__all__ = [
    # base
    "mark_event_started",
    "record_event_failure",
    # auth / onboarding
    "slug_exists",
    "create_agency_with_owner",
    "get_branding_by_slug",
    "update_branding",
    "create_user",
    "get_user_by_email",
    # social
    "claim_next_social_post",
    "mark_social_post_published",
    "mark_social_post_failed",
    "insert_social_account",
    "list_social_accounts",
    "enqueue_post",
    "reschedule_repost",
    "list_posts",
    "set_account_rate_limited",
    "set_account_active",
    "set_account_disconnected",
    "create_reconnect_task",
    # messaging
    "upsert_contact",
    "get_or_create_session",
    "get_session",
    "insert_message",
    "update_session_state",
    "set_session_mode",
]
