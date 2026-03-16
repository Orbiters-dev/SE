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
]

if __name__ == "__main__":
    with connection.cursor() as cursor:
        for sql in TABLES:
            table_name = sql.split("IF NOT EXISTS ")[1].split(" (")[0]
            cursor.execute(sql)
            print(f"OK: {table_name}")

    # Clear stale migration history and re-fake
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM django_migrations WHERE app='datakeeper'")
        print(f"Cleared {cursor.rowcount} migration records")

    print("Done! Now run: python3 manage.py makemigrations datakeeper && python3 manage.py migrate datakeeper --fake")
