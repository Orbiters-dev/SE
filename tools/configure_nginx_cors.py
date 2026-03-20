"""Configure nginx to allow CORS preflight (OPTIONS) without Basic Auth.

Uses map directive to conditionally disable auth for OPTIONS requests.
Run on EC2: python3 configure_nginx_cors.py
"""
import subprocess
import re
import sys

NGINX_CONF = "/etc/nginx/nginx.conf"
MAP_BLOCK = """
    # Skip auth for OPTIONS (CORS preflight)
    map $request_method $auth_type {
        OPTIONS "off";
        default "Restricted";
    }
"""


def fix_nginx_conf():
    """Add map directive to nginx.conf if missing, and clean up broken entries."""
    with open(NGINX_CONF, "r") as f:
        content = f.read()

    # Backup before modifying
    with open(NGINX_CONF + ".bak", "w") as f:
        f.write(content)

    # Remove broken map blocks and comments from previous attempts
    content = re.sub(r'# Skip auth for OPTIONS.*?}\s*}', '', content, flags=re.DOTALL)
    content = re.sub(r'map \$request_method \$auth_type\s*\{[^}]*\}', '', content)

    # Remove broken 'n' lines from previous sed \n escaping failures
    lines = content.split('\n')
    lines = [l for l in lines if l.strip() != 'n']
    content = '\n'.join(lines)

    # Clean up excessive blank lines (3+ → 2)
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Add map block inside http { ... }
    if 'map $request_method $auth_type' not in content:
        content = content.replace('http {', 'http {' + MAP_BLOCK, 1)

    with open(NGINX_CONF, "w") as f:
        f.write(content)
    print("OK: nginx.conf map directive added")


def fix_site_config():
    """Replace hardcoded auth_basic with variable $auth_type."""
    import glob
    sites = glob.glob("/etc/nginx/sites-enabled/*") + glob.glob("/etc/nginx/sites-available/*")
    for site_path in sites:
        with open(site_path, "r") as f:
            content = f.read()

        original = content

        # Remove any broken cors-preflight includes
        content = re.sub(r'\s*include snippets/cors-preflight\.conf;\s*', '\n', content)
        # Remove stale Access-Control headers
        content = re.sub(r'.*[Aa]ccess-[Cc]ontrol.*\n', '', content)

        # Replace auth_basic "..." with auth_basic $auth_type;
        # But keep auth_basic_user_file as-is
        content = re.sub(
            r'auth_basic\s+"[^"]*"\s*;',
            'auth_basic $auth_type;',
            content,
        )
        # Also handle auth_basic 'string';
        content = re.sub(
            r"auth_basic\s+'[^']*'\s*;",
            'auth_basic $auth_type;',
            content,
        )

        if content != original:
            with open(site_path, "w") as f:
                f.write(content)
            print(f"OK: {site_path} updated")
        else:
            print(f"SKIP: {site_path} (no changes needed)")


def test_and_reload():
    """Test nginx config and reload. Restore backup on failure."""
    result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: nginx test failed:\n{result.stderr}")
        # Restore backup
        bak = NGINX_CONF + ".bak"
        import os
        if os.path.exists(bak):
            import shutil
            shutil.copy2(bak, NGINX_CONF)
            print("RESTORED: nginx.conf reverted to backup")
        sys.exit(1)
    print("OK: nginx config test passed")

    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print("OK: nginx reloaded")


if __name__ == "__main__":
    fix_nginx_conf()
    fix_site_config()
    test_and_reload()
