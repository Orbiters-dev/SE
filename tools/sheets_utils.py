"""
Shared Google Sheets utilities  (M-009 prevention)
====================================================
- safe_range():  quote tab names that contain spaces
- get_sheets_client():  common gspread auth setup

Usage:
    from sheets_utils import safe_range, get_sheets_client

    gc = get_sheets_client()
    sh = gc.open_by_key("SHEET_ID")
    ws = sh.worksheet("US Posts Master")
    ws.spreadsheet.values_batch_update({
        "valueInputOption": "RAW",
        "data": [{"range": safe_range("US Posts Master", "K2:N2"),
                  "values": [[1, 2, 3, "brand"]]}],
    })
"""

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# safe_range  -- M-009: quote tab names with spaces for Sheets API
# ---------------------------------------------------------------------------

def safe_range(tab_name: str, cell_range: str) -> str:
    """Quote tab names with spaces for Sheets API (M-009 prevention).

    >>> safe_range("US Posts Master", "A1:Z50")
    "'US Posts Master'!A1:Z50"
    >>> safe_range("SNS", "A1:Z50")
    "SNS!A1:Z50"
    >>> safe_range("'Already Quoted'", "B2")
    "'Already Quoted'!B2"
    """
    if " " in tab_name and not tab_name.startswith("'"):
        return f"'{tab_name}'!{cell_range}"
    return f"{tab_name}!{cell_range}"


# ---------------------------------------------------------------------------
# get_sheets_client  -- common gspread auth
# ---------------------------------------------------------------------------

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_sheets_client():
    """Return an authorised gspread.Client using env_loader credentials.

    Credential lookup order:
      1. GOOGLE_SERVICE_ACCOUNT_PATH env var
      2. credentials/google_service_account.json (project root)

    Raises FileNotFoundError if no credential file is found.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise ImportError(
            "gspread or google-auth not installed.  "
            "Run: pip install gspread google-auth"
        )

    # Ensure env is loaded
    try:
        from env_loader import load_env
        load_env()
    except ImportError:
        pass  # env_loader not available (e.g. CI); rely on env vars already set

    # Resolve service-account JSON path
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
    if not sa_path or not os.path.exists(sa_path):
        project_root = Path(__file__).resolve().parent.parent
        sa_path = str(project_root / "credentials" / "google_service_account.json")

    if not os.path.exists(sa_path):
        raise FileNotFoundError(
            f"Service account JSON not found.  "
            f"Set GOOGLE_SERVICE_ACCOUNT_PATH or place file at {sa_path}"
        )

    creds = Credentials.from_service_account_file(sa_path, scopes=_SCOPES)
    return gspread.authorize(creds)


# ---------------------------------------------------------------------------
# quick self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Verify safe_range logic
    assert safe_range("US Posts Master", "A1:Z50") == "'US Posts Master'!A1:Z50"
    assert safe_range("SNS", "A1:Z50") == "SNS!A1:Z50"
    assert safe_range("'Already Quoted'", "B2") == "'Already Quoted'!B2"
    assert safe_range("Reference", "C3") == "Reference!C3"  # no space, no quote
    assert safe_range("US D+60 Tracker", "C3") == "'US D+60 Tracker'!C3"
    print("All safe_range tests passed.")

    # Try auth (will only work if credentials are available)
    try:
        gc = get_sheets_client()
        print(f"Sheets client OK: {type(gc)}")
    except (FileNotFoundError, ImportError) as e:
        print(f"Sheets client skipped (expected in test): {e}")
