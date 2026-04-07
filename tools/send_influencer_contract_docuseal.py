"""
인플루언서 계약서 자동 생성 및 DocuSeal 서명 요청 도구
------------------------------------------------------
Word 템플릿의 placeholder를 채우고 DocuSeal API로 서명 요청을 생성합니다.
DocuSign 대신 자체 호스팅 DocuSeal(docuseal.orbiters.co.kr)을 사용합니다.

사전 조건:
    1. DocuSeal 템플릿 업로드 완료 (template_id=1)
    2. pip install python-docx requests python-dotenv

사용법:
    # 서명 요청 생성 (Draft — 이메일 발송)
    python tools/send_influencer_contract_docuseal.py \
        --name "Sarah Johnson" \
        --email "sarah@example.com" \
        --handle "@sarahjohnson" \
        --payment 600 \
        --deliverables "Two (2) Instagram Reels and two (2) TikTok videos" \
        --products "one (1) Grosmimi PPSU Straw cup and one (1) Grosmimi Stainless Steel Tumbler" \
        --video-count 2

    # Dry run (API 호출 없이 데이터 확인만)
    python tools/send_influencer_contract_docuseal.py \
        --name "Sarah Johnson" --email "sarah@example.com" --handle "@sarahjohnson" \
        --payment 600 --deliverables "..." --products "..." --video-count 2 \
        --dry-run

    # 서명 상태 확인
    python tools/send_influencer_contract_docuseal.py --status

    # 특정 submission 상태 확인
    python tools/send_influencer_contract_docuseal.py --check-submission 123
"""

import argparse
import json
import os
import sys
from datetime import datetime

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 환경변수 ───────────────────────────────────────────────────────────────
DOCUSEAL_BASE_URL = os.getenv("DOCUSEAL_BASE_URL", "https://docuseal.orbiters.co.kr")
DOCUSEAL_API_KEY = os.getenv("DOCUSEAL_API_KEY")
DOCUSEAL_TEMPLATE_ID = int(os.getenv("DOCUSEAL_TEMPLATE_ID", "1"))

COMPANY_NAME = os.getenv("CONTRACT_COMPANY_NAME", "Jane Jeon")
COMPANY_TITLE = os.getenv("CONTRACT_COMPANY_TITLE", "Brand manager")
PRODUCT_BRAND = os.getenv("CONTRACT_PRODUCT_BRAND", "GROSMIMI Cups")

API_HEADERS = {
    "X-Auth-Token": DOCUSEAL_API_KEY,
    "Content-Type": "application/json",
}


# ── 날짜 포맷 ──────────────────────────────────────────────────────────────
def format_date(dt: datetime) -> str:
    day = dt.day
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(
        day % 10 if day not in (11, 12, 13) else 0, "th"
    )
    return dt.strftime(f"%B {day}{suffix}, %Y")


# ── DocuSeal API 호출 ─────────────────────────────────────────────────────
def create_submission(data: dict) -> dict:
    """DocuSeal API로 서명 요청 생성"""
    today = datetime.today()
    today_str = format_date(today)

    video_count = data["video_count"]
    cadence_suffix = ""
    if video_count > 1:
        cadence_suffix = (
            f", to be produced and published at a cadence of {data['cadence']}"
        )

    whitelisting = data.get("whitelisting", "without any fixed end date")
    w9_line = "Submit a signed W-9 form" if data["payment_amount"] >= 600 else "(not required)"

    handle = data["account_handle"]
    if not handle.startswith("@"):
        handle = f"@{handle}"

    # DocuSeal submission payload
    payload = {
        "template_id": DOCUSEAL_TEMPLATE_ID,
        "send_email": True,
        "submitters": [
            {
                "name": data["influencer_name"],
                "email": data["influencer_email"],
                "role": "First Party",
                "fields": [
                    {"name": "AGREEMENT_DATE", "default_value": today_str, "readonly": True},
                    {"name": "INFLUENCER_NAME", "default_value": data["influencer_name"], "readonly": True},
                    {"name": "ACCOUNT_HANDLE", "default_value": handle, "readonly": True},
                    {"name": "DELIVERABLES_SUMMARY", "default_value": data["deliverables"], "readonly": True},
                    {"name": "PRODUCTS_LIST", "default_value": data["products"], "readonly": True},
                    {"name": "W9_LINE", "default_value": w9_line, "readonly": True},
                    {"name": "PAYMENT_AMOUNT", "default_value": f"${data['payment_amount']}", "readonly": True},
                    {"name": "VIDEO_COUNT", "default_value": str(video_count), "readonly": True},
                    {"name": "CADENCE_SUFFIX", "default_value": cadence_suffix, "readonly": True},
                    {"name": "PLATFORMS", "default_value": data.get("platforms", "Instagram Reels and/or TikTok"), "readonly": True},
                    {"name": "PRODUCT_BRAND", "default_value": PRODUCT_BRAND, "readonly": True},
                    {"name": "WHITELISTING_TERMS", "default_value": whitelisting, "readonly": True},
                    {"name": "COMPANY_NAME", "default_value": COMPANY_NAME, "readonly": True},
                    {"name": "COMPANY_TITLE", "default_value": COMPANY_TITLE, "readonly": True},
                ],
            }
        ],
        # ⚠️ CRITICAL: body must contain {{submitter.link}} or recipients get no signing link
        "message": {
            "subject": "Influencer Content Agreement - Signature Required",
            "body": (
                f"Hi {data['influencer_name']},\n\n"
                "Please review and sign the Influencer Content Agreement.\n\n"
                "Click here to sign: {{submitter.link}}\n\n"
                "Thank you!"
            ),
        },
    }

    # ── 서명 링크 누락 방지 검증 ──────────────────────────────────────────
    email_body = payload.get("message", {}).get("body", "")
    if "{{submitter.link}}" not in email_body:
        print("[FATAL] Email body missing {{submitter.link}}!")
        print("        Without this, recipients won't receive the signing link.")
        sys.exit(1)

    resp = requests.post(
        f"{DOCUSEAL_BASE_URL}/api/submissions",
        headers=API_HEADERS,
        json=payload,
    )

    if resp.status_code not in (200, 201):
        print(f"[ERROR] DocuSeal API error {resp.status_code}:")
        print(resp.text[:500])
        sys.exit(1)

    return resp.json()


def list_templates() -> list:
    """DocuSeal 템플릿 목록 조회"""
    resp = requests.get(
        f"{DOCUSEAL_BASE_URL}/api/templates",
        headers=API_HEADERS,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def get_submission(submission_id: int) -> dict:
    """특정 submission 상태 조회"""
    resp = requests.get(
        f"{DOCUSEAL_BASE_URL}/api/submissions/{submission_id}",
        headers=API_HEADERS,
    )
    resp.raise_for_status()
    return resp.json()


def list_submissions() -> list:
    """최근 submissions 목록 조회"""
    resp = requests.get(
        f"{DOCUSEAL_BASE_URL}/api/submissions",
        headers=API_HEADERS,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


# ── 메인 ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="인플루언서 계약서 DocuSeal 서명 요청")
    parser.add_argument("--name", help="인플루언서 실명")
    parser.add_argument("--email", help="인플루언서 이메일")
    parser.add_argument("--handle", help="소셜미디어 핸들 (예: @username)")
    parser.add_argument("--payment", type=int, help="지급 금액 (숫자만, USD)")
    parser.add_argument("--deliverables", help="납품물 설명")
    parser.add_argument("--products", help="제품 목록")
    parser.add_argument("--video-count", type=int, dest="video_count", help="총 영상 개수")
    parser.add_argument("--cadence",
                        default="one (1) video every three to four (3\u20134) weeks",
                        help="게시 주기 (video_count > 1일 때만 사용)")
    parser.add_argument("--platforms", default="Instagram Reels and/or TikTok")
    parser.add_argument("--whitelisting", default="without any fixed end date")
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 데이터 확인만")
    parser.add_argument("--status", action="store_true", help="최근 submissions 목록 조회")
    parser.add_argument("--check-submission", type=int, help="특정 submission 상태 확인")
    parser.add_argument("--list-templates", action="store_true", help="템플릿 목록 조회")
    args = parser.parse_args()

    if not DOCUSEAL_API_KEY:
        print("[ERROR] DOCUSEAL_API_KEY not set in .env")
        sys.exit(1)

    # ── 상태 조회 모드 ─────────────────────────────────────────────────
    if args.list_templates:
        templates = list_templates()
        print(f"Templates ({len(templates)}):")
        for t in templates:
            print(f"  [{t['id']}] {t['name']} (fields: {len(t.get('fields', []))})")
        return

    if args.status:
        subs = list_submissions()
        print(f"Recent submissions ({len(subs)}):")
        for s in subs:
            submitters = s.get("submitters", [{}])
            name = submitters[0].get("name", "?") if submitters else "?"
            email = submitters[0].get("email", "?") if submitters else "?"
            status = submitters[0].get("status", "?") if submitters else "?"
            print(f"  [{s['id']}] {name} <{email}> — {status} ({s.get('created_at', '')[:10]})")
        return

    if args.check_submission:
        sub = get_submission(args.check_submission)
        print(json.dumps(sub, indent=2, ensure_ascii=False))
        return

    # ── 서명 요청 모드 ─────────────────────────────────────────────────
    required = ["name", "email", "handle", "payment", "deliverables", "products", "video_count"]
    missing = [f for f in required if getattr(args, f) is None]
    if missing:
        print(f"[ERROR] Missing required args: {', '.join('--' + f.replace('_', '-') for f in missing)}")
        sys.exit(1)

    data = {
        "influencer_name": args.name,
        "influencer_email": args.email,
        "account_handle": args.handle,
        "payment_amount": args.payment,
        "deliverables": args.deliverables,
        "products": args.products,
        "video_count": args.video_count,
        "cadence": args.cadence,
        "platforms": args.platforms,
        "whitelisting": args.whitelisting,
    }

    handle = args.handle if args.handle.startswith("@") else f"@{args.handle}"
    w9_label = "Yes (auto, >= $600)" if args.payment >= 600 else "No (auto, < $600)"
    wl_label = ("Negotiate later (v2)" if args.whitelisting.lower() == "later"
                else f"Fixed: {args.whitelisting} (v1)")

    print("=" * 55)
    print("DocuSeal Contract Submission")
    print("=" * 55)
    print(f"Influencer : {args.name}  /  {args.email}")
    print(f"Handle     : {handle}")
    print(f"Payment    : ${args.payment} USD")
    print(f"Deliverables: {args.deliverables}")
    print(f"Videos     : {args.video_count}  (cadence: {'yes' if args.video_count > 1 else 'no'})")
    print(f"W-9        : {w9_label}")
    print(f"Whitelisting: {wl_label}")
    print(f"Template ID: {DOCUSEAL_TEMPLATE_ID}")
    print(f"DocuSeal   : {DOCUSEAL_BASE_URL}")
    print()

    if args.dry_run:
        print("[DRY RUN] No API call made. Data above is what would be sent.")
        return

    print("Sending to DocuSeal API...")
    result = create_submission(data)

    # result can be a list of submitter objects
    if isinstance(result, list):
        sub = result[0] if result else {}
        submission_id = sub.get("submission_id", sub.get("id", "?"))
        slug = sub.get("slug", "")
        status = sub.get("status", "?")
    else:
        submission_id = result.get("id", "?")
        slug = result.get("slug", "")
        status = result.get("status", "?")

    print()
    print("=" * 55)
    print("DocuSeal Submission Created")
    print("=" * 55)
    print(f"Submitter    : {args.name} ({args.email})")
    print(f"Handle       : {handle}")
    print(f"Payment      : ${args.payment} USD")
    print(f"Submission ID: {submission_id}")
    print(f"Status       : {status}")
    if slug:
        print(f"Sign URL     : {DOCUSEAL_BASE_URL}/s/{slug}")
    print()
    print("The influencer will receive an email to sign the agreement.")
    print(f"Check status: python tools/send_influencer_contract_docuseal.py --check-submission {submission_id}")

    # Output for n8n / automation parsing
    print(f"\nSUBMISSION_ID={submission_id}")
    if slug:
        print(f"SIGN_URL={DOCUSEAL_BASE_URL}/s/{slug}")


if __name__ == "__main__":
    main()
