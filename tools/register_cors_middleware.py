"""Register CorsMiddleware in Django production settings.

Run on EC2: python3 register_cors_middleware.py
Idempotent: safe to run multiple times.
"""
import sys

SETTINGS_PATH = "export_calculator/settings/production.py"
MIDDLEWARE_CLASS = "onzenna.middleware.CorsMiddleware"


def main():
    with open(SETTINGS_PATH, "r") as f:
        content = f.read()

    if MIDDLEWARE_CLASS in content:
        print(f"SKIP: {MIDDLEWARE_CLASS} already in settings")
        return

    if "MIDDLEWARE" not in content:
        print(f"ERROR: MIDDLEWARE not found in {SETTINGS_PATH}")
        sys.exit(1)

    # Insert at the TOP of MIDDLEWARE list (before other middleware)
    content = content.replace(
        "MIDDLEWARE = [",
        f"MIDDLEWARE = [\n    '{MIDDLEWARE_CLASS}',",
    )

    with open(SETTINGS_PATH, "w") as f:
        f.write(content)
    print(f"OK: Added {MIDDLEWARE_CLASS} to MIDDLEWARE")


if __name__ == "__main__":
    main()
