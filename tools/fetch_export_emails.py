"""
Fetch export-related emails from Outlook (mj.lee@orbiters.co.kr).

Uses win32com to access the local Outlook desktop application directly.
Searches for CIPL, invoice, packing list, 발주, 선적, 수출 related emails.

Usage:
    python tools/fetch_export_emails.py
    python tools/fetch_export_emails.py --months 6
    python tools/fetch_export_emails.py --folder "받은 편지함"
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta

# Ensure UTF-8 output on Windows
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, '.tmp', 'export_emails')

# Export-related keywords for filtering
EXPORT_KEYWORDS = [
    'cipl', 'ci/pl', 'ci pl', 'commercial invoice', 'packing list',
    '발주', '선적', '수출', '팩킹', '통관', '카톤', '파렛트',
    'shipment', 'shipping', 'invoice', 'booking',
    'bl', 'b/l', 'bill of lading', 'awb',
    'customs', 'clearance',
    'payment', 't/t', 'remittance', '송금', '결제',
    'packing', 'pallet', 'carton',
    'quotation', 'quote', '견적', '단가',
    'grosmimi', 'littlefinger', 'fleeters', 'orbiters',
    'naeiae', 'commemoi', 'alpremio', 'babyrabbit', 'bamboo',
    'walk by faith', 'cgetc', 'shipbob',
    'exw', 'fob', 'cif',
    'etd', 'eta',
]


def get_outlook():
    """Connect to local Outlook application via COM."""
    import win32com.client
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        return namespace
    except Exception as e:
        print(f"[ERROR] Outlook에 연결할 수 없습니다: {e}")
        print("  Outlook 앱이 실행 중인지 확인해 주세요.")
        sys.exit(1)


def get_inbox(namespace, folder_name=None):
    """Get the inbox folder (or specified folder)."""
    # 6 = olFolderInbox
    inbox = namespace.GetDefaultFolder(6)

    if folder_name:
        # Try to find subfolder
        try:
            for folder in inbox.Folders:
                if folder.Name == folder_name:
                    return folder
        except:
            pass
        # Try top-level folders
        try:
            for folder in namespace.Folders:
                if folder.Name == folder_name:
                    return folder
                for sub in folder.Folders:
                    if sub.Name == folder_name:
                        return sub
        except:
            pass
        print(f"  WARN: Folder '{folder_name}' not found, using Inbox")

    return inbox


def list_folders(namespace):
    """List all available mail folders."""
    folders = []
    try:
        for account_folder in namespace.Folders:
            folders.append(account_folder.Name)
            try:
                for sub in account_folder.Folders:
                    folders.append(f"  └─ {sub.Name} ({sub.Items.Count})")
                    try:
                        for sub2 in sub.Folders:
                            folders.append(f"      └─ {sub2.Name} ({sub2.Items.Count})")
                    except:
                        pass
            except:
                pass
    except:
        pass
    return folders


def is_export_related(subject, body_preview):
    """Check if email is export-related based on keywords."""
    text = (subject + ' ' + body_preview).lower()
    return any(kw in text for kw in EXPORT_KEYWORDS)


def classify_email(subject, body_preview):
    """Classify export email by type."""
    text = (subject + ' ' + body_preview).lower()

    categories = []
    if any(kw in text for kw in ['cipl', 'ci/pl', 'ci pl', 'commercial invoice', 'packing list']):
        categories.append('CIPL')
    if any(kw in text for kw in ['발주', 'order', 'purchase order', 'po ', 'p/o']):
        categories.append('ORDER')
    if any(kw in text for kw in ['선적', 'shipment', 'shipping', 'booking', 'etd', 'eta']):
        categories.append('SHIPMENT')
    if any(kw in text for kw in ['bl', 'b/l', 'bill of lading', 'awb', 'airway']):
        categories.append('BL')
    if any(kw in text for kw in ['통관', 'customs', 'clearance', 'hscode', 'hs code']):
        categories.append('CUSTOMS')
    if any(kw in text for kw in ['결제', 'payment', 't/t', 'remittance', 'wire', '송금']):
        categories.append('PAYMENT')
    if any(kw in text for kw in ['팩킹', 'packing', 'pallet', '파렛트', '카톤', 'carton']):
        categories.append('PACKING')
    if any(kw in text for kw in ['견적', 'quotation', 'quote', 'price', '단가']):
        categories.append('PRICING')

    if not categories:
        categories.append('OTHER')

    return categories


def extract_email_data(mail_item):
    """Extract data from an Outlook MailItem."""
    try:
        subject = str(mail_item.Subject or '')
    except:
        subject = ''

    try:
        body = str(mail_item.Body or '')[:3000]
    except:
        body = ''

    try:
        sender = str(mail_item.SenderEmailAddress or '')
        sender_name = str(mail_item.SenderName or '')
    except:
        sender = ''
        sender_name = ''

    try:
        to = str(mail_item.To or '')
    except:
        to = ''

    try:
        cc = str(mail_item.CC or '')
    except:
        cc = ''

    try:
        received = mail_item.ReceivedTime
        date_str = received.strftime('%Y-%m-%d %H:%M')
    except:
        date_str = ''

    # Extract attachments
    attachments = []
    try:
        for i in range(1, mail_item.Attachments.Count + 1):
            att = mail_item.Attachments.Item(i)
            attachments.append(str(att.FileName))
    except:
        pass

    return {
        'date': date_str,
        'from': f"{sender_name} <{sender}>" if sender_name else sender,
        'from_email': sender,
        'from_name': sender_name,
        'to': to,
        'cc': cc,
        'subject': subject,
        'body': body,
        'snippet': body[:200].replace('\r\n', ' ').replace('\n', ' '),
        'attachments': attachments,
        'categories': classify_email(subject, body[:500]),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fetch export-related emails from Outlook')
    parser.add_argument('--months', type=int, default=12, help='How many months back to search (default: 12)')
    parser.add_argument('--folder', type=str, default=None, help='Specific folder name to search')
    parser.add_argument('--list-folders', action='store_true', help='List all available folders and exit')
    parser.add_argument('--max', type=int, default=500, help='Max emails to process (default: 500)')
    parser.add_argument('--all-emails', action='store_true', help='Fetch ALL emails, not just export-related')
    args = parser.parse_args()

    print("=" * 70)
    print("  Export Email Fetcher - Outlook (mj.lee@orbiters.co.kr)")
    print("=" * 70)

    # Step 1: Connect to Outlook
    print("\n[1] Connecting to Outlook...")
    namespace = get_outlook()
    print("    Connected!")

    # List folders if requested
    if args.list_folders:
        print("\n  Available folders:")
        for f in list_folders(namespace):
            print(f"    {f}")
        return

    # Step 2: Get inbox
    print(f"\n[2] Accessing mail folder...")
    inbox = get_inbox(namespace, args.folder)
    print(f"    Folder: {inbox.Name} ({inbox.Items.Count} items)")

    # Step 3: Filter by date
    cutoff_date = datetime.now() - timedelta(days=args.months * 30)
    print(f"    Date range: {cutoff_date.strftime('%Y-%m-%d')} ~ now")

    # Sort by received date descending
    items = inbox.Items
    items.Sort("[ReceivedTime]", True)

    # Step 4: Scan emails
    print(f"\n[3] Scanning emails for export-related content...")
    emails = []
    scanned = 0
    skipped = 0

    for item in items:
        if scanned >= args.max:
            break

        try:
            # Check date
            received = item.ReceivedTime
            received_dt = datetime(received.year, received.month, received.day,
                                   received.hour, received.minute)
            if received_dt < cutoff_date:
                break  # Items are sorted descending, so we can stop

            scanned += 1

            if scanned % 50 == 0:
                print(f"    Scanned {scanned} emails, found {len(emails)} export-related...")

            # Check if export-related
            subject = str(item.Subject or '')
            try:
                body_preview = str(item.Body or '')[:500]
            except:
                body_preview = ''

            if not args.all_emails and not is_export_related(subject, body_preview):
                skipped += 1
                continue

            # Extract full data
            data = extract_email_data(item)
            emails.append(data)

        except Exception as e:
            # Some items might not be mail items (meetings, etc.)
            continue

    print(f"    Scanned: {scanned} | Export-related: {len(emails)} | Skipped: {skipped}")

    if not emails:
        print("\n    No export-related emails found.")
        return

    # Sort by date descending
    emails.sort(key=lambda x: x.get('date', ''), reverse=True)

    # Step 5: Save results
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save full JSON
    json_path = os.path.join(OUTPUT_DIR, 'export_emails.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(emails, f, ensure_ascii=False, indent=2)

    # Save summary (without full body)
    summary = []
    for e in emails:
        summary.append({
            'date': e['date'],
            'from': e['from'],
            'to': e['to'],
            'subject': e['subject'],
            'categories': e['categories'],
            'attachments': e['attachments'],
            'snippet': e['snippet'],
        })

    summary_path = os.path.join(OUTPUT_DIR, 'export_emails_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Print results
    print(f"\n{'=' * 70}")
    print(f"  DONE! {len(emails)} export-related emails found")
    print(f"{'=' * 70}")

    # Category breakdown
    cat_counts = {}
    for e in emails:
        for c in e['categories']:
            cat_counts[c] = cat_counts.get(c, 0) + 1

    print(f"\n  Category breakdown:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat:12s}: {count}")

    # Top senders
    sender_counts = {}
    for e in emails:
        sender = e.get('from_email', e['from'])
        sender_counts[sender] = sender_counts.get(sender, 0) + 1

    print(f"\n  Top senders/receivers:")
    for sender, count in sorted(sender_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"    {sender:45s}: {count}")

    # Recent emails preview
    print(f"\n  Recent 15 emails:")
    for e in emails[:15]:
        cats = ','.join(e['categories'])
        att = f" [{len(e['attachments'])} files]" if e['attachments'] else ""
        print(f"    {e['date']}  [{cats:12s}] {e['subject'][:55]}{att}")

    print(f"\n  Full data:    {json_path}")
    print(f"  Summary:      {summary_path}")
    print()


if __name__ == '__main__':
    main()
