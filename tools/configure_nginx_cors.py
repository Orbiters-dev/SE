"""Configure nginx to allow CORS preflight (OPTIONS) without Basic Auth.

Uses named location @cors_preflight to avoid 'if is evil' with add_header.
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

# Named location avoids nginx 'if is evil' issues with add_header
CORS_NAMED_LOCATION = """
    # CORS preflight handler (named location to avoid if+add_header bug)
    location @cors_preflight {
        add_header 'Access-Control-Allow-Origin' 'https://orbiters-dev.github.io' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Content-Type, Authorization' always;
        add_header 'Access-Control-Max-Age' '86400' always;
        return 204;
    }
"""

CORS_IF_BLOCK = """
        # Route OPTIONS to named CORS handler
        error_page 418 = @cors_preflight;
        if ($request_method = 'OPTIONS') {
            return 418;
        }
"""


def cleanup_nginx_conf():
    """Remove broken entries from previous sed/heredoc attempts in nginx.conf."""
    with open(NGINX_CONF, "r") as f:
        content = f.read()

    original = content

    # Remove broken map blocks
    content = re.sub(r'# Skip auth for OPTIONS.*?}', '', content, flags=re.DOTALL)
    content = re.sub(r'map \$request_method \$auth_type\s*\{[^}]*\}', '', content)

    # Remove standalone 'n' lines from broken sed
    lines = content.split('\n')
    clean = [l for l in lines if not (l.strip() == 'n' or l.strip().startswith('n ') or l.strip().startswith('n\t'))]
    content = '\n'.join(clean)
    content = re.sub(r'\n{3,}', '\n\n', content)

    if content != original:
        shutil.copy2(NGINX_CONF, NGINX_CONF + ".bak")
        with open(NGINX_CONF, "w") as f:
            f.write(content)
        print("OK: nginx.conf cleaned up")
    else:
        print("SKIP: nginx.conf clean")


def write_map_conf():
    """Write map directive to conf.d/."""
    os.makedirs(os.path.dirname(MAP_CONF), exist_ok=True)
    with open(MAP_CONF, "w") as f:
        f.write(MAP_CONTENT)
    print(f"OK: {MAP_CONF} written")


def fix_site_config():
    """Fix site configs: auth_basic + CORS via named location."""
    sites = glob.glob("/etc/nginx/sites-enabled/*") + glob.glob("/etc/nginx/sites-available/*")
    for site_path in sites:
        with open(site_path, "r") as f:
            content = f.read()

        # Print first 30 lines for debugging
        if 'production' in site_path:
            print(f"\n--- DEBUG: {site_path} (first 30 lines) ---")
            for i, line in enumerate(content.split('\n')[:30], 1):
                print(f"  {i:3d}: {line}")
            print("--- END DEBUG ---\n")

        original = content

        # Remove broken includes
        content = re.sub(r'\s*include snippets/cors-preflight\.conf;\s*', '\n', content)

        # Replace auth_basic "string" with $auth_type
        content = re.sub(r'auth_basic\s+"[^"]*"\s*;', 'auth_basic $auth_type;', content)
        content = re.sub(r"auth_basic\s+'[^']*'\s*;", 'auth_basic $auth_type;', content)

        # Remove ALL previous CORS blocks (if blocks, named locations, add_header lines)
        content = re.sub(r'\s*# CORS preflight[^\n]*\n?', '', content)
        content = re.sub(r'\s*# Route OPTIONS[^\n]*\n?', '', content)
        content = re.sub(r'\s*error_page 418[^\n]*\n?', '', content)
        content = re.sub(
            r'\s*location @cors_preflight\s*\{[^}]*\}',
            '', content
        )
        content = re.sub(
            r"\s*if \(\$request_method = 'OPTIONS'\)\s*\{[^}]*\}",
            '', content
        )
        content = re.sub(r"\s*add_header 'Access-Control-[^;]*;\n?", '', content)
        content = re.sub(r'\s*return 204;\s*\}\s*\n?', '', content)

        # Only modify production site config (has proxy_pass)
        if 'proxy_pass' not in content:
            if content != original:
                with open(site_path, "w") as f:
                    f.write(content)
                print(f"OK: {site_path} cleaned (no proxy)")
            else:
                print(f"SKIP: {site_path}")
            continue

        # Add named location @cors_preflight before the last closing brace (server block end)
        if '@cors_preflight' not in content:
            # Insert before the last '}' (closing server block)
            last_brace = content.rfind('}')
            content = content[:last_brace] + CORS_NAMED_LOCATION + content[last_brace:]

        # Add if block inside location / { }
        if 'error_page 418' not in content:
            content = re.sub(
                r'(location\s+/\s*\{)',
                r'\1' + CORS_IF_BLOCK,
                content,
                count=1,
            )

        if content != original:
            with open(site_path, "w") as f:
                f.write(content)
            print(f"OK: {site_path} updated (CORS named location)")
        else:
            print(f"SKIP: {site_path} (no changes needed)")


def test_and_reload():
    """Test nginx config and reload. Restore on failure."""
    result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: nginx test failed:\n{result.stderr}")
        bak = NGINX_CONF + ".bak"
        if os.path.exists(bak):
            shutil.copy2(bak, NGINX_CONF)
            print("RESTORED: nginx.conf")
        if os.path.exists(MAP_CONF):
            os.remove(MAP_CONF)
            print(f"REMOVED: {MAP_CONF}")
        sys.exit(1)
    print("OK: nginx config test passed")
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print("OK: nginx reloaded")


if __name__ == "__main__":
    print("=== Step 1: Cleanup nginx.conf ===")
    cleanup_nginx_conf()
    print("=== Step 2: Write map conf ===")
    write_map_conf()
    print("=== Step 3: Fix site configs ===")
    fix_site_config()
    print("=== Step 4: Test and reload ===")
    test_and_reload()
