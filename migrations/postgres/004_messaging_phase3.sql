-- Phase 3 (Messaging) — speed up the hot lookups the conversation engine does
-- on every inbound message: resolve the session for a contact+channel and read
-- a session's message history.

create index if not exists idx_chat_sessions_contact_channel
  on chat_sessions(contact_id, channel);

create index if not exists idx_messages_session
  on messages(session_id, created_at);
