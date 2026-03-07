"""Fetch PayPal transactions for influencer payment matching.

PayPal Transaction Search API has a 31-day window limit per request,
so we iterate in monthly chunks from Jan 2024 to current month.

Saves to .tmp/polar_data/q11_paypal_transactions.json
"""
import os, json, urllib.request, urllib.parse, base64, time
from datetime import datetime, timedelta
from env_loader import load_env

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(DIR, "..")
load_env()

CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
SECRET = os.getenv("PAYPAL_SECRET")
PAYPAL_ENV = os.getenv("PAYPAL_ENV", "live")  # "live" or "sandbox"
BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_ENV == "sandbox" else "https://api-m.paypal.com"
OUT = os.path.join(ROOT, ".tmp", "polar_data", "q11_paypal_transactions.json")


def get_access_token():
    """OAuth2 client_credentials exchange."""
    auth = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
    req = urllib.request.Request(
        f"{BASE}/v1/oauth2/token",
        data=b"grant_type=client_credentials&scope=https://uri.paypal.com/services/reporting/search/read",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise Exception(f"PayPal auth failed ({e.code}): {body[:300]}\n  URL: {BASE}/v1/oauth2/token")


def fetch_transactions_window(start_dt, end_dt, token):
    """Fetch transactions for a single date window (max 31 days)."""
    txns = []
    page = 1
    page_size = 500

    while True:
        params = urllib.parse.urlencode({
            "start_date": start_dt.strftime("%Y-%m-%dT00:00:00-0000"),
            "end_date": end_dt.strftime("%Y-%m-%dT23:59:59-0000"),
            "page_size": page_size,
            "page": page,
            "fields": "transaction_info,payer_info",
        })
        url = f"{BASE}/v1/reporting/transactions?{params}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"  API error (page {page}): {e.code} — {body[:200]}")
            break

        details = data.get("transaction_details", [])
        for d in details:
            ti = d.get("transaction_info", {})
            pi = d.get("payer_info", {})
            payer_name = pi.get("payer_name", {})
            full_name = f"{payer_name.get('given_name', '')} {payer_name.get('surname', '')}".strip()
            amount_info = ti.get("transaction_amount", {})

            txns.append({
                "transaction_id": ti.get("transaction_id", ""),
                "date": ti.get("transaction_initiation_date", ""),
                "payer_email": pi.get("email_address", ""),
                "payer_name": full_name,
                "amount": float(amount_info.get("value") or "0"),
                "currency": amount_info.get("currency_code", "USD"),
                "status": ti.get("transaction_status", ""),
                "subject": ti.get("transaction_subject", ""),
                "note": ti.get("transaction_note", ""),
                "invoice_id": ti.get("invoice_id", ""),
            })

        total_pages = data.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)

    return txns


def fetch_all_transactions(start_year=2024, start_month=1):
    """Iterate in 31-day windows from start to now."""
    token = get_access_token()
    all_txns = []

    current = datetime(start_year, start_month, 1)
    now = datetime.now()

    while current < now:
        # End = current + 30 days (31-day window inclusive)
        end = current + timedelta(days=30)
        if end > now:
            end = now

        print(f"  Fetching {current.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}...")
        txns = fetch_transactions_window(current, end, token)
        all_txns.extend(txns)
        print(f"    {len(txns)} transactions")

        current = end + timedelta(days=1)
        time.sleep(0.5)

    return all_txns


def main():
    if not CLIENT_ID or not SECRET:
        print("ERROR: PAYPAL_CLIENT_ID and PAYPAL_SECRET must be set in .env")
        return

    print("Fetching PayPal transactions...")
    txns = fetch_all_transactions()
    print(f"  Total: {len(txns)} transactions")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"transactions": txns}, f, indent=2, ensure_ascii=False)
    print(f"  Saved to {OUT}")


if __name__ == "__main__":
    main()
