"""
Twitter slot upload reminder for @grosmimi_jp.
Sends a minimal Teams notification at each slot time (JST 10/11/13/17/19).
"""
import os
import sys
import argparse
from pathlib import Path
import requests

# .env load is optional: GitHub Actions injects secrets as env vars directly
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

WEBHOOK = os.getenv("TEAMS_WEBHOOK_URL_SEEUN")

VALID_SLOTS = [10, 11, 13, 17, 19]
EXCEL_LINK = "https://orbiters.sharepoint.com/:x:/s/Operation/IQCRaI8st-ypRJTkXEen8iMWAS-2BG8eGBK9OZ_Ydv5jTGY"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", type=int, required=True, choices=VALID_SLOTS)
    args = ap.parse_args()

    if not WEBHOOK:
        print("[ERR] TEAMS_WEBHOOK_URL_SEEUN not set")
        sys.exit(1)

    msg = (
        f"🐻 세은님, {args.slot}:00 트위터 업로드할 시간이에요!\n"
        f"📄 [週間プラン]({EXCEL_LINK})"
    )

    r = requests.post(WEBHOOK, json={"text": msg}, timeout=20)
    r.raise_for_status()
    print(f"[OK] Slot {args.slot} notification sent")


if __name__ == "__main__":
    main()
