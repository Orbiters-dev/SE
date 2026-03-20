"""Deploy Onzenna Django app to orbiters_2 EC2.

This script generates the commands to run on EC2 via Instance Connect.
Copy-paste the output into the EC2 terminal.

Usage:
    python tools/deploy_onzenna.py
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
APP_DIR = os.path.join(ROOT, "onzenna")

files_to_deploy = {
    "__init__.py": os.path.join(APP_DIR, "__init__.py"),
    "apps.py": os.path.join(APP_DIR, "apps.py"),
    "models.py": os.path.join(APP_DIR, "models.py"),
    "views.py": os.path.join(APP_DIR, "views.py"),
    "urls.py": os.path.join(APP_DIR, "urls.py"),
    "admin.py": os.path.join(APP_DIR, "admin.py"),
}


def generate_ec2_commands():
    """Generate bash commands to run on EC2."""

    print("=" * 70)
    print("  ONZENNA APP - EC2 DEPLOYMENT COMMANDS")
    print("  Run these on orbiters_2 EC2 via Instance Connect")
    print("=" * 70)
    print()

    # Step 1: Create app directory
    print("# Step 1: Create onzenna app directory")
    print("cd /home/ubuntu/export_calculator")
    print("mkdir -p onzenna")
    print()

    # Step 2: Write each file
    for fname, fpath in files_to_deploy.items():
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        print(f"# --- {fname} ---")
        print(f"cat > onzenna/{fname} << 'ONZENNA_EOF'")
        print(content)
        print("ONZENNA_EOF")
        print()

    # Step 3: Add to INSTALLED_APPS
    print("# Step 3: Add 'onzenna' to INSTALLED_APPS (if not already)")
    print("grep -n 'onzenna' export_calculator/settings/production.py || echo 'NOT FOUND - need to add'")
    print()
    print("""python3 -c "
path = 'export_calculator/settings/production.py'
with open(path, 'r') as f:
    content = f.read()
if 'onzenna' not in content:
    content = content.replace(
        \"'datakeeper',\",
        \"'datakeeper',\\n    'onzenna',\"
    )
    with open(path, 'w') as f:
        f.write(content)
    print('Added onzenna to INSTALLED_APPS')
else:
    print('onzenna already in INSTALLED_APPS')
"
""")

    # Step 4: Add URL routing
    print("# Step 4: Add URL routing (if not already)")
    print("grep -n 'onzenna' export_calculator/urls.py || echo 'NOT FOUND - need to add'")
    print()
    print("""python3 -c "
path = 'export_calculator/urls.py'
with open(path, 'r') as f:
    content = f.read()
if 'onzenna' not in content:
    content = content.replace(
        'urlpatterns = [',
        'urlpatterns = [\\n    path(\"api/onzenna/\", include(\"onzenna.urls\")),'
    )
    if 'from django.urls import' in content and 'include' not in content.split('from django.urls import')[1].split('\\n')[0]:
        content = content.replace(
            'from django.urls import path',
            'from django.urls import path, include'
        )
    with open(path, 'w') as f:
        f.write(content)
    print('Added onzenna URLs')
else:
    print('onzenna URLs already configured')
"
""")

    # Step 5: Add CORS for Vercel domain
    print("# Step 5: Add CORS for Vercel (if django-cors-headers installed)")
    print("""python3 -c "
path = 'export_calculator/settings/production.py'
with open(path, 'r') as f:
    content = f.read()
if 'CORS_ALLOWED_ORIGIN_REGEXES' not in content:
    content += '''

# CORS for Onzenna Vercel frontend
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://.*\\\\.vercel\\\\.app$',
    r'^https://onzenna.*\\\\.vercel\\\\.app$',
    r'^https://orbiters-dev\\\\.github\\\\.io$',
]
CORS_ALLOW_HEADERS = ['content-type', 'authorization']
'''
    with open(path, 'w') as f:
        f.write(content)
    print('Added CORS settings')
else:
    print('CORS settings already configured')
"
""")
    print()
    print("# Install django-cors-headers if needed:")
    print("pip3 install django-cors-headers")
    print("# Then add 'corsheaders' to INSTALLED_APPS and 'corsheaders.middleware.CorsMiddleware' to MIDDLEWARE")
    print()

    # Step 6: Migrate
    print("# Step 6: Run migrations")
    print("python3 manage.py makemigrations onzenna --settings=export_calculator.settings.production")
    print("python3 manage.py migrate onzenna --settings=export_calculator.settings.production")
    print()

    # Step 7: Restart service
    print("# Step 7: Restart service")
    print("sudo systemctl restart export_calculator")
    print("sudo systemctl status export_calculator")
    print()

    # Step 8: Verify
    print("# Step 8: Verify endpoints")
    print("curl -u admin:PASSWORD https://orbitools.orbiters.co.kr/api/onzenna/tables/")
    print()
    print("# Test user creation:")
    print('curl -X POST -u admin:PASSWORD -H "Content-Type: application/json" \\')
    print('  https://orbitools.orbiters.co.kr/api/onzenna/users/ \\')
    print('  -d \'{"id":"00000000-0000-0000-0000-000000000001","email":"test@onzenna.com","full_name":"Test User","auth_provider":"email"}\'')
    print()
    print("# Test pipeline config:")
    print("curl -u admin:PASSWORD https://orbitools.orbiters.co.kr/api/onzenna/pipeline/config/today/")
    print()
    print("# Test pipeline creators API:")
    print("curl -u admin:PASSWORD https://orbitools.orbiters.co.kr/api/onzenna/pipeline/creators/stats/")
    print("curl -u admin:PASSWORD 'https://orbitools.orbiters.co.kr/api/onzenna/pipeline/creators/?limit=5'")
    print("curl -u admin:PASSWORD https://orbitools.orbiters.co.kr/api/onzenna/pipeline/execution/log/")
    print()

    print("=" * 70)
    print("  DONE - After running all steps above, the API should be live.")
    print("  Replace PASSWORD with actual admin password from ~/.wat_secrets")
    print("=" * 70)


if __name__ == "__main__":
    generate_ec2_commands()
