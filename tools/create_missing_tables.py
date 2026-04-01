"""Create missing Data Keeper tables on EC2 PostgreSQL.

Run on EC2: python3 create_missing_tables.py
"""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "export_calculator.settings.production")

import django
django.setup()

from django.db import connection

TABLES = [
    """CREATE TABLE IF NOT EXISTS gk_amazon_ads_search_terms (
        id SERIAL PRIMARY KEY,
        date VARCHAR(30) NOT NULL,
        profile_id VARCHAR(50) NOT NULL,
        brand VARCHAR(100) NOT NULL,
        campaign_id VARCHAR(50) NOT NULL,
        ad_group_id VARCHAR(50) NOT NULL,
        keyword_id VARCHAR(50) DEFAULT '',
        search_term VARCHAR(500) NOT NULL,
        impressions INTEGER DEFAULT 0,
        clicks INTEGER DEFAULT 0,
        spend NUMERIC(12,2) DEFAULT 0,
        sales NUMERIC(12,2) DEFAULT 0,
        purchases INTEGER DEFAULT 0,
        collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(date, profile_id, campaign_id, ad_group_id, search_term)
    )""",
    """CREATE TABLE IF NOT EXISTS gk_amazon_ads_keywords (
        id SERIAL PRIMARY KEY,
        date VARCHAR(30) NOT NULL,
        profile_id VARCHAR(50) NOT NULL,
        brand VARCHAR(100) NOT NULL,
        campaign_id VARCHAR(50) NOT NULL,
        ad_group_id VARCHAR(50) NOT NULL,
        keyword_id VARCHAR(50) DEFAULT '',
        keyword_text VARCHAR(500) DEFAULT '',
        match_type VARCHAR(30) DEFAULT '',
        impressions INTEGER DEFAULT 0,
        clicks INTEGER DEFAULT 0,
        spend NUMERIC(12,2) DEFAULT 0,
        sales NUMERIC(12,2) DEFAULT 0,
        purchases INTEGER DEFAULT 0,
        collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(date, profile_id, campaign_id, ad_group_id, keyword_id)
    )""",
    """CREATE TABLE IF NOT EXISTS gk_content_posts (
        id SERIAL PRIMARY KEY,
        post_id VARCHAR(200) UNIQUE NOT NULL,
        url VARCHAR(1000) DEFAULT '',
        platform VARCHAR(20) NOT NULL,
        username VARCHAR(200) NOT NULL,
        nickname VARCHAR(200) DEFAULT '',
        followers INTEGER DEFAULT 0,
        caption TEXT DEFAULT '',
        hashtags TEXT DEFAULT '',
        tagged_account VARCHAR(200) DEFAULT '',
        post_date DATE NOT NULL,
        brand VARCHAR(100) DEFAULT '',
        region VARCHAR(10) DEFAULT 'us',
        source VARCHAR(20) DEFAULT 'syncly',
        collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS gk_content_metrics_daily (
        id SERIAL PRIMARY KEY,
        post_id VARCHAR(200) NOT NULL,
        date DATE NOT NULL,
        comments INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        views INTEGER DEFAULT 0,
        collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(post_id, date)
    )""",
    """CREATE TABLE IF NOT EXISTS gk_amazon_brand_analytics (
        id SERIAL PRIMARY KEY,
        date DATE NOT NULL,
        week_end DATE NOT NULL,
        brand VARCHAR(100) NOT NULL,
        is_ours BOOLEAN DEFAULT FALSE,
        department VARCHAR(200) DEFAULT '',
        search_term VARCHAR(500) NOT NULL,
        search_frequency_rank INTEGER DEFAULT 0,
        asin VARCHAR(20) NOT NULL,
        asin_name VARCHAR(200) DEFAULT '',
        asin_rank INTEGER DEFAULT 0,
        click_share NUMERIC(8,4) DEFAULT 0,
        conversion_share NUMERIC(8,4) DEFAULT 0,
        collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(date, search_term, asin)
    )""",
    """CREATE TABLE IF NOT EXISTS gk_google_ads_search_terms (
        id SERIAL PRIMARY KEY,
        date DATE NOT NULL,
        customer_id VARCHAR(50) NOT NULL,
        campaign_id VARCHAR(50) NOT NULL,
        campaign_name VARCHAR(500) NOT NULL,
        ad_group_id VARCHAR(50) NOT NULL,
        ad_group_name VARCHAR(500) NOT NULL,
        search_term VARCHAR(500) NOT NULL,
        brand VARCHAR(100) NOT NULL,
        impressions INTEGER DEFAULT 0,
        clicks INTEGER DEFAULT 0,
        spend NUMERIC(12,2) DEFAULT 0,
        conversions NUMERIC(10,2) DEFAULT 0,
        conversion_value NUMERIC(12,2) DEFAULT 0,
        collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(date, campaign_id, ad_group_id, search_term)
    )""",
    """CREATE TABLE IF NOT EXISTS gk_influencer_orders (
        id SERIAL PRIMARY KEY,
        order_id VARCHAR(50) UNIQUE NOT NULL,
        order_name VARCHAR(50) DEFAULT '',
        customer_name VARCHAR(200) NOT NULL,
        customer_email VARCHAR(200) DEFAULT '',
        account_handle VARCHAR(200) DEFAULT '',
        channel VARCHAR(20) DEFAULT '',
        product_types TEXT DEFAULT '',
        product_names TEXT DEFAULT '',
        influencer_fee NUMERIC(10,2) DEFAULT 0,
        shipping_date DATE,
        fulfillment_status VARCHAR(50) DEFAULT '',
        brand VARCHAR(100) DEFAULT '',
        tags TEXT DEFAULT '',
        collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""",
    # ===== Pipeline CRM tables =====
    """CREATE TABLE IF NOT EXISTS onz_pipeline_creators (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(254) UNIQUE NOT NULL,
        ig_handle VARCHAR(200) DEFAULT '',
        tiktok_handle VARCHAR(200) DEFAULT '',
        full_name VARCHAR(200) DEFAULT '',
        platform VARCHAR(30) DEFAULT '',
        pipeline_status VARCHAR(30) DEFAULT 'Not Started',
        brand VARCHAR(30) DEFAULT '',
        outreach_type VARCHAR(10) DEFAULT '',
        source VARCHAR(30) DEFAULT 'outbound',
        followers INTEGER,
        avg_views INTEGER,
        initial_discovery_date DATE,
        shopify_customer_id VARCHAR(50) DEFAULT '',
        shopify_draft_order_id VARCHAR(50) DEFAULT '',
        shopify_draft_order_name VARCHAR(50) DEFAULT '',
        airtable_record_id VARCHAR(50) DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS onz_pipeline_execution_log (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        action_type VARCHAR(30) NOT NULL,
        triggered_by VARCHAR(50) DEFAULT '',
        target_count INTEGER DEFAULT 0,
        status VARCHAR(20) DEFAULT 'pending',
        details TEXT DEFAULT '{}',
        started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        completed_at TIMESTAMP WITH TIME ZONE
    )""",
    """CREATE TABLE IF NOT EXISTS onz_pipeline_status_changes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        creator_email VARCHAR(254) NOT NULL,
        from_status VARCHAR(30) NOT NULL,
        to_status VARCHAR(30) NOT NULL,
        changed_by VARCHAR(50) DEFAULT '',
        changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS onz_pipeline_conversations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        creator_email VARCHAR(254) NOT NULL,
        direction VARCHAR(10) NOT NULL,
        subject VARCHAR(500) DEFAULT '',
        message_content TEXT DEFAULT '',
        brand VARCHAR(30) DEFAULT '',
        outreach_type VARCHAR(10) DEFAULT '',
        gmail_message_id VARCHAR(200) DEFAULT '',
        gmail_thread_id VARCHAR(200) DEFAULT '',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS gk_gmail_contacts (
        id SERIAL PRIMARY KEY,
        email VARCHAR(254) UNIQUE NOT NULL,
        name VARCHAR(255) DEFAULT '',
        domain VARCHAR(255) DEFAULT '',
        account VARCHAR(50) DEFAULT 'zezebaebae',
        first_contact_date TIMESTAMP WITH TIME ZONE,
        last_contact_date TIMESTAMP WITH TIME ZONE,
        last_subject VARCHAR(500) DEFAULT '',
        total_sent INTEGER DEFAULT 0,
        total_received INTEGER DEFAULT 0,
        synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_pipeline_creators_email ON onz_pipeline_creators(email)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_creators_status ON onz_pipeline_creators(pipeline_status)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_creators_brand ON onz_pipeline_creators(brand)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_creators_discovery ON onz_pipeline_creators(initial_discovery_date)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_exec_action ON onz_pipeline_execution_log(action_type)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_status_email ON onz_pipeline_status_changes(creator_email)",
    "CREATE INDEX IF NOT EXISTS idx_gmail_contacts_domain ON gk_gmail_contacts(domain)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_convs_email ON onz_pipeline_conversations(creator_email)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_convs_thread ON onz_pipeline_conversations(gmail_thread_id)",
]

# Column additions (safe — IF NOT EXISTS)
ALTER_COLUMNS = [
    "ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS country VARCHAR(50) DEFAULT ''",
    "ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS is_business_account BOOLEAN NULL",
    "ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS business_category VARCHAR(100) DEFAULT ''",
    "ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS biography TEXT DEFAULT ''",
    "ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NULL",
    "ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS enriched_at TIMESTAMP WITH TIME ZONE NULL",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_creators_country ON onz_pipeline_creators(country)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_creators_is_business ON onz_pipeline_creators(is_business_account)",
    "ALTER TABLE onz_pipeline_creators ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(30) DEFAULT ''",
    # PipelineConfig — columns added in commits 8dda2af, 2687dd1
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS ht_follower_min INTEGER DEFAULT 50000",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS brand_assignees TEXT DEFAULT '{\"Grosmimi\":\"Jeehoo\",\"CHA&MOM\":\"Laeeka\",\"Naeiae\":\"Soyeon\"}'",
    # PipelineConfig — dashboard feature toggles + allocation + account_handles
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS apify_brand_filter BOOLEAN DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS us_only BOOLEAN DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS hil_draft_review BOOLEAN DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS hil_send_approval BOOLEAN DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS hil_sample_approval BOOLEAN DEFAULT FALSE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS alloc_grosmimi INTEGER DEFAULT 5",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS alloc_chaenmom INTEGER DEFAULT 3",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS alloc_naeiae INTEGER DEFAULT 2",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS account_handles TEXT DEFAULT '{}'",
    # PipelineConfig — operational config (migrated from n8n Airtable Config)
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'production'",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS notification_email VARCHAR(200) NOT NULL DEFAULT 'william@pathlightai.io'",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS only_pull_with_email BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS test_email_override VARCHAR(200) NOT NULL DEFAULT ''",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS tone VARCHAR(50) NOT NULL DEFAULT 'friendly'",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS sign_off VARCHAR(100) NOT NULL DEFAULT 'Best,\nOnzenna'",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS max_body_sentences INTEGER NOT NULL DEFAULT 5",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS assistant_name VARCHAR(50) NOT NULL DEFAULT 'William'",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS brand_name VARCHAR(100) NOT NULL DEFAULT 'Onzenna'",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS company_signer_name VARCHAR(100) NOT NULL DEFAULT 'Jeehoo Jeon'",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS company_signer_title VARCHAR(100) NOT NULL DEFAULT 'CEO'",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS estimated_shipping_days INTEGER NOT NULL DEFAULT 5",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS ht_required_posts INTEGER NOT NULL DEFAULT 2",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS lt_required_posts INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS ht_reminder_days INTEGER NOT NULL DEFAULT 14",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS lt_reminder_days INTEGER NOT NULL DEFAULT 7",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS hil_draft_gen BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS hil_manychat BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE onz_pipeline_config ADD COLUMN IF NOT EXISTS hil_reply_handler BOOLEAN NOT NULL DEFAULT TRUE",
    # Fix existing columns that have NO DEFAULT — set defaults so Django INSERT works
    "ALTER TABLE onz_pipeline_config ALTER COLUMN active SET DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN mode SET DEFAULT 'production'",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN notification_email SET DEFAULT 'william@pathlightai.io'",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN only_pull_with_email SET DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN test_email_override SET DEFAULT ''",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN tone SET DEFAULT 'friendly'",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN sign_off SET DEFAULT 'Best,\nOnzenna'",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN max_body_sentences SET DEFAULT 5",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN assistant_name SET DEFAULT 'William'",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN brand_name SET DEFAULT 'Onzenna'",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN company_signer_name SET DEFAULT 'Jeehoo Jeon'",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN company_signer_title SET DEFAULT 'CEO'",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN estimated_shipping_days SET DEFAULT 5",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN ht_required_posts SET DEFAULT 2",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN lt_required_posts SET DEFAULT 1",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN ht_reminder_days SET DEFAULT 14",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN lt_reminder_days SET DEFAULT 7",
    """CREATE TABLE IF NOT EXISTS gk_amazon_sqp_brand (
        id SERIAL PRIMARY KEY,
        week_end DATE NOT NULL,
        brand VARCHAR(100) NOT NULL,
        search_query VARCHAR(500) NOT NULL,
        search_query_score INTEGER DEFAULT 0,
        search_query_volume INTEGER DEFAULT 0,
        impressions_brand INTEGER DEFAULT 0,
        clicks_brand INTEGER DEFAULT 0,
        clicks_brand_share NUMERIC(8,4) DEFAULT 0,
        purchases_brand INTEGER DEFAULT 0,
        purchases_brand_share NUMERIC(8,4) DEFAULT 0,
        collected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(week_end, brand, search_query)
    )""",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN hil_draft_gen SET DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN hil_manychat SET DEFAULT FALSE",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN hil_reply_handler SET DEFAULT TRUE",
    "ALTER TABLE onz_pipeline_config ALTER COLUMN account_handles SET DEFAULT '{}'",
]

if __name__ == "__main__":
    with connection.cursor() as cursor:
        for sql in TABLES:
            table_name = sql.split("IF NOT EXISTS ")[1].split(" (")[0]
            cursor.execute(sql)
            print(f"OK: {table_name}")

    with connection.cursor() as cursor:
        for sql in INDEXES:
            idx_name = sql.split("IF NOT EXISTS ")[1].split(" ON")[0]
            cursor.execute(sql)
            print(f"IDX: {idx_name}")

    with connection.cursor() as cursor:
        for sql in ALTER_COLUMNS:
            try:
                cursor.execute(sql)
                print(f"COL: {sql.split('ADD COLUMN IF NOT EXISTS ')[-1].split(' ')[0] if 'ADD COLUMN' in sql else sql.split('IF NOT EXISTS ')[-1].split(' ON')[0]}")
            except Exception as e:
                print(f"COL-SKIP: {e}")

    # Clear stale migration history and re-fake
    with connection.cursor() as cursor:
        for app in ['datakeeper', 'onzenna']:
            cursor.execute(f"DELETE FROM django_migrations WHERE app='{app}'")
            print(f"Cleared {cursor.rowcount} migration records for {app}")

    print("Done! Now run:")
    print("  python3 manage.py makemigrations datakeeper onzenna")
    print("  python3 manage.py migrate datakeeper --fake")
    print("  python3 manage.py migrate onzenna --fake")
