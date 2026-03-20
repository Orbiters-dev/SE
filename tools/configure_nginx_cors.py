"""Configure nginx to allow CORS preflight (OPTIONS) without Basic Auth.

1. Drops a map directive into /etc/nginx/conf.d/ (avoids modifying nginx.conf).
2. Cleans up broken entries from previous sed attempts.
3. Injects OPTIONS CORS handler into site config (returns 204 with CORS headers
   directly from nginx, so Django doesn't need to handle preflight).
Run on EC2: sudo python3 configure_nginx_cors.py
"""
import subprocess
import re
import sys
import os
import shutil
import glob

NGINX_CONF = "/etc/nginx/nginx.conf"
MAP_CONF = "/etc/nginx/conf.d/cors_preflight_map.conf"
MAP_CONTENT = """# Skip Basic Auth for OPTIONS requests (CORS preflight)
map $request_method $auth_type {
    OPTIONS "off";
    default "Restricted";
}
"""

CORS_BLOCK = """
        # CORS preflight: return headers directly from nginx
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' 'https://orbiters-dev.github.io' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;
            add_header 'Access-Control-Max-Age' '86400' always;
            return 204;
        }
"""

ALLOWED_ORIGIN = "https://orbiters-dev.github.io"


def cleanup_nginx_conf():
    """Remove broken entries from previous sed/heredoc attempts in nginx.conf."""
    with open(NGINX_CONF, "r") as f:
        content = f.read()

    original = content

    # Remove broken map blocks (complete or partial)
    content = re.sub(r'# Skip auth for OPTIONS.*?}', '', content, flags=re.DOTALL)
    content = re.sub(r'map \$request_method \$auth_type\s*\{[^}]*\}', '', content)

    # Remove ANY line where the first non-whitespace token is a standalone 'n'
    lines = content.split('\n')
    clean = []
    for line in lines:
        s = line.strip()
        if s == 'n' or s.startswith('n ') or s.startswith('n\t'):
            print(f"  CLEANUP: removed broken line: {repr(line)}")
            continue
        clean.append(line)
    content = '\n'.join(clean)

    # Remove excessive blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)

    if content != original:
        shutil.copy2(NGINX_CONF, NGINX_CONF + ".bak")
        with open(NGINX_CONF, "w") as f:
            f.write(content)
        print("OK: nginx.conf cleaned up")
    else:
        print("SKIP: nginx.conf (no broken entries found)")


def write_map_conf():
    """Write map directive to conf.d/."""
    os.makedirs(os.path.dirname(MAP_CONF), exist_ok=True)
    with open(MAP_CONF, "w") as f:
        f.write(MAP_CONTENT)
    print(f"OK: {MAP_CONF} written")


def fix_site_config():
    """Fix site configs: auth_basic variable + CORS OPTIONS handler."""
    sites = glob.glob("/etc/nginx/sites-enabled/*") + glob.glob("/etc/nginx/sites-available/*")
    for site_path in sites:
        with open(site_path, "r") as f:
            content = f.read()

        original = content

        # Remove broken cors-preflight includes
        content = re.sub(r'\s*include snippets/cors-preflight\.conf;\s*', '\n', content)

        # Replace auth_basic "string" with auth_basic $auth_type;
        content = re.sub(r'auth_basic\s+"[^"]*"\s*;', 'auth_basic $auth_type;', content)
        content = re.sub(r"auth_basic\s+'[^']*'\s*;", 'auth_basic $auth_type;', content)

        # Remove any previous CORS blocks (complete if/return blocks)
        content = re.sub(
            r'\s*# CORS preflight:.*?return 204;\s*\}',
            '', content, flags=re.DOTALL
        )
        # Also remove stale Access-Control add_header lines
        content = re.sub(r"\s*add_header 'Access-Control-[^']*' '[^']*'[^;]*;\n?", '', content)

        # Inject CORS OPTIONS handler into each location / { } block
        # Insert right after 'location / {'
        if "# CORS preflight:" not in content and 'proxy_pass' in content:
            content = re.sub(
                r'(location\s+/\s*\{)',
                r'\1' + CORS_BLOCK,
                content,
                count=1,
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
        bak = NGINX_CONF + ".bak"
        if os.path.exists(bak):
            shutil.copy2(bak, NGINX_CONF)
            print("RESTORED: nginx.conf reverted to backup")
        if os.path.exists(MAP_CONF):
            os.remove(MAP_CONF)
            print(f"REMOVED: {MAP_CONF}")
        sys.exit(1)
    print("OK: nginx config test passed")

    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print("OK: nginx reloaded")


if __name__ == "__main__":
    print("=== Step 1: Cleanup broken nginx.conf entries ===")
    cleanup_nginx_conf()
    print("=== Step 2: Write map directive to conf.d ===")
    write_map_conf()
    print("=== Step 3: Fix site configs (auth + CORS) ===")
    fix_site_config()
    print("=== Step 4: Test and reload ===")
    test_and_reload()
