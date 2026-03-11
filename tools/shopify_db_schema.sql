-- Shopify Customer Data Pipeline - PostgreSQL Schema
-- Run this on EC2 PostgreSQL to create the tables
-- Usage: psql -h <host> -U <user> -d <db> -f shopify_db_schema.sql

BEGIN;

-- ============================================================
-- 1. customers - Shopify 고객 기본정보
-- ============================================================
CREATE TABLE IF NOT EXISTS customers (
    shopify_id          BIGINT PRIMARY KEY,
    email               VARCHAR(255),
    first_name          VARCHAR(255),
    last_name           VARCHAR(255),
    phone               VARCHAR(50),
    tags                TEXT DEFAULT '',
    note                TEXT DEFAULT '',
    orders_count        INTEGER DEFAULT 0,
    total_spent         NUMERIC(12,2) DEFAULT 0,
    state               VARCHAR(50) DEFAULT 'enabled',
    verified_email      BOOLEAN DEFAULT FALSE,
    tax_exempt          BOOLEAN DEFAULT FALSE,
    accepts_marketing   BOOLEAN DEFAULT FALSE,
    shopify_created_at  TIMESTAMPTZ,
    shopify_updated_at  TIMESTAMPTZ,
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_customers_state ON customers(state);
CREATE INDEX IF NOT EXISTS idx_customers_shopify_created ON customers(shopify_created_at);

-- ============================================================
-- 2. addresses - 고객 주소 (배송지 분석용)
-- ============================================================
CREATE TABLE IF NOT EXISTS addresses (
    id                  SERIAL PRIMARY KEY,
    customer_id         BIGINT NOT NULL REFERENCES customers(shopify_id) ON DELETE CASCADE,
    shopify_address_id  BIGINT,
    is_default          BOOLEAN DEFAULT FALSE,
    first_name          VARCHAR(255),
    last_name           VARCHAR(255),
    company             VARCHAR(255),
    address1            TEXT,
    address2            TEXT,
    city                VARCHAR(255),
    province            VARCHAR(255),
    province_code       VARCHAR(10),
    country             VARCHAR(255),
    country_code        VARCHAR(10),
    zip                 VARCHAR(20),
    phone               VARCHAR(50),
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(customer_id, shopify_address_id)
);

CREATE INDEX IF NOT EXISTS idx_addresses_customer ON addresses(customer_id);
CREATE INDEX IF NOT EXISTS idx_addresses_country ON addresses(country_code);
CREATE INDEX IF NOT EXISTS idx_addresses_city ON addresses(city);

-- ============================================================
-- 3. orders - 주문 이력
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    shopify_id          BIGINT PRIMARY KEY,
    order_number        VARCHAR(50),
    customer_id         BIGINT REFERENCES customers(shopify_id) ON DELETE SET NULL,
    email               VARCHAR(255),
    total_price         NUMERIC(12,2) DEFAULT 0,
    subtotal_price      NUMERIC(12,2) DEFAULT 0,
    total_tax           NUMERIC(12,2) DEFAULT 0,
    total_discounts     NUMERIC(12,2) DEFAULT 0,
    currency            VARCHAR(10) DEFAULT 'USD',
    financial_status    VARCHAR(50),
    fulfillment_status  VARCHAR(50),
    tags                TEXT DEFAULT '',
    note                TEXT DEFAULT '',
    discount_codes      JSONB DEFAULT '[]',
    shipping_country    VARCHAR(10),
    shipping_city       VARCHAR(255),
    shipping_province   VARCHAR(255),
    shopify_created_at  TIMESTAMPTZ,
    shopify_updated_at  TIMESTAMPTZ,
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_financial ON orders(financial_status);
CREATE INDEX IF NOT EXISTS idx_orders_fulfillment ON orders(fulfillment_status);
CREATE INDEX IF NOT EXISTS idx_orders_shopify_created ON orders(shopify_created_at);
CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(email);

-- ============================================================
-- 4. line_items - 주문별 상품 상세
-- ============================================================
CREATE TABLE IF NOT EXISTS line_items (
    id                  SERIAL PRIMARY KEY,
    shopify_line_id     BIGINT,
    order_id            BIGINT NOT NULL REFERENCES orders(shopify_id) ON DELETE CASCADE,
    product_id          BIGINT,
    variant_id          BIGINT,
    title               TEXT,
    variant_title       TEXT,
    sku                 VARCHAR(100),
    quantity            INTEGER DEFAULT 1,
    price               NUMERIC(12,2) DEFAULT 0,
    total_discount      NUMERIC(12,2) DEFAULT 0,
    synced_at           TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(order_id, shopify_line_id)
);

CREATE INDEX IF NOT EXISTS idx_line_items_order ON line_items(order_id);
CREATE INDEX IF NOT EXISTS idx_line_items_product ON line_items(product_id);
CREATE INDEX IF NOT EXISTS idx_line_items_sku ON line_items(sku);

-- ============================================================
-- 5. customer_metrics - 계산된 고객 지표 (enrichment)
-- ============================================================
CREATE TABLE IF NOT EXISTS customer_metrics (
    customer_id         BIGINT PRIMARY KEY REFERENCES customers(shopify_id) ON DELETE CASCADE,
    lifetime_value      NUMERIC(12,2) DEFAULT 0,
    order_count         INTEGER DEFAULT 0,
    avg_order_value     NUMERIC(12,2) DEFAULT 0,
    first_order_date    TIMESTAMPTZ,
    last_order_date     TIMESTAMPTZ,
    days_since_last     INTEGER,
    purchase_frequency  NUMERIC(8,4) DEFAULT 0,  -- orders per month
    -- RFM Scores (1-5)
    recency_score       SMALLINT,
    frequency_score     SMALLINT,
    monetary_score      SMALLINT,
    rfm_segment         VARCHAR(50),  -- e.g. 'Champions', 'At Risk', 'New'
    -- 소비 패턴 태그
    pattern_tags        TEXT[] DEFAULT '{}',  -- e.g. {'repeat_buyer', 'high_aov'}
    top_product         TEXT,
    top_category        TEXT,
    calculated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_rfm ON customer_metrics(rfm_segment);
CREATE INDEX IF NOT EXISTS idx_metrics_ltv ON customer_metrics(lifetime_value DESC);

-- ============================================================
-- 6. sync_log - 동기화 이력 추적
-- ============================================================
CREATE TABLE IF NOT EXISTS sync_log (
    id                  SERIAL PRIMARY KEY,
    sync_type           VARCHAR(50) NOT NULL,  -- 'customer', 'order', 'bulk_import', 'enrichment', 'airtable'
    source              VARCHAR(50) NOT NULL,  -- 'shopify_webhook', 'bulk_import', 'scheduled'
    records_processed   INTEGER DEFAULT 0,
    records_failed      INTEGER DEFAULT 0,
    error_message       TEXT,
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    status              VARCHAR(20) DEFAULT 'running'  -- 'running', 'completed', 'failed'
);

CREATE INDEX IF NOT EXISTS idx_sync_log_type ON sync_log(sync_type, started_at DESC);

-- ============================================================
-- Helper function: update updated_at timestamp
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS trg_customers_updated ON customers;
CREATE TRIGGER trg_customers_updated
    BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_orders_updated ON orders;
CREATE TRIGGER trg_orders_updated
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMIT;

-- ============================================================
-- Summary
-- ============================================================
-- Tables created:
--   customers        - Shopify 고객 기본정보
--   addresses        - 배송지 (지역 분석)
--   orders           - 주문 이력
--   line_items       - 주문별 상품 상세
--   customer_metrics - LTV, RFM, 소비패턴 (enrichment)
--   sync_log         - 동기화 이력
--
-- Next steps:
--   1. Run this SQL on EC2 PostgreSQL
--   2. Register Shopify webhooks (setup_shopify_webhooks.py)
--   3. Create n8n workflows (setup_n8n_customer_sync.py, setup_n8n_order_sync.py)
