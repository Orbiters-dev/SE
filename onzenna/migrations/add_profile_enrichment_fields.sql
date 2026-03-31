-- Add profile enrichment fields to onz_pipeline_creators
-- Run on orbitools EC2: psql -U postgres -d orbitools -f add_profile_enrichment_fields.sql

ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS country VARCHAR(50) DEFAULT '';
ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS is_business_account BOOLEAN NULL;
ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS business_category VARCHAR(100) DEFAULT '';
ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS biography TEXT DEFAULT '';
ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NULL;
ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMP WITH TIME ZONE NULL;

-- Index for US-only queries
CREATE INDEX IF NOT EXISTS idx_pipeline_creators_country ON onz_pipeline_creators (country);
CREATE INDEX IF NOT EXISTS idx_pipeline_creators_is_business ON onz_pipeline_creators (is_business_account);
