"""
Centralized Environment Loader
===============================
Loads secrets from a secure location outside the NAS shared folder.
All tools should use this instead of loading .env directly.

Usage:
    from env_loader import load_env
    load_env()

Or simply:
    import env_loader  # auto-loads on import
"""

import os
from dotenv import load_dotenv

# Primary: user's home directory (not on NAS)
SECRETS_PATH = os.path.expanduser("~/.wat_secrets")

# Fallback: project .env (for backwards compatibility)
_PROJECT_ENV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)


def load_env():
    """Load environment variables from the secure secrets file."""
    if os.path.exists(SECRETS_PATH):
        load_dotenv(SECRETS_PATH, override=True)
    elif os.path.exists(_PROJECT_ENV):
        load_dotenv(_PROJECT_ENV, override=True)
    else:
        print(f"WARNING: No secrets file found at {SECRETS_PATH} or {_PROJECT_ENV}")


# Auto-load on import
load_env()
