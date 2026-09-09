-- 0001_init.sql
-- HermesBoost milestone 1: organizations, datasets, dataset_profiles, LLM config/logging.
-- Modeling tables (modeling_specs, models, model_runs, model_metrics, scheduled_scores)
-- are deliberately deferred to a later migration -- nothing in this milestone touches them.

create extension if not exists pgcrypto;  -- gen_random_uuid()

create table organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  monthly_llm_budget_usd numeric(10,2) not null default 20.00,
  created_at timestamptz not null default now()
);

create table datasets (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  name text not null,                         -- original filename
  storage_bucket text not null default 'datasets',
  storage_path text not null,                 -- e.g. {organization_id}/{dataset_id}/{filename}
  content_hash text not null,                 -- sha256 of raw file bytes
  size_bytes bigint,
  row_count integer,
  column_count integer,
  status text not null default 'uploaded'
    check (status in ('uploaded','profiling','profiled','error')),
  error_message text,
  uploaded_by text,                           -- Supabase auth user id/email; nullable in dev-auth mode
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_datasets_org on datasets(organization_id);

create table dataset_profiles (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  dataset_id uuid not null references datasets(id) on delete cascade,
  content_hash text not null,
  row_count integer not null,
  column_count integer not null,
  columns jsonb not null,        -- [{name, dtype, null_rate, distinct_count, min, max, top_values:[{value,count}], histogram:[int;8]}]
  ai_description text,
  ai_description_model text,
  ai_description_generated_at timestamptz,
  profiled_at timestamptz not null default now(),
  unique (organization_id, content_hash)
);
create index idx_dataset_profiles_org_hash on dataset_profiles(organization_id, content_hash);

create table llm_task_model_config (
  task_type text primary key,
  model_id text not null default 'claude-opus-5',
  updated_at timestamptz not null default now()
);

create table llm_usage_log (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  task_type text not null,
  model_id text not null,
  trigger text,                   -- e.g. 'dataset_upload:<dataset_id>'
  input_tokens integer not null,
  output_tokens integer not null,
  cost_estimate_usd numeric(10,4) not null,
  stop_reason text,
  request_id text,
  related_table text,
  related_id uuid,
  created_at timestamptz not null default now()
);
create index idx_llm_usage_org_created on llm_usage_log(organization_id, created_at);

-- seed
insert into organizations (name, slug) values ('Default Organization', 'default');
insert into llm_task_model_config (task_type, model_id) values ('dataset_description', 'claude-opus-5');
