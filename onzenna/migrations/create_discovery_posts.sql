-- Create onz_discovery_posts table for JP/US content discovery pipeline
-- Run on orbitools EC2: psql -U postgres -d orbitools -f create_discovery_posts.sql

CREATE TABLE IF NOT EXISTS onz_discovery_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Post identity
    handle VARCHAR(200) NOT NULL,
    full_name VARCHAR(200) DEFAULT '',
    platform VARCHAR(30) NOT NULL,
    url VARCHAR(500) NOT NULL UNIQUE,
    post_date DATE,

    -- Content
    content_type VARCHAR(30) DEFAULT '',
    caption TEXT DEFAULT '',
    hashtags TEXT DEFAULT '',
    mentions VARCHAR(500) DEFAULT '',
    transcript TEXT DEFAULT '',

    -- Metrics
    followers INTEGER,
    views INTEGER,
    likes INTEGER,
    comments_count INTEGER,

    -- Discovery metadata
    source VARCHAR(100) DEFAULT '',
    region VARCHAR(10) NOT NULL DEFAULT 'jp',
    discovery_batch VARCHAR(50) DEFAULT '',

    -- Outreach tracking
    outreach_status VARCHAR(30) NOT NULL DEFAULT 'discovered',
    outreach_email VARCHAR(254) DEFAULT '',
    outreach_date DATE,
    outreach_notes TEXT DEFAULT '',

    -- Link to pipeline_creators
    pipeline_creator_id UUID,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_discovery_handle ON onz_discovery_posts (handle);
CREATE INDEX IF NOT EXISTS idx_discovery_platform ON onz_discovery_posts (platform);
CREATE INDEX IF NOT EXISTS idx_discovery_region ON onz_discovery_posts (region);
CREATE INDEX IF NOT EXISTS idx_discovery_region_status ON onz_discovery_posts (region, outreach_status);
CREATE INDEX IF NOT EXISTS idx_discovery_handle_platform ON onz_discovery_posts (handle, platform);
CREATE INDEX IF NOT EXISTS idx_discovery_pipeline_creator ON onz_discovery_posts (pipeline_creator_id);
CREATE INDEX IF NOT EXISTS idx_discovery_url ON onz_discovery_posts (url);

-- Verify
SELECT 'onz_discovery_posts created' AS result,
       (SELECT count(*) FROM information_schema.columns
        WHERE table_name = 'onz_discovery_posts') AS column_count;
