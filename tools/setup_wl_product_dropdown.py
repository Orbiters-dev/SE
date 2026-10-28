"""WL Code & Payment 탭 G(Product) SKU 드롭다운 설치 + 기존 값 표준화 (멱등).

2026-08-05 세은 지시: G열 표기 통일 — 드롭다운 24 SKU (파츠 제외, 온전한 제품만).
표기 형식: '{제품군} {용량}ml {색상}' 예) PPSU 200ml Butter / Stainless 300ml Cherry.

동작:
  1. '_dropdown_lists' V열에 SKU 24개 등록 (V1 헤더 sku_products)
  2. G4:G1000 데이터 검증 = ONE_OF_RANGE V2:V{여유 포함 동적 산출} (open range —
     빈 셀 무시되므로 추후 파츠/신규 SKU 추가 자동 수용),
     strict=False (복수 제품 ', ' 조합 허용, 경고만)
  3. 기존 G 값 표준 표기로 정규화. 복수 제품은 ', ' 조합 — 복수 선택 칩
     드롭다운의 저장 형식과 동일 (셀 값이 리스트 항목의 ', ' join 이면 칩 렌더).
     수량(x2)·파츠(Fliptop Cap/Nipple 4pcs)는 칩 표시 불가 → 메모 열로 이동.
  4. 셀 안 메모(개행 이후 텍스트)는 AU열 'Product Memo' 로 이동
  5. 원본 백업 .tmp/wl_product_g_backup_<date>.json

정규화는 이미 표준 표기인 값엔 no-op → 재실행 안전 (멱등).

⚠️ 칩(chip) 표시 + 복수 선택 허용은 Sheets API 미지원 (DataValidationRule 에 필드
없음 — SO 79653536, googleapis/google-api-python-client#2676 2026-02 종결 확인).
스크립트 실행 후 UI 수동 1회: G4:G1000 선택 → 데이터 확인 → 고급 옵션 →
표시 스타일 '칩' + '복수 선택 허용' 체크. 이후 재실행해도 UI 설정은 유지됨
(이 스크립트는 setDataValidation 을 다시 쏘면 칩 설정이 풀리므로, 칩 전환
후에는 --skip-dv 로 실행).
열 중간 삽입 금지 — sync_wl_codes_notion.py 등이 열 번호 하드코딩 (메모 열은 맨 끝 신설
AU. AT 는 기존 'Notes' 열이라 사용 불가).

Usage: PYTHONIOENCODING=utf-8 python tools/setup_wl_product_dropdown.py [--dry-run] [--skip-dv]
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sheets_utils import get_sheets_client  # noqa: E402

SHEET_ID = "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
WL_TAB = "WL Code & Payment"
DD_TAB = "_dropdown_lists"
SKU_COL = "V"           # _dropdown_lists 내 SKU 리스트 열
MEMO_COL_IDX = 47       # AU (1-based) — 맨 끝 신설 (AT 는 'Notes' 로 사용 중)
MEMO_COL = "AU"
DATA_START, DATA_END = 4, 1000
COL_G = 6               # 0-based

PPSU_COLORS = ["Skyblue", "Peach", "Butter", "White", "Cream Beige",
               "Pink", "Aqua Green", "Charcoal"]
SKUS = (
    [f"PPSU 200ml {c}" for c in PPSU_COLORS]
    + [f"PPSU 300ml {c}" for c in PPSU_COLORS]
    + ["Fliptop 300ml Dino", "Fliptop 300ml Unicorn"]
    + [f"Stainless {s}ml {c}" for s in (200, 300) for c in ("Cherry", "Olive", "Bear")]
)

# 다단어 색상 먼저 매칭 (순서 중요). blue→Skyblue: PPSU 8색 중 blue 계열은 스카이블루 유일.
COLOR_PATTERNS = [
    ("cream ?beige", "Cream Beige"), ("beige", "Cream Beige"),
    ("aqua ?green", "Aqua Green"),
    ("sky ?blue", "Skyblue"), ("blue", "Skyblue"),
    ("butter", "Butter"), (r"\bbt\b", "Butter"),  # bt = butter (河野様 계약 실측)
    ("peach", "Peach"), ("white", "White"), ("pink", "Pink"),
    ("charcoal", "Charcoal"), ("cherry", "Cherry"), ("olive", "Olive"),
    ("bear", "Bear"), ("dino", "Dino"), ("unicorn", "Unicorn"),
]


def parse_token(tok, prev_line, prev_size):
    """토큰 1개 → (표준 SKU 문자열, line, size). 파츠는 ('PART', 라벨) 반환."""
    t = re.sub(r"[\s_\-]+", " ", tok).strip().lower()
    if not t:
        return None, prev_line, prev_size
    if "nipple" in t:
        return ("PART", "Nipple 4pcs"), prev_line, prev_size
    if "cap" in t and "fliptop" in t:
        return ("PART", "Fliptop Cap"), prev_line, prev_size
    qty = ""
    m = re.search(r"\bx\s*0*(\d+)\b", t)  # x2 / x 2 / x02 전부 수용
    if m:
        qty = f" x{int(m.group(1))}"
        t = t.replace(m.group(0), " ")
    line = ("PPSU" if "ppsu" in t else "Stainless" if "stain" in t
            else "Fliptop" if "fliptop" in t else prev_line)
    m = re.search(r"(200|300)", t)
    size = m.group(1) if m else prev_size
    if line == "Fliptop":
        size = "300"
    color = None
    for pat, name in COLOR_PATTERNS:
        if re.search(pat, t):
            color = name
            break
    if not (line and size and color):
        raise ValueError(f"파싱 실패: {tok!r} (line={line} size={size} color={color})")
    base = f"{line} {size}ml {color}"
    if base not in SKUS:
        raise ValueError(f"마스터 밖 SKU: {base!r} <- {tok!r}")
    if qty:
        return ("QTY", base, qty.strip()), line, size
    return base, line, size


def normalize(raw):
    """G 셀 원본 → (표준 표기, 메모).

    복수 제품은 ', ' join — 복수 선택 칩의 셀 저장 형식과 동일.
    파츠·수량은 칩 표시 불가 → 메모로 분리. 표준 표기 입력이면 no-op (멱등).
    """
    lines = raw.split("\n")
    memo_parts = [x.strip() for x in lines[1:] if x.strip()]
    product_part = lines[0].strip()
    tokens = [x for x in re.split(r"[/+,]", product_part) if x.strip()]
    out, prev_line, prev_size = [], None, None
    for tok in tokens:
        sku, prev_line, prev_size = parse_token(tok, prev_line, prev_size)
        if sku is None:
            continue
        if isinstance(sku, tuple) and sku[0] == "PART":
            memo_parts.insert(0, f"+ {sku[1]} 동봉")
        elif isinstance(sku, tuple) and sku[0] == "QTY":
            out.append(sku[1])
            memo_parts.insert(0, f"{sku[1]} {sku[2]} (수량)")
        else:
            out.append(sku)
    seen = set()
    out = [s for s in out if not (s in seen or seen.add(s))]  # 칩은 중복 불가
    return ", ".join(out), " | ".join(memo_parts)


def main():
    dry = "--dry-run" in sys.argv
    skip_dv = "--skip-dv" in sys.argv
    gc = get_sheets_client()
    sh = gc.open_by_key(SHEET_ID)
    wl = sh.worksheet(WL_TAB)
    dd = sh.worksheet(DD_TAB)

    # 0) 메모 열 안전 확인 (열 부족 시 확장). 헤더가 'Product Memo' 면 우리 열 —
    #    재실행 시 기존 메모와 병합 (멱등). 다른 용도 데이터가 있으면 중단.
    if wl.col_count < MEMO_COL_IDX:
        wl.resize(rows=wl.row_count, cols=MEMO_COL_IDX)
        print(f"[wl] cols {MEMO_COL_IDX} 로 확장 ({MEMO_COL} 신설)")
    at_vals = wl.get(f"{MEMO_COL}1:{MEMO_COL}{DATA_END}")
    existing_memo = {i: r[0].strip() for i, r in enumerate(at_vals, 1)
                     if r and r[0].strip()}
    ours = existing_memo.get(3) == "Product Memo"
    if existing_memo and not ours:
        print(f"!! {MEMO_COL}열에 다른 용도 데이터 {len(existing_memo)}건 — 중단. "
              f"예: {list(existing_memo.items())[:3]}")
        sys.exit(1)

    # 1) 원본 읽기 + 백업
    gvals = wl.get(f"G1:G{DATA_END}")
    origin = {i: (r[0] if r else "") for i, r in enumerate(gvals, 1)}
    # 타임스탬프 파일명 — 재실행이 이전 백업을 덮어쓰지 않게
    backup = Path(__file__).resolve().parent.parent / ".tmp" / \
        f"wl_product_g_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(
        {k: v for k, v in origin.items() if v.strip()}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"[backup] {backup}")

    # 2) 정규화
    new_g, memos, diffs, errors = {}, {}, [], []
    for row in range(DATA_START, DATA_END + 1):
        raw = origin.get(row, "")
        if not raw.strip():
            continue
        try:
            norm, memo = normalize(raw)
        except ValueError as e:
            errors.append((row, raw, str(e)))
            continue
        if norm != raw:
            new_g[row] = norm
            diffs.append((row, raw, norm))
        if memo:
            memos[row] = memo
    if errors:
        print("\n!! 파싱 실패 — 아무것도 안 씀. 수동 확인 필요:")
        for row, raw, e in errors:
            print(f"  row{row}: {raw!r} -> {e}")
        sys.exit(1)

    print(f"\n[plan] 치환 {len(diffs)}건 / 메모 이동 {len(memos)}건")
    for row, raw, norm in diffs:
        m = f"   memo-> {memos[row]!r}" if row in memos else ""
        print(f"  row{row}: {raw!r}\n        -> {norm!r}{m}")
    if dry:
        print("\n[dry-run] 종료")
        return

    # 3) _dropdown_lists V열 SKU 등록 (열 부족 시 확장)
    if dd.col_count < 22:
        dd.resize(rows=dd.row_count, cols=22)
    sh.values_batch_update({
        "valueInputOption": "RAW",
        "data": [{
            "range": f"'{DD_TAB}'!{SKU_COL}1:{SKU_COL}{len(SKUS) + 1}",
            "values": [["sku_products"]] + [[s] for s in SKUS],
        }],
    })
    print(f"[dd] {SKU_COL}1:{SKU_COL}{len(SKUS) + 1} SKU {len(SKUS)}개 등록")

    # 4) G 치환 + 메모 기록 (기존 메모 있으면 병합, 이미 있으면 skip)
    data = [{"range": f"'{WL_TAB}'!G{r}", "values": [[v]]} for r, v in new_g.items()]
    data.append({"range": f"'{WL_TAB}'!{MEMO_COL}3", "values": [["Product Memo"]]})
    for r, m in memos.items():
        prev = existing_memo.get(r, "")
        if m in prev:
            continue
        merged = f"{prev} | {m}" if prev else m
        data.append({"range": f"'{WL_TAB}'!{MEMO_COL}{r}", "values": [[merged]]})
    sh.values_batch_update({"valueInputOption": "RAW", "data": data})
    print(f"[write] G {len(new_g)}셀 치환 + {MEMO_COL} 메모 {len(memos)}셀 + 헤더")

    # 5) 데이터 검증 설치 (기존 I/J 드롭다운과 동일 방식).
    #    UI 에서 칩+복수 선택으로 전환한 뒤에는 --skip-dv 로 실행해 설정 보존.
    if skip_dv:
        print("[dv] --skip-dv — 검증 규칙 미변경 (UI 칩 설정 보존)")
    else:
        # 범위 끝 = SKU 수 x2 여유 (최소 50) — 빈 셀은 드롭다운에서 무시되므로
        # 추후 V열에 파츠/신규 SKU 를 append 만 하면 재실행 없이 자동 반영.
        dv_end = max(50, len(SKUS) * 2 + 1)
        sh.batch_update({"requests": [{"setDataValidation": {
            "range": {"sheetId": wl.id,
                      "startRowIndex": DATA_START - 1, "endRowIndex": DATA_END,
                      "startColumnIndex": COL_G, "endColumnIndex": COL_G + 1},
            "rule": {
                "condition": {"type": "ONE_OF_RANGE",
                              "values": [{"userEnteredValue": f"='{DD_TAB}'!${SKU_COL}$2:${SKU_COL}${dv_end}"}]},
                "showCustomUi": True, "strict": False,
            },
        }}]})
        print(f"[dv] G{DATA_START}:G{DATA_END} 드롭다운 설치")

    # 6) 사후 검증 — 재읽기 후 전 셀이 SKU 마스터의 ', ' 조합인지
    check = wl.get(f"G{DATA_START}:G{DATA_END}")
    bad = []
    for i, r in enumerate(check, DATA_START):
        v = (r[0] if r else "").strip()
        if not v:
            continue
        if any(tok.strip() not in SKUS for tok in v.split(", ")):
            bad.append((i, v))
    if bad:
        print(f"\n!! 사후 검증 실패 {len(bad)}건: {bad}")
        sys.exit(1)
    filled = sum(1 for r in check if r and r[0].strip())
    print(f"[verify] G {filled}셀 전부 표준 표기 확인 OK")


if __name__ == "__main__":
    main()
