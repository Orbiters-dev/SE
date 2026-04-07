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
    # ===== JP Influencer Pipeline tables (리공이) =====
    """CREATE TABLE IF NOT EXISTS gk_pipeline_creators (
        id SERIAL PRIMARY KEY,
        username VARCHAR(200) UNIQUE NOT NULL,
        name VARCHAR(500) DEFAULT '',
        followers INTEGER DEFAULT 0,
        platform VARCHAR(20) DEFAULT 'instagram',
        program VARCHAR(20) DEFAULT 'collab',
        status VARCHAR(50) DEFAULT 'not_started',
        assigned_to VARCHAR(50) DEFAULT '',
        manychat_id VARCHAR(100) DEFAULT '',
        dm_draft TEXT DEFAULT '',
        dm_link VARCHAR(500) DEFAULT '',
        dm_count INTEGER DEFAULT 0,
        last_dm VARCHAR(50) DEFAULT '',
        content_script TEXT DEFAULT '',
        recommended_product VARCHAR(300) DEFAULT '',
        real_name VARCHAR(200) DEFAULT '',
        email VARCHAR(200) DEFAULT '',
        product VARCHAR(300) DEFAULT '',
        color VARCHAR(100) DEFAULT '',
        contract_type VARCHAR(20) DEFAULT '',
        payment_amount NUMERIC(10,0) DEFAULT 0,
        docuseal_submission_id VARCHAR(100) DEFAULT '',
        contract_status VARCHAR(50) DEFAULT '',
        added_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS gk_pipeline_dm_logs (
        id SERIAL PRIMARY KEY,
        username VARCHAR(200) NOT NULL,
        direction VARCHAR(10) DEFAULT 'out',
        message TEXT DEFAULT '',
        step VARCHAR(20) DEFAULT '',
        sent_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS gk_pipeline_config (
        id SERIAL PRIMARY KEY,
        key VARCHAR(200) UNIQUE NOT NULL,
        value TEXT DEFAULT '',
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
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
    "CREATE INDEX IF NOT EXISTS idx_pipeline_dm_logs_username ON gk_pipeline_dm_logs(username)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_creators_status ON gk_pipeline_creators(status)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_creators_program ON gk_pipeline_creators(program)",
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

    # Clear stale migration history and re-fake
    with connection.cursor() as cursor:
        for app in ['datakeeper', 'onzenna']:
            cursor.execute(f"DELETE FROM django_migrations WHERE app='{app}'")
            print(f"Cleared {cursor.rowcount} migration records for {app}")

    print("Done! Now run:")
    print("  python3 manage.py makemigrations datakeeper onzenna")
    print("  python3 manage.py migrate datakeeper --fake")
    print("  python3 manage.py migrate onzenna --fake")
