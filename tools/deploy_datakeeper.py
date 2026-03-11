"""Deploy Data Keeper Django app to orbiters_2 EC2.

This script generates the commands to run on EC2 via Instance Connect.
Copy-paste the output into the EC2 terminal.

Usage:
    python tools/deploy_datakeeper.py
"""

import os
import sys

# Read the source files
DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
APP_DIR = os.path.join(ROOT, "datakeeper")

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
    print("  DATA KEEPER - EC2 DEPLOYMENT COMMANDS")
    print("  Run these on orbiters_2 EC2 via Instance Connect")
    print("=" * 70)
    print()

    # Step 1: Create app directory
    print("# Step 1: Create datakeeper app directory")
    print("cd /home/ubuntu/export_calculator")
    print("mkdir -p datakeeper")
    print()

    # Step 2: Write each file
    for fname, fpath in files_to_deploy.items():
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        # Escape for heredoc
        print(f"# --- {fname} ---")
        print(f"cat > datakeeper/{fname} << 'DATAKEEPER_EOF'")
        print(content)
        print("DATAKEEPER_EOF")
        print()

    # Step 3: Add to INSTALLED_APPS
    print("# Step 3: Add 'datakeeper' to INSTALLED_APPS (if not already)")
    print("# Check current settings:")
    print("grep -n 'datakeeper' export_calculator/settings/production.py || echo 'NOT FOUND - need to add'")
    print()
    print("# If not found, add to INSTALLED_APPS:")
    print("""python3 -c "
import re
path = 'export_calculator/settings/production.py'
with open(path, 'r') as f:
    content = f.read()
if 'datakeeper' not in content:
    # Find INSTALLED_APPS and add datakeeper
    content = content.replace(
        \"'onzenna',\",
        \"'onzenna',\\n    'datakeeper',\"
    )
    with open(path, 'w') as f:
        f.write(content)
    print('Added datakeeper to INSTALLED_APPS')
else:
    print('datakeeper already in INSTALLED_APPS')
"
""")

    # Step 4: Add URL routing
    print("# Step 4: Add URL routing (if not already)")
    print("grep -n 'datakeeper' export_calculator/urls.py || echo 'NOT FOUND - need to add'")
    print()
    print("""python3 -c "
path = 'export_calculator/urls.py'
with open(path, 'r') as f:
    content = f.read()
if 'datakeeper' not in content:
    # Add import and urlpattern
    content = content.replace(
        'urlpatterns = [',
        'urlpatterns = [\\n    path(\"api/datakeeper/\", include(\"datakeeper.urls\")),'
    )
    if 'from django.urls import' in content and 'include' not in content.split('from django.urls import')[1].split('\\n')[0]:
        content = content.replace(
            'from django.urls import path',
            'from django.urls import path, include'
        )
    with open(path, 'w') as f:
        f.write(content)
    print('Added datakeeper URLs')
else:
    print('datakeeper URLs already configured')
"
""")

    # Step 5: Migrate
    print("# Step 5: Run migrations")
    print("python3 manage.py makemigrations datakeeper --settings=export_calculator.settings.production")
    print("python3 manage.py migrate datakeeper --settings=export_calculator.settings.production")
    print()

    # Step 6: Restart service
    print("# Step 6: Restart service")
    print("sudo systemctl restart export_calculator")
    print("sudo systemctl status export_calculator")
    print()

    # Step 7: Verify
    print("# Step 7: Verify endpoints")
    print("curl -u admin:PASSWORD https://orbitools.orbiters.co.kr/api/datakeeper/tables/")
    print("curl -u admin:PASSWORD https://orbitools.orbiters.co.kr/api/datakeeper/status/")
    print()

    print("=" * 70)
    print("  DONE - After running all steps above, the API should be live.")
    print("=" * 70)


if __name__ == "__main__":
    generate_ec2_commands()
