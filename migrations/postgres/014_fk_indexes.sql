-- Phase 14 (DB review) — index every foreign key column. Postgres does NOT auto-index FKs;
-- missing FK indexes slow down JOINs and make ON DELETE CASCADE do sequential scans.
-- Found by the schema audit (fgos_db_audit.sql). All idempotent.

create index if not exists idx_campaign_shipping_contact_item on campaign_shipping(contact_item_id);
create index if not exists idx_campaigns_contact_list on campaigns(contact_list_id);
create index if not exists idx_chat_sessions_agency on chat_sessions(agency_id);
create index if not exists idx_clients_agency on clients(agency_id);
create index if not exists idx_contacts_agency on contacts(agency_id);
create index if not exists idx_content_pieces_brand_voice on content_pieces(brand_voice_id);
create index if not exists idx_deals_contact on deals(contact_id);
create index if not exists idx_deals_pipeline on deals(pipeline_id);
create index if not exists idx_items_agency on items(agency_id);
create index if not exists idx_items_assignee on items(assignee_id);
create index if not exists idx_lists_parent on lists(parent_id);
create index if not exists idx_media_files_parent on media_files(parent_id);
create index if not exists idx_pipelines_agency on pipelines(agency_id);
create index if not exists idx_posts_queue_agency on posts_queue(agency_id);
create index if not exists idx_queue_integrations_queue on queue_integrations(queue_id);
create index if not exists idx_queue_options_parent on queue_options(parent_id);
create index if not exists idx_social_accounts_client on social_accounts(client_id);
create index if not exists idx_stages_pipeline on stages(pipeline_id);
create index if not exists idx_ticket_traking_user on ticket_traking(user_id);
create index if not exists idx_tickets_assigned_user on tickets(assigned_user_id);
create index if not exists idx_tickets_queue on tickets(queue_id);
create index if not exists idx_tickets_queue_option on tickets(queue_option_id);
create index if not exists idx_tickets_session on tickets(session_id);
create index if not exists idx_user_queues_queue on user_queues(queue_id);
create index if not exists idx_workspaces_agency on workspaces(agency_id);
