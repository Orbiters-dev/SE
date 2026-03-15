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
