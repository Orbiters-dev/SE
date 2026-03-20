"""Configure nginx to allow CORS preflight (OPTIONS) without Basic Auth.

Drops a map directive into /etc/nginx/conf.d/ (avoids modifying nginx.conf).
Also cleans up any broken entries from previous sed attempts.
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


def cleanup_nginx_conf():
    """Remove broken entries from previous sed/heredoc attempts in nginx.conf."""
    with open(NGINX_CONF, "r") as f:
        content = f.read()

    original = content

    # Remove broken map blocks (complete or partial)
    content = re.sub(r'# Skip auth for OPTIONS.*?}', '', content, flags=re.DOTALL)
    content = re.sub(r'map \$request_method \$auth_type\s*\{[^}]*\}', '', content)

    # Remove ANY line where the first non-whitespace token is a standalone 'n'
    # These come from broken \n escaping in sed commands
    lines = content.split('\n')
    clean = []
    for line in lines:
        s = line.strip()
        if s == 'n' or s.startswith('n ') or s.startswith('n\t'):
            print(f"  CLEANUP: removed broken line: {repr(line)}")
            continue
        clean.append(line)
    content = '\n'.join(clean)

    # Remove excessive blank lines (3+ consecutive → 1)
    content = re.sub(r'\n{3,}', '\n\n', content)

    if content != original:
        # Backup
        shutil.copy2(NGINX_CONF, NGINX_CONF + ".bak")
        with open(NGINX_CONF, "w") as f:
            f.write(content)
        print("OK: nginx.conf cleaned up")
    else:
        print("SKIP: nginx.conf (no broken entries found)")


def write_map_conf():
    """Write map directive to conf.d/ (included by nginx.conf automatically)."""
    os.makedirs(os.path.dirname(MAP_CONF), exist_ok=True)
    with open(MAP_CONF, "w") as f:
        f.write(MAP_CONTENT)
    print(f"OK: {MAP_CONF} written")


def fix_site_config():
    """Replace hardcoded auth_basic with variable $auth_type."""
    sites = glob.glob("/etc/nginx/sites-enabled/*") + glob.glob("/etc/nginx/sites-available/*")
    for site_path in sites:
        with open(site_path, "r") as f:
            content = f.read()

        original = content

        # Remove broken cors-preflight includes
        content = re.sub(r'\s*include snippets/cors-preflight\.conf;\s*', '\n', content)
        # Remove stale Access-Control headers added by previous attempts
        content = re.sub(r'.*[Aa]ccess-[Cc]ontrol.*\n', '', content)

        # Replace auth_basic "string" with auth_basic $auth_type;
        content = re.sub(r'auth_basic\s+"[^"]*"\s*;', 'auth_basic $auth_type;', content)
        content = re.sub(r"auth_basic\s+'[^']*'\s*;", 'auth_basic $auth_type;', content)

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
        # Restore nginx.conf backup
        bak = NGINX_CONF + ".bak"
        if os.path.exists(bak):
            shutil.copy2(bak, NGINX_CONF)
            print("RESTORED: nginx.conf reverted to backup")
        # Remove our map conf so it doesn't interfere
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
    print("=== Step 3: Fix site configs ===")
    fix_site_config()
    print("=== Step 4: Test and reload ===")
    test_and_reload()
