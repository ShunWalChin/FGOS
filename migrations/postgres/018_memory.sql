-- Phase 19 (Memória semântica / RAG) — original FGOS rewrite of RuVector's core idea
-- (vector memory + hybrid sparse+dense retrieval) on Postgres + pgvector. Multi-tenant.

create extension if not exists vector;

create table if not exists memory_documents (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  kind text not null default 'note',     -- note | brand | content | url | faq
  title text not null,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_memory_docs_agency on memory_documents(agency_id);

create table if not exists memory_chunks (
  id uuid primary key default gen_random_uuid(),
  agency_id uuid not null,
  document_id uuid not null references memory_documents(id) on delete cascade,
  chunk_index int not null default 0,
  content text not null,
  embedding vector(1536),
  tsv tsvector generated always as (to_tsvector('portuguese', content)) stored,
  created_at timestamptz not null default now()
);
create index if not exists idx_memory_chunks_doc on memory_chunks(document_id);
create index if not exists idx_memory_chunks_agency on memory_chunks(agency_id);
create index if not exists idx_memory_chunks_tsv on memory_chunks using gin(tsv);
create index if not exists idx_memory_chunks_vec on memory_chunks using hnsw (embedding vector_cosine_ops);
