"""
send_docuseal_contract.py
DocuSeal 계약서 자동 발송 도구 (JP 인플루언서용)
──────────────────────────────────────────────
계약서 PDF를 DocuSeal에 직접 업로드하고 서명 요청 이메일을 자동 발송합니다.
POST /api/submissions/pdf 엔드포인트로 템플릿 생성 없이 한 번에 처리.

사용법:
    # 무상(gifting) 계약서 발송
    python tools/send_docuseal_contract.py \
        --name "児玉愛花" \
        --email "mnk29.h@gmail.com" \
        --pdf "C:/Users/orbit/Desktop/s/인플루언서 계약서(서명 없는 ver)/児玉愛花_20260401.pdf" \
        --type gifting

    # 유상(paid) 계약서 발송
    python tools/send_docuseal_contract.py \
        --name "遠藤めぐみ" \
        --email "sunk.you@icloud.com" \
        --pdf "path/to/contract.pdf" \
        --type paid

    # Dry run (발송 없이 확인만)
    python tools/send_docuseal_contract.py \
        --name "児玉愛花" --email "mnk29.h@gmail.com" \
        --pdf "path/to/contract.pdf" --type gifting --dry-run

    # 서명 상태 확인
    python tools/send_docuseal_contract.py --status

    # 특정 submission 상태 확인
    python tools/send_docuseal_contract.py --check 13

    # 테스트 데이터 정리
    python tools/send_docuseal_contract.py --cleanup
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

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

API_HEADERS = {
    "X-Auth-Token": DOCUSEAL_API_KEY,
    "Content-Type": "application/json",
}

# ── 서명 요청 이메일 (일본어) ──────────────────────────────────────────────
# ⚠️ CRITICAL: 이메일 본문에 {{submitter.link}} 필수.
#    이게 없으면 수신자에게 서명 링크가 안 간다. 절대 제거 금지.
EMAIL_SUBJECT = "【GROSMIMI JAPAN】契約書のご署名のお願い"
EMAIL_BODY_TEMPLATE = (
    "{name}様\n\n"
    "いつもお世話になっております。\n"
    "GROSMIMI JAPANです。\n\n"
    "インフルエンサーコンテンツ契約書をお送りいたします。\n"
    "下記のリンクより内容をご確認のうえ、ご署名をお願いいたします。\n\n"
    "署名ページ: {{{{submitter.link}}}}\n\n"
    "ご不明な点がございましたら、お気軽にお問い合わせください。\n\n"
    "何卒よろしくお願いいたします。\n\n"
    "GROSMIMI JAPAN"
)

# ── 서명 필드 좌표 ────────────────────────────────────────────────────────
# DocuSeal API의 page는 1-indexed이지만 내부 처리에서 -1 되므로 +1 보정 필요
# 실제 4페이지에 배치하려면 page=5로 전송

FIELDS_GIFTING = [
    {"name": "氏名", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.170, "y": 0.426, "w": 0.200, "h": 0.022, "page": 5}]},
    {"name": "メールアドレス", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.250, "y": 0.454, "w": 0.220, "h": 0.022, "page": 5}]},
    {"name": "Instagramハンドル", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.310, "y": 0.482, "w": 0.200, "h": 0.022, "page": 5}]},
    {"name": "署名", "type": "signature", "required": True, "role": "First Party",
     "areas": [{"x": 0.170, "y": 0.511, "w": 0.200, "h": 0.025, "page": 5}]},
    {"name": "日付", "type": "date", "required": True, "role": "First Party",
     "areas": [{"x": 0.170, "y": 0.540, "w": 0.200, "h": 0.022, "page": 5}]},
]

FIELDS_PAID = [
    # 乙(インフルエンサー) 서명 영역
    {"name": "氏名", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.178, "y": 0.427, "w": 0.133, "h": 0.024, "page": 5}]},
    {"name": "メールアドレス", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.272, "y": 0.452, "w": 0.163, "h": 0.024, "page": 5}]},
    {"name": "住所", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.329, "y": 0.481, "w": 0.148, "h": 0.023, "page": 5}]},
    {"name": "署名", "type": "signature", "required": True, "role": "First Party",
     "areas": [{"x": 0.169, "y": 0.501, "w": 0.157, "h": 0.028, "page": 5}]},
    {"name": "日付", "type": "date", "required": True, "role": "First Party",
     "areas": [{"x": 0.176, "y": 0.534, "w": 0.153, "h": 0.023, "page": 5}]},
    # 振込先情報
    {"name": "金融機関名", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.233, "y": 0.631, "w": 0.110, "h": 0.020, "page": 5}]},
    {"name": "支店名", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.354, "y": 0.657, "w": 0.115, "h": 0.022, "page": 5}]},
    {"name": "口座種別", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.219, "y": 0.681, "w": 0.118, "h": 0.021, "page": 5}]},
    {"name": "口座番号", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.220, "y": 0.709, "w": 0.117, "h": 0.020, "page": 5}]},
    {"name": "口座名義", "type": "text", "required": True, "role": "First Party",
     "areas": [{"x": 0.300, "y": 0.737, "w": 0.138, "h": 0.021, "page": 5}]},
    {"name": "PayPal メール", "type": "text", "required": False, "role": "First Party",
     "areas": [{"x": 0.359, "y": 0.809, "w": 0.130, "h": 0.018, "page": 5}]},
]


# ── DocuSeal API ──────────────────────────────────────────────────────────

def create_submission_from_pdf(
    pdf_path: Path, name: str, email: str,
    collab_type: str = "gifting", send_email: bool = True,
    use_autodetect: bool = True,
    external_id: str = None,
) -> dict:
    """PDF에서 직접 서명 요청 생성 (POST /api/submissions/pdf)

    use_autodetect=True (기본): DocuSeal이 템플릿 내 `_____` 패턴을 자동 감지해서 필드 배치
    use_autodetect=False: 하드코딩된 FIELDS_PAID/GIFTING 좌표 사용 (레거시)
    """
    return _create_submission(pdf_path, name, email, send_email,
                              collab_type=collab_type,
                              use_autodetect=use_autodetect,
                              doc_type="pdf",
                              external_id=external_id)


def create_submission_from_docx(
    docx_path: Path, name: str, email: str,
    send_email: bool = True,
    external_id: str = None,
) -> dict:
    """DOCX 업로드 서명 요청 (POST /api/submissions/docx)

    DocuSeal이 DOCX → PDF 변환 시 {{...}} text tag를 자동 제거·필드로 변환.
    PDF 업로드 방식에서 tag 글자가 남는 문제를 해결.
    """
    return _create_submission(docx_path, name, email, send_email,
                              doc_type="docx",
                              external_id=external_id)


def _create_submission(doc_path, name, email, send_email, *, collab_type="gifting", use_autodetect=True, doc_type="pdf", external_id=None):
    with open(doc_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    mime = {
        "pdf":  "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }[doc_type]

    document = {
        "name": doc_path.stem,
        "file": f"data:{mime};base64,{b64}",
    }
    if doc_type == "pdf" and not use_autodetect:
        document["fields"] = FIELDS_PAID if collab_type == "paid" else FIELDS_GIFTING

    # external_id: GROSMIMI_JP 계약 식별자. ONZ Contracting WF가 필터링해 오알림 차단.
    if not external_id:
        external_id = f"GROSMIMI_JP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    payload = {
        "name": f"JP Contract - {name} ({datetime.now().strftime('%Y-%m-%d')})",
        "external_id": external_id,
        "send_email": send_email,
        "documents": [document],
        "submitters": [
            {
                "name": name,
                "email": email,
                "role": "First Party",
                "external_id": external_id,
            }
        ],
        "message": {
            "subject": EMAIL_SUBJECT,
            "body": EMAIL_BODY_TEMPLATE.format(name=name),
        },
    }

    email_body = payload.get("message", {}).get("body", "")
    if "{{submitter.link}}" not in email_body:
        print("[FATAL] 이메일 본문에 {{submitter.link}}가 없습니다!")
        sys.exit(1)

    url = f"{DOCUSEAL_BASE_URL}/api/submissions/{doc_type}"
    resp = requests.post(url, headers=API_HEADERS, json=payload)

    if resp.status_code not in (200, 201):
        print(f"[ERROR] 서명 요청 실패 ({resp.status_code}): {resp.text[:500]}")
        sys.exit(1)

    return resp.json()


def list_submissions() -> list:
    """최근 submissions 목록"""
    resp = requests.get(
        f"{DOCUSEAL_BASE_URL}/api/submissions",
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


def cleanup_test_data():
    """테스트 템플릿 + submission 정리"""
    # 템플릿 정리
    resp = requests.get(f"{DOCUSEAL_BASE_URL}/api/templates", headers=API_HEADERS)
    resp.raise_for_status()
    templates = resp.json().get("data", [])
    cleaned = 0
    for t in templates:
        name_lower = t["name"].lower()
        if "[test]" in name_lower or "test" in name_lower or "Upload Test" in t["name"]:
            requests.delete(
                f"{DOCUSEAL_BASE_URL}/api/templates/{t['id']}",
                headers=API_HEADERS,
            )
            cleaned += 1
            print(f"  템플릿 삭제: [{t['id']}] {t['name']}")

    # 테스트 submission 정리 (test 이메일)
    subs = list_submissions()
    sub_cleaned = 0
    for s in subs:
        submitters = s.get("submitters", [])
        if submitters:
            email = submitters[0].get("email", "")
            name = s.get("name", "")
            if "test" in email.lower() or (name and "[test]" in name.lower()):
                requests.delete(
                    f"{DOCUSEAL_BASE_URL}/api/submissions/{s['id']}",
                    headers=API_HEADERS,
                )
                sub_cleaned += 1
                print(f"  submission 삭제: [{s['id']}] {name}")

    print(f"\n  정리 완료: 템플릿 {cleaned}개, submission {sub_cleaned}개")


# ── 메인 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DocuSeal 계약서 자동 발송 (JP)")
    parser.add_argument("--name", help="인플루언서 실명 (例: 児玉愛花)")
    parser.add_argument("--email", help="인플루언서 이메일")
    parser.add_argument("--pdf", help="계약서 PDF 경로")
    parser.add_argument("--type", choices=["gifting", "paid"], default="gifting",
                        help="계약 유형 (gifting/paid)")
    parser.add_argument("--dry-run", action="store_true", help="발송 없이 확인만")
    parser.add_argument("--no-send", action="store_true", help="submission은 생성하되 이메일은 발송하지 않음 (서명 URL만 반환)")
    parser.add_argument("--resend", type=int, metavar="SUBMITTER_ID", help="기존 submitter에게 이메일 재발송")
    parser.add_argument("--status", action="store_true", help="최근 서명 요청 목록")
    parser.add_argument("--check", type=int, help="특정 submission ID 상태 확인")
    parser.add_argument("--cleanup", action="store_true", help="테스트 데이터 정리")
    args = parser.parse_args()

    if not DOCUSEAL_API_KEY:
        print("[ERROR] DOCUSEAL_API_KEY가 .env에 설정되지 않았습니다.")
        sys.exit(1)

    # ── 상태 조회 ──────────────────────────────────────────────────────
    if args.status:
        subs = list_submissions()
        print(f"\n최근 서명 요청 ({len(subs)}건):")
        print("-" * 70)
        for s in subs:
            submitters = s.get("submitters", [{}])
            sub = submitters[0] if submitters else {}
            name = sub.get("name", "?")
            email = sub.get("email", "?")
            status = sub.get("status", "?")
            created = s.get("created_at", "")[:10]
            completed = sub.get("completed_at", "")
            completed_str = completed[:10] if completed else "-"

            status_icon = {
                "completed": "✅",
                "awaiting": "⏳",
                "opened": "📂",
                "sent": "📧",
                "declined": "❌",
            }.get(status, "❓")

            print(f"  [{s['id']:>3}] {status_icon} {status:<10} | {name} <{email}> | 생성: {created} | 완료: {completed_str}")
        return

    if args.check:
        sub = get_submission(args.check)
        print(json.dumps(sub, indent=2, ensure_ascii=False))
        return

    if args.cleanup:
        cleanup_test_data()
        return

    # ── 재발송 모드 ────────────────────────────────────────────────────
    if args.resend:
        url = f"{DOCUSEAL_BASE_URL}/api/submitters/{args.resend}"
        resp = requests.put(url, headers=API_HEADERS, json={"send_email": True})
        resp.raise_for_status()
        print(f"[OK] submitter {args.resend} 이메일 재발송 요청 완료")
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        return

    # ── 발송 모드 ──────────────────────────────────────────────────────
    if not all([args.name, args.email, args.pdf]):
        print("[ERROR] --name, --email, --pdf 모두 필요합니다.")
        print("  예: python tools/send_docuseal_contract.py \\")
        print("      --name '児玉愛花' --email 'email@example.com' \\")
        print("      --pdf 'path/to/contract.docx' --type gifting")
        print("  (PDF 대신 DOCX 경로 권장 — text tag 자동 제거됨)")
        sys.exit(1)

    doc_path = Path(args.pdf)
    if not doc_path.exists():
        print(f"[ERROR] 파일 없음: {doc_path}")
        sys.exit(1)

    is_docx = doc_path.suffix.lower() == ".docx"
    collab_type = args.type

    print()
    print("=" * 60)
    print("DocuSeal 계약서 발송")
    print("=" * 60)
    print(f"  인플루언서 : {args.name}")
    print(f"  이메일     : {args.email}")
    print(f"  파일       : {doc_path}")
    print(f"  파일 크기  : {doc_path.stat().st_size / 1024:.1f} KB")
    print(f"  계약 유형  : {collab_type} ({'유상' if collab_type == 'paid' else '무상'})")
    print(f"  업로드     : {'DOCX (text tag 자동 제거)' if is_docx else 'PDF (legacy)'}")
    print(f"  DocuSeal   : {DOCUSEAL_BASE_URL}")
    print()

    if args.dry_run:
        print("[DRY RUN] 여기까지 확인. 실제 발송은 --dry-run 제거 후 실행.")
        return

    send_email_flag = not args.no_send
    if args.no_send:
        print("[NO-SEND] submission만 생성. 이메일 발송 X. 서명 URL은 반환됩니다.")
    else:
        print("서명 요청 생성 + 이메일 발송 중...")

    # DOCX / PDF 분기
    if is_docx:
        result = create_submission_from_docx(doc_path, args.name, args.email, send_email=send_email_flag)
    else:
        result = create_submission_from_pdf(
            doc_path, args.name, args.email,
            collab_type=collab_type, send_email=send_email_flag,
        )

    # 결과 파싱
    if isinstance(result, dict):
        submission_id = result.get("id", "?")
        submitters = result.get("submitters", [])
        sub = submitters[0] if submitters else {}
        slug = sub.get("slug", "")
        status = sub.get("status", result.get("status", "?"))
    else:
        sub = result[0] if result else {}
        submission_id = sub.get("submission_id", sub.get("id", "?"))
        slug = sub.get("slug", "")
        status = sub.get("status", "?")

    sign_url = f"{DOCUSEAL_BASE_URL}/s/{slug}" if slug else None

    print()
    print("=" * 60)
    print("발송 완료")
    print("=" * 60)
    print(f"  Submission ID : {submission_id}")
    print(f"  상태          : {status}")
    if sign_url:
        print(f"  서명 URL      : {sign_url}")
    print(f"  이메일 발송   : {args.email}")
    print()
    print(f"  상태 확인: python tools/send_docuseal_contract.py --check {submission_id}")
    print(f"  전체 목록: python tools/send_docuseal_contract.py --status")
    print("=" * 60)

    # 결과 JSON 저장
    result_path = Path(".tmp/docuseal_submissions")
    result_path.mkdir(parents=True, exist_ok=True)
    result_file = result_path / f"submission_{submission_id}.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({
            "submission_id": submission_id,
            "name": args.name,
            "email": args.email,
            "pdf": str(doc_path),
            "collab_type": collab_type,
            "sign_url": sign_url,
            "status": status,
            "created_at": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  기록 저장: {result_file}")


if __name__ == "__main__":
    main()
