"""
generate_influencer_contract.py
인플루언서 협업 계약서 생성기

템플릿 2계층 (이 도구는 orbit PC 로컬 전용 — 경로 하드코딩은 의도):
  1) 세은 관리 원본 (불변): s\\contents\\instagram\\인플루언서 계약서(서명 無 ver)\\new*.docx
  2) 생성용 앵커 사본 (코드가 읽는 것): s\\참고자료\\인플루언서 컨택\\형식\\new*_anchored.docx
     — {{VAR}} + DocuSeal 필드 태그 삽입본. 원본 개정 시 .tmp/make_anchored_templates.py 로 재생성.

사용법:
  python tools/generate_influencer_contract.py --manual '{"collab_type":"gifting","influencer_name":"田中さくら","influencer_handle":"@sakura_life","influencer_email":"sakura@email.com","product_name":"PPSUストローマグ","product_type":"ppsu_straw","color_size":"クリームベージュ/300ml","quantity":1,"video_count":1,"platforms":"Instagram Reels"}'
"""

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass  # 리다이렉트 등 reconfigure 불가 환경에서는 그대로 진행

try:
    from dotenv import load_dotenv
    load_dotenv()  # CONTRACT_SIGNER_NAME_JP / CONTRACT_TEMPLATE_DIR / CONTRACT_OUTPUT_DIR
except ImportError:
    pass  # dotenv 없으면 OS 환경변수만 사용


# 원본 DOCX 템플릿 경로
# 2026-07-31 스위치: 세은 신규 양식(new*, s\contents\instagram\인플루언서 계약서(서명 無 ver)) 기반.
#   세은 원본은 불변 — _anchored 사본({{VAR}} + DocuSeal 필드 태그)을 사용.
#   앵커: AGREEMENT_DATE / ACCOUNT_HANDLE / INFLUENCER_NAME / COMPANY_NAME / VIDEO_COUNT /
#         PLATFORMS(계약별 합의 플랫폼, 단일 원칙) / PRODUCT_NAME / QUANTITY / COLOR_SIZE /
#         HASHTAGS(제품별, PPSU는 +#PPSU) / PAYMENT_AMOUNT(유상)
# 다른 PC(핸드오버 패키지)에서는 .env CONTRACT_TEMPLATE_DIR 로 템플릿 폴더 지정
TEMPLATE_DIR = Path(os.getenv("CONTRACT_TEMPLATE_DIR",
                              r"C:\Users\orbit\Desktop\s\참고자료\인플루언서 컨택\형식"))
TEMPLATE_PAID    = TEMPLATE_DIR / "newインフルエンサーコンテンツ契約書（有償）_anchored.docx"
TEMPLATE_GIFTING = TEMPLATE_DIR / "newインフルエンサーコンテンツ契約書（無償）_anchored.docx"
DEFAULT_OUTPUT_DIR = os.getenv("CONTRACT_OUTPUT_DIR",
                               r"C:\Users\orbit\Desktop\s\contents\instagram\인플루언서 계약서(서명 無 ver)")


def check_deps():
    try:
        import docx  # noqa
    except ImportError:
        print("[ERROR] python-docx 없음. 설치: pip install python-docx")
        sys.exit(1)


def load_negotiation(handle: str) -> dict:
    handle_clean = handle.lstrip("@")
    path = Path(".tmp/influencer_negotiations") / f"{handle_clean}.json"
    if not path.exists():
        print(f"[ERROR] 협상 데이터 없음: {path}")
        print("  --manual 옵션으로 직접 입력하거나 협상 기록을 먼저 저장하세요.")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_manual(json_str: str) -> dict:
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 파싱 실패: {e}")
        sys.exit(1)


def validate_fields(data: dict) -> dict:
    """필수 필드 검증 + 기본값"""
    collab_type = data.get("collab_type", "").lower()
    if collab_type not in ("paid", "gifting"):
        print(f"[ERROR] collab_type은 'paid' 또는 'gifting'이어야 합니다. 현재: '{collab_type}'")
        sys.exit(1)

    # 2026-07-31 신규 양식: 【提供商品】 블록이 계약서 본문에 들어감 → 제품 정보 필수
    # product_type은 해시태그 분기용 (세은 7/31 확정: PPSU 제품은 계약서에도 #PPSU 기재)
    # platforms: 투고 플랫폼 단일 기재가 원칙 (세은 7/31: 3종 병기 X, 복수 운영 계약일 때만 병기)
    required_common = ["influencer_name", "influencer_handle", "product_name", "color_size", "product_type", "platforms"]
    required_paid = ["compensation_amount"]

    missing = [f for f in required_common if not data.get(f)]
    if collab_type == "paid":
        missing += [f for f in required_paid if not data.get(f)]

    if missing:
        print(f"[ERROR] 필수 필드 누락: {', '.join(missing)}")
        print(f"  - product_name 예: 'ステンレスストローマグ'")
        print(f"  - color_size 예: 'チェリーピーチ/300ml'")
        print(f"  - product_type: 'ppsu_straw' / 'ppsu_onetouch' / 'stainless' 중 하나")
        print(f"  - platforms 예: 'Instagram Reels' (단일 원칙. 복수 운영 계약만 'Instagram Reels・TikTok')")
        sys.exit(1)

    valid_product_types = ("ppsu_straw", "ppsu_onetouch", "stainless", "straw_set")
    if data["product_type"] not in valid_product_types:
        print(f"[ERROR] product_type 값 오류: '{data.get('product_type')}'")
        print(f"  → 허용값: {', '.join(valid_product_types)}")
        sys.exit(1)

    # ── 제품-색상-용량 정합 하드게이트 (2026-07-31 세은 확정 마스터. 라쿠텐 실측) ──
    # 존재하지 않는 제품·색상 조합으로 계약서가 생성되는 사고 방지. 신컬러 입고 시 이 표만 갱신.
    PRODUCT_MASTER = {
        "ppsu_straw": {
            "name_must": "PPSU", "name_must_not": "ワンタッチ",
            "colors": ["スカイブルー", "ピーチ", "バター", "ホワイト",
                       "クリームベージュ", "ピンク", "アクアグリーン", "チャコール"],
            "capacities": ["200ml", "300ml"],
        },
        "ppsu_onetouch": {
            "name_must": "ワンタッチ", "name_must_not": None,
            "colors": ["ユニコーン", "恐竜"],
            "capacities": ["300ml"],
        },
        "stainless": {
            "name_must": "ステンレス", "name_must_not": None,
            "colors": ["チェリーピーチ", "オリーブピスタチオ", "ベアバター"],
            "capacities": ["200ml", "300ml"],
        },
        # 액세서리(교체용 스트로/니플 세트 등): 머그 색상/용량 마스터 미적용 (2026-10-05 村田 재협업 替えのストローセット)
        "straw_set": {
            "name_must": None, "name_must_not": None,
            "colors": [], "capacities": [],
        },
    }
    master = PRODUCT_MASTER[data["product_type"]]

    # straw_set(액세서리)은 머그 색상/용량 정합 게이트 미적용 — 아래 검증 스킵
    if data["product_type"] != "straw_set":
        # 제품명 ↔ product_type 일치
        pname = data["product_name"]
        if master["name_must"] not in pname or (master["name_must_not"] and master["name_must_not"] in pname):
            print(f"[ERROR] product_name '{pname}' 이(가) product_type '{data['product_type']}' 과 불일치")
            sys.exit(1)

        # color_size "색상/용량" 파싱 후 마스터 대조
        cs = data["color_size"]
        color_part, _, cap_part = cs.partition("/")
        color_part, cap_part = color_part.strip(), cap_part.strip()
        if not cap_part:
            print(f"[ERROR] color_size 형식 오류: '{cs}' → '색상/용량' 형식 (예: 'チェリーピーチ/300ml')")
            sys.exit(1)
        if color_part not in master["colors"]:
            print(f"[ERROR] '{pname}' 에 없는 색상: '{color_part}'")
            print(f"  → 이 제품 색상: {', '.join(master['colors'])}")
            sys.exit(1)
        if cap_part not in master["capacities"]:
            print(f"[ERROR] '{pname}' 에 없는 용량: '{cap_part}'")
            print(f"  → 이 제품 용량: {', '.join(master['capacities'])}")
            sys.exit(1)

    # video_count / quantity 정수 검증 (1 이상)
    for int_field in ("video_count", "quantity"):
        val = data.get(int_field, 1)
        try:
            data[int_field] = int(val)
        except (ValueError, TypeError):
            print(f"[ERROR] {int_field}은(는) 정수여야 합니다. 현재: '{val}'")
            sys.exit(1)
        if data[int_field] < 1:
            print(f"[ERROR] {int_field}은(는) 1 이상이어야 합니다. 현재: {data[int_field]}")
            sys.exit(1)

    today = date.today()
    data.setdefault("contract_date", today.strftime("%Y年%m月%d日"))
    data.setdefault("products_description", "")
    data.setdefault("compensation_currency", "JPY")
    # 신규 양식 第3条: 광고 배신 목적 이용 最大180日間
    data.setdefault("whitelisting_days", 180)
    data.setdefault("contract_id", f"IC-{today.strftime('%Y%m')}-{str(uuid.uuid4())[:6].upper()}")

    # handle에서 @ 제거
    data["influencer_handle"] = data["influencer_handle"].lstrip("@")

    return data


def replace_text_in_paragraph(para, old: str, new: str, bold_segment: str = None):
    """
    단락 내 텍스트 치환. runs에 걸쳐 분리된 경우도 처리.
    서식(볼드, 폰트 등)은 첫 번째 run 기준 유지.
    치환 후 빨간색 폰트는 검정으로 리셋.
    bold_segment가 주어지면 해당 부분만 볼드 run으로 분리.
    """
    from docx.shared import RGBColor
    full_text = para.text
    if old not in full_text:
        return

    new_full = full_text.replace(old, new)

    if para.runs:
        # 첫 run의 서식 정보 보존
        base_run = para.runs[0]
        base_font = base_run.font

        # 모든 run 텍스트 비움 (첫 run 포함)
        for run in para.runs:
            run.text = ""

        if bold_segment and bold_segment in new_full:
            # bold_segment 기준으로 분리: before + bold + after
            idx = new_full.index(bold_segment)
            before = new_full[:idx]
            after = new_full[idx + len(bold_segment):]

            base_run.text = before
            base_run.font.color.rgb = RGBColor(0, 0, 0)

            # 볼드 run 추가
            bold_run = para.add_run(bold_segment)
            bold_run.bold = True
            bold_run.font.color.rgb = RGBColor(0, 0, 0)
            if base_font.name:
                bold_run.font.name = base_font.name
            if base_font.size:
                bold_run.font.size = base_font.size

            # after run 추가
            if after:
                after_run = para.add_run(after)
                after_run.font.color.rgb = RGBColor(0, 0, 0)
                if base_font.name:
                    after_run.font.name = base_font.name
                if base_font.size:
                    after_run.font.size = base_font.size
        else:
            base_run.text = new_full
            base_run.font.color.rgb = RGBColor(0, 0, 0)
    else:
        if bold_segment and bold_segment in new_full:
            idx = new_full.index(bold_segment)
            before = new_full[:idx]
            after = new_full[idx + len(bold_segment):]
            if before:
                r = para.add_run(before)
                r.font.color.rgb = RGBColor(0, 0, 0)
            bold_run = para.add_run(bold_segment)
            bold_run.bold = True
            bold_run.font.color.rgb = RGBColor(0, 0, 0)
            if after:
                r = para.add_run(after)
                r.font.color.rgb = RGBColor(0, 0, 0)
        else:
            r = para.add_run(new_full)
            r.font.color.rgb = RGBColor(0, 0, 0)


def build_docx_from_template(template_path: Path, output_path: Path, data: dict):
    """원본 DOCX 복사 후 플레이스홀더 치환"""
    from docx import Document

    if not template_path.exists():
        print(f"[ERROR] 템플릿 없음: {template_path}")
        sys.exit(1)

    doc = Document(str(template_path))

    collab_type = data["collab_type"]
    handle = data["influencer_handle"]
    name = data["influencer_name"]
    contract_date = data["contract_date"]

    # IG 핸들 검증: 영문소문자/숫자/언더스코어/피리어드만 허용
    import re as _re_handle
    clean_handle = handle.lstrip("@")
    if not _re_handle.match(r'^[a-z0-9_.]+$', clean_handle):
        print(f"[ERROR] IG 핸들이 올바르지 않습니다: {handle}")
        print(f"  → 영문소문자/숫자/언더스코어/피리어드만 가능합니다.")
        print(f"  → 일본어 닉네임이나 호칭을 핸들로 넣지 마세요.")
        print(f"  → 세은에게 정확한 핸들을 확인하세요.")
        sys.exit(1)

    # 甲 서명자: 기본 許世恩. 시스템을 다른 담당자에게 전달할 때는
    # .env CONTRACT_SIGNER_NAME_JP 또는 --manual JSON의 company_signer로 본인 이름 지정 (세은 7/31 지시).
    company_signer = (
        data.get("company_signer")
        or os.getenv("CONTRACT_SIGNER_NAME_JP")
        or "許世恩"
    )

    # 해시태그 통일 룰 (세은 7/31 확정: 계약서에도 PPSU 제품은 #PPSU 추가, 유상/무상 동일)
    HASHTAG_MAP = {
        "ppsu_straw":    "#grosmimi #グロミミ #ストローマグ #スマートマグ #PPSU",
        "ppsu_onetouch": "#grosmimi #グロミミ #ストローマグ #スマートマグ #PPSU",
        "stainless":     "#grosmimi #グロミミ #ストローマグ #スマートマグ",
        "straw_set":     "#grosmimi #グロミミ #ストローマグ #スマートマグ #PPSU",
    }
    hashtags = HASHTAG_MAP[data["product_type"]]

    # 2026-07-31 신규 양식 앵커
    replacements = {
        "{{AGREEMENT_DATE}}": contract_date,
        "{{ACCOUNT_HANDLE}}": handle,
        "{{INFLUENCER_NAME}}": name,
        "{{COMPANY_NAME}}": company_signer,
        "{{VIDEO_COUNT}}": str(data["video_count"]),
        "{{PLATFORMS}}": data["platforms"],
        "{{PRODUCT_NAME}}": data["product_name"],
        "{{QUANTITY}}": str(data["quantity"]),
        "{{COLOR_SIZE}}": data["color_size"],
        "{{HASHTAGS}}": hashtags,
    }

    # bold_map: 특정 치환에서 볼드 처리할 부분 지정
    bold_map = {"{{HASHTAGS}}": hashtags}

    if collab_type == "paid":
        amount_raw = data.get("compensation_amount", "")
        # 숫자면 쉼표 포맷, 아니면 그대로
        try:
            amount_fmt = f"{int(str(amount_raw).replace(',', '')):,}"
        except (ValueError, TypeError):
            amount_fmt = str(amount_raw)
        replacements["{{PAYMENT_AMOUNT}}"] = amount_fmt
        bold_map["{{PAYMENT_AMOUNT}}"] = amount_fmt

    # 본문 단락 치환
    for para in doc.paragraphs:
        for old, new in replacements.items():
            if old in para.text:
                replace_text_in_paragraph(para, old, new, bold_segment=bold_map.get(old))

    # 테이블 내 치환
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for old, new in replacements.items():
                        if old in para.text:
                            replace_text_in_paragraph(para, old, new, bold_segment=bold_map.get(old))

    # 잔여 {{VAR}} 앵커 검증 (DocuSeal 필드 태그 {{...;role=...}}는 정상 잔존)
    residue = []
    all_paras = list(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                all_paras.extend(cell.paragraphs)
    for para in all_paras:
        for m in _re_handle.findall(r"\{\{[A-Z_]+\}\}", para.text):
            residue.append(m)
    if residue:
        print(f"[ERROR] 치환 안 된 앵커 잔존: {sorted(set(residue))}")
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    print(f"  저장: {output_path}")


def save_record(data: dict, files: list, output_dir: Path) -> Path:
    collab_type = data["collab_type"]
    record = {
        "contract_id": data["contract_id"],
        "generated_at": datetime.now().isoformat(),
        "collab_type": collab_type,
        "influencer": {
            "name": data["influencer_name"],
            "handle": "@" + data["influencer_handle"],
            "email": data.get("influencer_email", ""),
        },
        "terms": {
            "product_name": data.get("product_name", ""),
            "quantity": data.get("quantity", 1),
            "color_size": data.get("color_size", ""),
            "video_count": data.get("video_count", 1),
            "products_description": data.get("products_description", ""),
            "whitelisting_days": data.get("whitelisting_days", 180),
            **({"compensation": f"{data['compensation_amount']} {data.get('compensation_currency','JPY')}"} if collab_type == "paid" else {}),
        },
        "files": [str(f) for f in files],
        "status": "generated",
        "docusign_sent": False,
        "docusign_envelope_id": None,
        "signed_at": None,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    record_path = output_dir / f"contract_{data['influencer_handle']}_record.json"
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"  기록: {record_path}")
    return record_path


def print_summary(data: dict, files: list):
    collab_type = data["collab_type"]
    print("\n" + "=" * 60)
    print(f"계약서 생성 완료  [{collab_type.upper()}]")
    print("=" * 60)
    print(f"  계약 ID    : {data['contract_id']}")
    print(f"  인플루언서 : {data['influencer_name']} (@{data['influencer_handle']})")
    print(f"  제공 상품  : {data['product_name']} x{data['quantity']} ({data['color_size']})")
    print(f"  영상 개수  : {data['video_count']}本")
    if collab_type == "paid":
        print(f"  보상       : {data['compensation_amount']} {data.get('compensation_currency','JPY')}")
    else:
        print(f"  보상       : 기프팅 제품 (무상)")
    print("\n  생성 파일:")
    for f in files:
        print(f"    {f}")
    print("\n  다음 단계:")
    print("  1. DOCX 열어서 내용 최종 확인")
    print("  2. DocuSeal 업로드: python tools/send_docuseal_contract.py --name \"실명\" --email \"메일\" --pdf \"계약서.docx\" --no-send")
    print("     ⚠️ 인자명은 --pdf지만 반드시 .docx 경로를 넘길 것 (DOCX 루트가 {{태그}} 자동 제거. .pdf 넘기면 태그 글자 노출)")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="인플루언서 협업 계약서 생성 (원본 DOCX 템플릿 기반)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--handle", help="인스타 핸들 (협상 JSON 자동 로드)")
    group.add_argument("--manual", help="직접 JSON 입력")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR,
                        help="출력 디렉토리 (.env CONTRACT_OUTPUT_DIR 로 기본값 변경 가능)")
    args = parser.parse_args()

    check_deps()

    data = load_negotiation(args.handle) if args.handle else load_manual(args.manual)
    data = validate_fields(data)

    collab_type = data["collab_type"]
    handle_clean = data["influencer_handle"]
    influencer_name = data["influencer_name"]
    date_str = date.today().strftime("%Y%m%d")
    output_dir = Path(args.output)

    template_path = TEMPLATE_PAID if collab_type == "paid" else TEMPLATE_GIFTING

    print(f"\n[계약서 생성]")
    print(f"  유형     : {collab_type.upper()}")
    print(f"  대상     : {influencer_name} (@{handle_clean})")
    print(f"  템플릿   : {template_path.name}")

    filename_base = f"{influencer_name}_{date_str}"
    docx_path = output_dir / f"{filename_base}.docx"

    build_docx_from_template(template_path, docx_path, data)

    # PDF 자동 생성
    pdf_path = output_dir / f"{filename_base}.pdf"
    try:
        from docx2pdf import convert
        convert(str(docx_path), str(pdf_path))
        print(f"  저장: {pdf_path}")
    except ImportError:
        print("[ERROR] docx2pdf 없음. 설치: pip install docx2pdf")
        pdf_path = None
    except Exception as e:
        print(f"[ERROR] PDF 변환 실패: {e}")
        pdf_path = None

    files = [docx_path] + ([pdf_path] if pdf_path else [])

    # record는 기존 경로에 저장 (메타데이터)
    record_dir = Path("Data Storage/contracts/influencer")
    save_record(data, files, record_dir)
    print_summary(data, files)


if __name__ == "__main__":
    main()
