"""
Fetch emails from/to Kiran Lee related to compliance from Outlook.

Uses win32com to access the local Outlook desktop application directly.
Searches for emails involving 'kiran' with compliance-related keywords.

Usage:
    python tools/fetch_kiran_emails.py
    python tools/fetch_kiran_emails.py --months 24
"""

import os
import sys
import json
from datetime import datetime, timedelta

if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, '.tmp', 'kiran_emails')

COMPLIANCE_KEYWORDS = [
    'compliance', 'cpsc', 'fda', 'cpsia', 'astm', 'prop 65',
    'testing', 'test report', 'certificate', 'cpc', 'gcc',
    'label', 'labeling', 'regulation', 'regulatory',
    'lead', 'phthalate', 'bpa', 'formaldehyde',
    'safety', 'recall', 'import alert',
    'fsvp', 'mocra', 'epa', 'tsca',
    'tracking label', 'small parts', 'choking',
    'amazon', 'seller central', 'listing', 'suspended',
    'inspection', 'audit', 'sgs', 'intertek', 'bureau veritas',
    'customs', 'cbp', 'hs code', 'tariff',
    'prop65', 'california',
    'registration', 'notification',
    '컴플라이언스', '인증', '시험', '테스트', '규정', '라벨',
]


def get_outlook():
    import win32com.client
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        return namespace
    except Exception as e:
        print(f"[ERROR] Cannot connect to Outlook: {e}")
        print("  Make sure Outlook is running.")
        sys.exit(1)


def search_all_folders(namespace, search_func, max_emails=1000, months=24):
    """Search through all folders recursively."""
    results = []
    cutoff = datetime.now() - timedelta(days=months * 30)

    def scan_folder(folder, depth=0):
        if len(results) >= max_emails:
            return
        try:
            items = folder.Items
            items.Sort("[ReceivedTime]", True)
            count = 0
            for item in items:
                if len(results) >= max_emails:
                    break
                try:
                    received = item.ReceivedTime
                    received_dt = datetime(received.year, received.month, received.day)
                    if received_dt < cutoff:
                        break
                    count += 1
                    data = search_func(item)
                    if data:
                        data['folder'] = folder.Name
                        results.append(data)
                except:
                    continue
            if depth < 3:
                try:
                    for sub in folder.Folders:
                        scan_folder(sub, depth + 1)
                except:
                    pass
        except:
            pass

    # Search all account folders
    for account_folder in namespace.Folders:
        try:
            for sub in account_folder.Folders:
                scan_folder(sub)
        except:
            pass

    return results


def check_kiran_email(item):
    """Check if email involves Kiran Lee and extract data."""
    try:
        sender = str(item.SenderEmailAddress or '').lower()
        sender_name = str(item.SenderName or '').lower()
        to = str(item.To or '').lower()
        cc = str(item.CC or '').lower()
        subject = str(item.Subject or '')

        # Check if Kiran is involved
        all_people = sender + ' ' + sender_name + ' ' + to + ' ' + cc
        if 'kiran' not in all_people:
            return None

        # Get body
        try:
            body = str(item.Body or '')[:5000]
        except:
            body = ''

        # Get attachments
        attachments = []
        try:
            for i in range(1, item.Attachments.Count + 1):
                att = item.Attachments.Item(i)
                attachments.append(str(att.FileName))
        except:
            pass

        # Check if compliance-related (optional, include all Kiran emails)
        full_text = (subject + ' ' + body).lower()
        is_compliance = any(kw in full_text for kw in COMPLIANCE_KEYWORDS)

        try:
            date_str = item.ReceivedTime.strftime('%Y-%m-%d %H:%M')
        except:
            date_str = ''

        return {
            'date': date_str,
            'from': f"{item.SenderName} <{item.SenderEmailAddress}>",
            'to': str(item.To or ''),
            'cc': str(item.CC or ''),
            'subject': subject,
            'body': body,
            'snippet': body[:300].replace('\r\n', ' ').replace('\n', ' '),
            'attachments': attachments,
            'is_compliance': is_compliance,
        }

    except:
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--months', type=int, default=24)
    parser.add_argument('--max', type=int, default=500)
    args = parser.parse_args()

    print("=" * 70)
    print("  Kiran Lee Email Search - Outlook (mj.lee@orbiters.co.kr)")
    print("=" * 70)

    print("\n[1] Connecting to Outlook...")
    namespace = get_outlook()
    print("    Connected!")

    print(f"\n[2] Searching all folders for Kiran Lee emails (last {args.months} months)...")
    emails = search_all_folders(namespace, check_kiran_email, args.max, args.months)

    emails.sort(key=lambda x: x.get('date', ''), reverse=True)

    compliance_emails = [e for e in emails if e.get('is_compliance')]
    other_emails = [e for e in emails if not e.get('is_compliance')]

    print(f"    Found: {len(emails)} total ({len(compliance_emails)} compliance-related)")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save all
    all_path = os.path.join(OUTPUT_DIR, 'kiran_all_emails.json')
    with open(all_path, 'w', encoding='utf-8') as f:
        json.dump(emails, f, ensure_ascii=False, indent=2)

    # Save compliance only
    comp_path = os.path.join(OUTPUT_DIR, 'kiran_compliance_emails.json')
    with open(comp_path, 'w', encoding='utf-8') as f:
        json.dump(compliance_emails, f, ensure_ascii=False, indent=2)

    # Print preview
    print(f"\n{'=' * 70}")
    print(f"  COMPLIANCE-RELATED ({len(compliance_emails)} emails):")
    print(f"{'=' * 70}")
    for e in compliance_emails[:20]:
        att = f" [{len(e['attachments'])} files]" if e['attachments'] else ""
        print(f"  {e['date']}  {e['subject'][:60]}{att}")

    if other_emails:
        print(f"\n  OTHER ({len(other_emails)} emails):")
        for e in other_emails[:10]:
            att = f" [{len(e['attachments'])} files]" if e['attachments'] else ""
            print(f"  {e['date']}  {e['subject'][:60]}{att}")

    print(f"\n  All emails:        {all_path}")
    print(f"  Compliance only:   {comp_path}")
    print()


if __name__ == '__main__':
    main()
