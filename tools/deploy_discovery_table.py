#!/usr/bin/env python3
"""
Deploy Discovery Posts table to EC2.
Generates compact EC2 Instance Connect commands.

Usage:
  python tools/deploy_discovery_table.py
  python tools/deploy_discovery_table.py > .tmp/deploy_discovery.sh

Then copy-paste into EC2 Instance Connect terminal.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "onzenna"


def main():
    # Read current files
    models_py = (APP_DIR / "models.py").read_text(encoding="utf-8")
    views_py = (APP_DIR / "views.py").read_text(encoding="utf-8")
    urls_py = (APP_DIR / "urls.py").read_text(encoding="utf-8")
    migration_sql = (APP_DIR / "migrations" / "create_discovery_posts.sql").read_text(encoding="utf-8")

    print("#!/bin/bash")
    print("# ═══════════════════════════════════════════════")
    print("# DEPLOY: Discovery Posts table + API endpoints")
    print("# Run on orbiters_2 EC2 via Instance Connect")
    print("# ═══════════════════════════════════════════════")
    print()
    print("set -e")
    print("cd /home/ubuntu/export_calculator")
    print()

    # Step 1: Update models.py
    print("# --- Step 1: Update models.py ---")
    print("cat > onzenna/models.py << 'MODELS_EOF'")
    print(models_py)
    print("MODELS_EOF")
    print()

    # Step 2: Update views.py
    print("# --- Step 2: Update views.py ---")
    print("cat > onzenna/views.py << 'VIEWS_EOF'")
    print(views_py)
    print("VIEWS_EOF")
    print()

    # Step 3: Update urls.py
    print("# --- Step 3: Update urls.py ---")
    print("cat > onzenna/urls.py << 'URLS_EOF'")
    print(urls_py)
    print("URLS_EOF")
    print()

    # Step 4: Run SQL migration directly
    print("# --- Step 4: Create discovery_posts table ---")
    print("sudo -u postgres psql -d orbitools << 'SQL_EOF'")
    print(migration_sql)
    print("SQL_EOF")
    print()

    # Step 5: Django migration (to sync ORM state)
    print("# --- Step 5: Django migrate ---")
    print("python3 manage.py makemigrations onzenna --settings=export_calculator.settings.production 2>/dev/null || true")
    print("python3 manage.py migrate onzenna --settings=export_calculator.settings.production 2>/dev/null || true")
    print()

    # Step 6: Restart
    print("# --- Step 6: Restart ---")
    print("sudo systemctl restart export_calculator")
    print("sleep 2")
    print("sudo systemctl status export_calculator --no-pager | head -5")
    print()

    # Step 7: Verify
    print("# --- Step 7: Verify ---")
    print("curl -s -u admin:admin https://orbitools.orbiters.co.kr/api/onzenna/tables/ | python3 -m json.tool 2>/dev/null | grep -A1 discovery")
    print()
    print("# Test discovery endpoint:")
    print("curl -s -u admin:admin 'https://orbitools.orbiters.co.kr/api/onzenna/discovery/posts/stats/' | python3 -m json.tool")
    print()
    print('echo "═══ DEPLOY COMPLETE ═══"')


if __name__ == "__main__":
    main()
