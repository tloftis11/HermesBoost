-- 0009_data_acquisition.sql
-- Data-acquisition assistant: an optional, chat-driven agent (web search +
-- web fetch + a custom file-preview tool) that helps a user figure out what
-- data they need and stages candidate datasets for review. Nothing becomes
-- a real, usable dataset until the user explicitly confirms it -- staged
-- datasets sit in datasets.pending_confirmation until then. Additive, no
-- breaking changes to tables from 0001-0008.

create table data_acquisition_sessions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  problem_description text not null,
  raw_messages jsonb not null default '[]',  -- full Anthropic-format history (tool_use/tool_result blocks included) -- required to correctly resume a tool-loop conversation, not just display text
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_data_acq_sessions_org on data_acquisition_sessions(organization_id);

create table data_acquisition_messages (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  session_id uuid not null references data_acquisition_sessions(id) on delete cascade,
  role text not null,
  display_text text not null,  -- human-readable projection for the chat UI (tool calls summarized in plain English)
  staged_dataset_ids jsonb not null default '[]',
  created_at timestamptz not null default now()
);
create index idx_data_acq_messages_session on data_acquisition_messages(session_id);

alter table datasets add column pending_confirmation boolean not null default false;
alter table datasets add column source_url text;
