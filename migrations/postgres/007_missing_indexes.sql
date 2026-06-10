-- 007_missing_indexes.sql
-- Índices identificados como faltando na análise de performance

-- social_accounts: busca por agency é frequente mas sem índice
CREATE INDEX IF NOT EXISTS idx_social_accounts_agency
    ON social_accounts(agency_id);

-- chat_sessions: get_or_create_session busca por (contact_id, channel)
CREATE INDEX IF NOT EXISTS idx_chat_sessions_contact_channel
    ON chat_sessions(contact_id, channel);

-- lists: adiciona updated_at para suporte a sincronização incremental
ALTER TABLE lists ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_lists_workspace_updated
    ON lists(workspace_id, updated_at DESC);
