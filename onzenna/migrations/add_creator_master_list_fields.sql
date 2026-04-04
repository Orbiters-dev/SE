-- Migration: PipelineCreator Master List fields
-- Date: 2026-04-04
-- Part A: Multi-source tracking, Gmail RAG, Cross-check, Shopify PR, Apify D+90

ALTER TABLE onz_pipeline_creators
  -- Multi-source tracking
  ADD COLUMN IF NOT EXISTS sources jsonb DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS first_contacted_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_contacted_at timestamptz,
  ADD COLUMN IF NOT EXISTS contact_count integer DEFAULT 0,

  -- Gmail RAG integration
  ADD COLUMN IF NOT EXISTS gmail_first_contact date,
  ADD COLUMN IF NOT EXISTS gmail_last_contact date,
  ADD COLUMN IF NOT EXISTS gmail_total_sent integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gmail_total_received integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gmail_accounts jsonb DEFAULT '[]'::jsonb,

  -- Cross-check flags
  ADD COLUMN IF NOT EXISTS is_shopify_pr boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_apify_tagged boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_manychat_contact boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS collaboration_status varchar(30) DEFAULT '',

  -- Shopify PR detail
  ADD COLUMN IF NOT EXISTS phone varchar(30) DEFAULT '',
  ADD COLUMN IF NOT EXISTS child_1_birthday varchar(20) DEFAULT '',
  ADD COLUMN IF NOT EXISTS child_2_birthday varchar(20) DEFAULT '',
  ADD COLUMN IF NOT EXISTS pr_products jsonb DEFAULT '[]'::jsonb,

  -- Apify Posted data (D+90 view tracking)
  ADD COLUMN IF NOT EXISTS apify_post_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS apify_posted_brands jsonb DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS apify_last_post_date date,
  ADD COLUMN IF NOT EXISTS apify_last_crawled_at timestamptz,
  ADD COLUMN IF NOT EXISTS apify_posts jsonb DEFAULT '[]'::jsonb;

-- Indexes for cross-check queries
CREATE INDEX IF NOT EXISTS idx_pc_is_shopify_pr ON onz_pipeline_creators (is_shopify_pr) WHERE is_shopify_pr = true;
CREATE INDEX IF NOT EXISTS idx_pc_is_apify_tagged ON onz_pipeline_creators (is_apify_tagged) WHERE is_apify_tagged = true;
CREATE INDEX IF NOT EXISTS idx_pc_email_discovered ON onz_pipeline_creators (email) WHERE email LIKE '%@discovered.syncly';
