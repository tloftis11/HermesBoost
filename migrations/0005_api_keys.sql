-- 0005_api_keys.sql
-- HermesBoost milestone 6: real, revocable, per-organization API keys --
-- replaces the single-shared-key placeholder. Additive, no breaking
-- changes to tables from 0001-0004.

create table api_keys (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references organizations(id),
  name text not null,
  key_prefix text not null,       -- first ~12 chars, shown in the UI list
  key_hash text not null unique,  -- sha256 of the full raw key; raw key never stored
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at timestamptz
);
create index idx_api_keys_org on api_keys(organization_id);
