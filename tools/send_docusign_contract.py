"""
send_docusign_contract.py
계약서 DOCX → DocuSign 업로드 (Draft Envelope 생성)

업로드만 하고 발송은 하지 않음.
세은씨가 DocuSign에서 직접 확인 후 발송.

사용법:
    python tools/send_docusign_contract.py --handle @sakura_life
    python tools/send_docusign_contract.py --contract "Data Storage/contracts/influencer/contract_record.json"
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 환경변수 ─────────────────────────────────────────────
INTEGRATION_KEY = os.getenv("DOCUSIGN_INTEGRATION_KEY")
SECRET_KEY      = os.getenv("DOCUSIGN_SECRET_KEY")
ACCOUNT_ID      = os.getenv("DOCUSIGN_ACCOUNT_ID")
BASE_URL        = os.getenv("DOCUSIGN_BASE_URL", "https://demo.docusign.net/restapi")
REDIRECT_URI    = os.getenv("DOCUSIGN_REDIRECT_URI", "http://localhost:8080")
TOKEN_PATH      = os.getenv("DOCUSIGN_TOKEN_PATH", "credentials/docusign_token.json")

AUTH_SERVER = "https://account-d.docusign.com" if "demo" in BASE_URL else "https://account.docusign.com"


def load_token() -> dict:
    path = Path(TOKEN_PATH)
    if not path.exists():
        print(f"[ERROR] 토큰 파일 없음: {TOKEN_PATH}")
        print("  먼저 인증을 완료하세요: python tools/docusign_auth_setup.py")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def refresh_token(token_data: dict) -> str:
    """refresh_token으로 새 access_token 발급"""
    creds = base64.b64encode(f"{INTEGRATION_KEY}:{SECRET_KEY}".encode()).decode()
    resp = requests.post(
        f"{AUTH_SERVER}/oauth/token",
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
        },
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[ERROR] 토큰 갱신 실패: {resp.text}")
        sys.exit(1)

    new_token = resp.json()
    # 저장
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(new_token, f, indent=2)
    print("  토큰 갱신 완료")
    return new_token["access_token"]


def get_access_token() -> str:
    token_data = load_token()
    # 갱신 시도 (만료 여부 상관없이 refresh로 최신 토큰 확보)
    return refresh_token(token_data)


def find_record_by_handle(handle: str) -> Path:
    handle_clean = handle.lstrip("@")
    base = Path("Data Storage/contracts/influencer")
    record_path = base / f"contract_{handle_clean}_record.json"
    if not record_path.exists():
        print(f"[ERROR] 계약 기록 없음: {record_path}")
        print("  먼저 계약서를 생성하세요: python tools/generate_influencer_contract.py")
        sys.exit(1)
    return record_path


def load_record(record_path: Path) -> dict:
    with open(record_path, encoding="utf-8") as f:
        return json.load(f)


def find_docx(record: dict) -> Path:
    for f in record.get("files", []):
        if f.endswith(".docx"):
            p = Path(f)
            if p.exists():
                return p
    print("[ERROR] DOCX 파일을 찾을 수 없습니다.")
    print(f"  기록된 파일: {record.get('files')}")
    sys.exit(1)


def convert_to_pdf(docx_path: Path) -> Path:
    """DOCX → PDF 변환 (DocuSign은 DOCX 미지원)"""
    pdf_path = docx_path.with_suffix(".pdf")
    if pdf_path.exists():
        print(f"  PDF 이미 존재: {pdf_path.name}")
        return pdf_path
    try:
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
        print(f"  PDF 변환 완료: {pdf_path.name}")
        return pdf_path
    except ImportError:
        print("[ERROR] docx2pdf 없음. 설치: pip install docx2pdf")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] PDF 변환 실패: {e}")
        sys.exit(1)


def encode_file(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def create_draft_envelope(access_token: str, record: dict, pdf_path: Path) -> dict:
    """DocuSign에 Draft Envelope 생성 (발송 안 함)"""

    influencer = record["influencer"]
    contract_id = record["contract_id"]
    collab_type = record["collab_type"]

    doc_name = pdf_path.name
    doc_b64 = encode_file(pdf_path)

    # 서명자: 乙(인플루언서)만
    # 甲(회사) 서명란은 계약서 생성 시 텍스트로 미리 채워짐
    # 두 번째 "署名：" = 乙 서명란
    valid_signers = []
    if influencer.get("email"):
        valid_signers = [
            {
                "email": influencer["email"],
                "name": influencer.get("name", ""),
                "recipientId": "1",
                "routingOrder": "1",
                "tabs": {
                    "signHereTabs": [
                        {
                            "anchorString": "署名：",
                            "anchorUnits": "pixels",
                            "anchorXOffset": "60",
                            "anchorYOffset": "-5",
                            "anchorIgnoreIfNotPresent": "false",
                            "anchorOccurrence": "2",  # 두 번째 署名：= 乙(인플루언서)
                        }
                    ]
                },
            }
        ]

    envelope_def = {
        "emailSubject": f"[GROSMIMI] 인플루언서 협업 계약서 서명 요청 — {influencer['name']} ({contract_id})",
        "documents": [
            {
                "documentBase64": doc_b64,
                "name": doc_name,
                "fileExtension": "pdf",
                "documentId": "1",
            }
        ],
        "recipients": {
            "signers": valid_signers,
        },
        "status": "created",  # draft (발송 안 함)
    }

    url = f"{BASE_URL}/v2.1/accounts/{ACCOUNT_ID}/envelopes"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=envelope_def,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        print(f"[ERROR] Envelope 생성 실패 ({resp.status_code}): {resp.text}")
        sys.exit(1)

    return resp.json()


def update_record(record_path: Path, record: dict, envelope_id: str, docusign_url: str):
    record["docusign_envelope_id"] = envelope_id
    record["docusign_url"] = docusign_url
    record["docusign_uploaded_at"] = datetime.now().isoformat()
    record["status"] = "uploaded"
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def get_docusign_web_url(envelope_id: str) -> str:
    """DocuSign 웹에서 Envelope 바로 열리는 URL"""
    if "demo" in BASE_URL:
        return f"https://appdemo.docusign.com/documents/details/{envelope_id}"
    return f"https://app.docusign.com/documents/details/{envelope_id}"


def main():
    parser = argparse.ArgumentParser(description="계약서 DOCX → DocuSign 업로드")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--handle", help="인스타 핸들 (예: @sakura_life)")
    group.add_argument("--contract", help="계약 record.json 경로")
    args = parser.parse_args()

    print("\n[DocuSign 업로드]")

    # 1. 계약 기록 로드
    if args.handle:
        record_path = find_record_by_handle(args.handle)
    else:
        record_path = Path(args.contract)
        if not record_path.exists():
            print(f"[ERROR] 파일 없음: {record_path}")
            sys.exit(1)

    record = load_record(record_path)
    influencer = record["influencer"]
    print(f"  대상: {influencer['name']} ({influencer['handle']})")
    print(f"  계약 ID: {record['contract_id']}")

    # 2. DOCX 파일 찾기 → PDF 변환
    docx_path = find_docx(record)
    print(f"  파일: {docx_path.name}")
    print("  PDF 변환 중...")
    pdf_path = convert_to_pdf(docx_path)

    # 3. 토큰 가져오기
    print("\n  DocuSign 인증 중...")
    access_token = get_access_token()

    # 4. Draft Envelope 생성
    print("  Envelope 생성 중...")
    result = create_draft_envelope(access_token, record, pdf_path)

    envelope_id = result["envelopeId"]
    web_url = get_docusign_web_url(envelope_id)

    # 5. 기록 업데이트
    update_record(record_path, record, envelope_id, web_url)

    # 6. 결과 출력
    print("\n" + "=" * 60)
    print("DocuSign 업로드 완료")
    print("=" * 60)
    print(f"  Envelope ID : {envelope_id}")
    print(f"  상태        : Draft (미발송)")
    print(f"\n  DocuSign에서 확인 및 발송:")
    print(f"  {web_url}")
    print("\n  발송 전 체크리스트:")
    print("  [ ] 계약서 내용 최종 확인")
    print("  [ ] 인플루언서 이메일 주소 확인")
    print("  [ ] 서명란 위치 확인")
    print("=" * 60)


if __name__ == "__main__":
    main()
