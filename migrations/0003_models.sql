-- 0003_models.sql
-- HermesBoost milestone 3: build & compare models, plus multi-dataset joins
-- and recurring-feed schema (design doc §4.5/§4.6) -- both additive, no
-- breaking changes to tables from 0001/0002.

-- Multi-dataset joins (design doc §4.5) -- additive, base dataset_id unchanged
create table modeling_spec_join_datasets (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  modeling_spec_id uuid not null references modeling_specs(id) on delete cascade,
  dataset_id uuid not null references datasets(id),
  join_key_column text not null,
  join_type text not null default 'left' check (join_type in ('left','inner')),
  created_at timestamptz not null default now()
);
create index idx_spec_join_datasets_spec on modeling_spec_join_datasets(modeling_spec_id);

-- Recurring feeds (design doc §4.6) -- schema only this milestone
create table dataset_series (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  name text not null,
  created_at timestamptz not null default now(),
  unique (organization_id, name)
);
alter table datasets add column series_id uuid references dataset_series(id);
alter table datasets add column as_of_date date;

-- The spec's stable model "slot"
create table models (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  modeling_spec_id uuid not null references modeling_specs(id) on delete cascade,
  status text not null default 'training' check (status in ('training','ready','error')),
  active_candidate_id uuid,  -- FK added below, after model_candidates exists
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_models_org_spec on models(organization_id, modeling_spec_id);

-- One training attempt
create table model_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  model_id uuid not null references models(id) on delete cascade,
  run_type text not null default 'train' check (run_type in ('train','score')),
  status text not null default 'running' check (status in ('running','completed','error')),
  ml_task text,
  row_count_used integer,
  warnings jsonb,
  error_message text,
  interpretation_summary text,
  interpretation_key_drivers jsonb,
  interpretation_model text,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);
create index idx_model_runs_model on model_runs(model_id, started_at desc);

-- One fitted candidate (4 per successful run: 1 recommended + 3 baseline)
create table model_candidates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  model_run_id uuid not null references model_runs(id) on delete cascade,
  role text not null check (role in ('recommended','baseline')),
  algorithm text not null,               -- 'flaml_automl' | 'logistic_regression' | 'random_forest' | 'xgboost' | 'linear_regression'
  ml_task text not null check (ml_task in ('classification','regression')),
  feature_columns jsonb not null,
  feature_dtypes jsonb not null,         -- {col: 'numeric'|'categorical'}
  target_column text not null,
  label_classes jsonb,                    -- classification only
  metrics jsonb not null,
  feature_importance jsonb,               -- [{feature, importance}], top ~15
  hyperparams jsonb,
  train_time_seconds numeric(10,2),
  storage_bucket text,
  storage_path text,
  created_at timestamptz not null default now()
);
create index idx_model_candidates_run on model_candidates(model_run_id);

alter table models add constraint fk_models_active_candidate
  foreign key (active_candidate_id) references model_candidates(id);

insert into llm_task_model_config (task_type, model_id) values ('model_interpretation', 'claude-opus-5');
