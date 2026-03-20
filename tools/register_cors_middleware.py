"""Register CorsMiddleware in Django production settings.

Run on EC2: python3 register_cors_middleware.py
Idempotent: safe to run multiple times.
Handles both cases: MIDDLEWARE defined locally or inherited from base.
"""
import sys

SETTINGS_PATH = "export_calculator/settings/production.py"
MIDDLEWARE_CLASS = "onzenna.middleware.CorsMiddleware"

APPEND_SNIPPET = f"""
# CORS middleware for GH Pages dashboard API access
MIDDLEWARE.insert(0, '{MIDDLEWARE_CLASS}')
"""


def main():
    with open(SETTINGS_PATH, "r") as f:
        content = f.read()

    if MIDDLEWARE_CLASS in content:
        print(f"SKIP: {MIDDLEWARE_CLASS} already in settings")
        return

    if "MIDDLEWARE = [" in content:
        # MIDDLEWARE defined locally: insert at top of list
        content = content.replace(
            "MIDDLEWARE = [",
            f"MIDDLEWARE = [\n    '{MIDDLEWARE_CLASS}',",
        )
    else:
        # MIDDLEWARE inherited from base: append insert statement
        content += APPEND_SNIPPET

    with open(SETTINGS_PATH, "w") as f:
        f.write(content)
    print(f"OK: Added {MIDDLEWARE_CLASS} to MIDDLEWARE")


if __name__ == "__main__":
    main()
