-- 0002_intent_chat.sql
-- HermesBoost milestone 2: intent chat + modeling spec.

create table modeling_specs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  dataset_id uuid not null references datasets(id) on delete cascade,
  status text not null default 'draft' check (status in ('draft','confirmed')),
  task_type text,
  task_description text,
  target text,
  candidate_features jsonb not null default '[]',
  evaluation_metric text,
  retrain_cadence text not null default 'weekly'
    check (retrain_cadence in ('daily','weekly','monthly')),
  score_cadence text not null default 'daily'
    check (score_cadence in ('daily','weekly','monthly')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_modeling_specs_org_dataset on modeling_specs(organization_id, dataset_id);

create table chat_messages (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  modeling_spec_id uuid not null references modeling_specs(id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  content text not null,
  created_at timestamptz not null default now()
);
create index idx_chat_messages_spec_created on chat_messages(modeling_spec_id, created_at);

insert into llm_task_model_config (task_type, model_id) values ('intent_chat', 'claude-opus-5');
