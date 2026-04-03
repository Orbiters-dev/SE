"""One-shot email backfill: reads Syncly sheet CSV, updates DB records."""
import csv, io, urllib.request, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'export_calculator.settings.production')

import django
django.setup()

from onzenna.models import PipelineCreator

# Download sheet
url = "https://docs.google.com/spreadsheets/d/1dIAhP8wCEdFulSAai3K-RoZTvLBIaWxAK7hzInBsF0o/export?format=csv&gid=522613099"
data = urllib.request.urlopen(url, timeout=30).read().decode('utf-8')
reader = csv.DictReader(io.StringIO(data))

pairs = {}
for row in reader:
    username = (row.get("Username (id)") or "").strip().lstrip("@").lower()
    email = (row.get("Email") or "").strip()
    if username and email and "@" in email and "@discovered." not in email:
        pairs[username] = email

print(f"Sheet: {len(pairs)} usernames with real emails")

updated = 0
creators = PipelineCreator.objects.filter(email__contains="@discovered.syncly")
print(f"DB: {creators.count()} records with @discovered.syncly")

for c in creators.iterator():
    handle = (c.ig_handle or c.tiktok_handle or "").lower()
    real_email = pairs.get(handle)
    if real_email:
        c.email = real_email
        c.save(update_fields=["email"])
        updated += 1

print(f"Updated: {updated}")
