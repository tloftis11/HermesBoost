-- 0008_imbalance_ack.sql
-- Rare-event classification handling: when a target's minority class is
-- detected as imbalanced, the build endpoint asks for one-time
-- acknowledgment before applying class weighting and reporting an
-- additional F1-optimal operating point. Additive, no breaking changes to
-- tables from 0001-0007.

alter table modeling_specs add column acknowledged_imbalance boolean not null default false;
