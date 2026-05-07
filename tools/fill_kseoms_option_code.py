"""
KSE OMS 팩킹리스트 옵션코드 자동 입력 도구

처리 흐름:
  1. kseoms.com/shipping2 에 Playwright로 로그인
  2. 팩킹리스트에서 일본어 상품명 읽기
  3. 매핑 테이블에서 옵션코드 찾기
  4. 빈 칸 입력 + 잘못된 값 수정 + 저장

Usage:
    python tools/fill_kseoms_option_code.py             # 빈 칸 채우기 + 오류 수정
    python tools/fill_kseoms_option_code.py --dry-run   # 입력 없이 매핑 결과만 확인
    python tools/fill_kseoms_option_code.py --headed    # 브라우저 표시 (디버그)

환경변수 (.env):
    KSEOMS_LOGIN_ID       - kseoms.com 로그인 ID
    KSEOMS_LOGIN_PASSWORD - kseoms.com 비밀번호
"""

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

KSEOMS_LOGIN_URL = "https://kseoms.com/login"
KSEOMS_SHIP_URL  = "https://kseoms.com/shipping2"
LOGIN_ID         = os.getenv("KSEOMS_LOGIN_ID", "")
LOGIN_PW         = os.getenv("KSEOMS_LOGIN_PASSWORD", "")
TMP_DIR          = PROJECT_ROOT / ".tmp"

# ── 옵션코드 매핑 테이블 ──────────────────────────────────────────────
# 상품명 키워드 + 옵션명 → 옵션코드
OPTION_MAP = {
    # PPSU 200ml
    ("ppsu", "200", "white"):           "8809466584558",
    ("ppsu", "200", "charcoal"):        "8809466584541",
    ("ppsu", "200", "pink"):            "8809466580956",
    ("ppsu", "200", "skyblue"):         "8809466582554",
    # PPSU 300ml
    ("ppsu", "300", "white"):           "8809466584527",
    ("ppsu", "300", "charcoal"):        "8809466584510",
    ("ppsu", "300", "pink"):            "8809466581038",
    ("ppsu", "300", "skyblue"):         "8809466582561",
    # PPSSU FLIP TOP 300ml
    ("flip", "300", "unicorn"):         "8809466588174",
    ("flip", "300", "dino"):            "8809466588181",
    # Stainless 200ml
    ("stainless", "200", "cherry"):     "8809466587740",
    ("stainless", "200", "bear"):       "8809466587733",
    ("stainless", "200", "olive"):      "8809466587726",
    # Stainless 300ml
    ("stainless", "300", "cherry"):     "8809466587771",
    ("stainless", "300", "bear"):       "8809466587764",
    ("stainless", "300", "olive"):      "8809466587757",
    # Accessory
    ("replacement", "straw", "2pack"):  "8809466582110",
    ("silicone", "nipple", "4pcs"):     "8809466583414",
    # Amazon용: ストロー&ニップル (상품명에 "ステージ2" + "交換" 포함)
    ("straw", "nipple", "replacement"): "8809466582110",
}


# ── 일본어 → 영어 정규화 테이블 ─────────────────────────────────────────
JP_TO_EN = {
    "ステンレス": "stainless",
    "フリップ":   "flip",
    "ワンタッチ": "flip",
    "ワンタッチ式": "flip",
    "シリコン":   "silicone",
    "交換用":     "replacement",
    "ストローニップル": "silicone nipple",
    "ストロー":   "straw",
    "乳首":       "nipple",
    "チェリー":   "cherry",
    "ベア":       "bear",
    "オリーブ":   "olive",
    "ホワイト":   "white",
    "チャコール": "charcoal",
    "ピンク":     "pink",
    "スカイブルー": "skyblue",
    "ユニコーン": "unicorn",
    "ダイノ":     "dino",
    "恐竜":       "dino",
    "4個入":      "4pcs",
    "4個":        "4pcs",
    "2個":        "2pack",
    "4pcs":       "4pcs",
    "2pack":      "2pack",
    "チェリーピーチ": "cherry",
    "ストロー&ニップル": "straw nipple",
    "ストロー＆ニップル": "straw nipple",
}


def _normalize(text: str) -> str:
    """일본어 키워드를 영어로 치환하여 소문자 문자열 반환."""
    result = text.lower()
    # 긴 키워드를 먼저 치환해야 부분 매칭 방지 (ex: ストローニップル > ストロー)
    for jp, en in sorted(JP_TO_EN.items(), key=lambda x: len(x[0]), reverse=True):
        result = result.replace(jp.lower(), " " + en + " ")
    return result


def lookup_option_code(item_name: str, option_name: str) -> str | None:
    """상품명(일본어 포함) + 옵션명으로 옵션코드 검색."""
    combined = _normalize(item_name + " " + option_name)

    for keywords, code in OPTION_MAP.items():
        if all(kw in combined for kw in keywords):
            return code

    return None


def _retry(fn, retries=3, delay=1.0, label=""):
    """Retry a synchronous callable up to `retries` times with `delay` between attempts."""
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i == retries - 1:
                raise
            print(f"    [retry {i+1}/{retries}] {label or ''} {type(e).__name__}: {e}")
            time.sleep(delay)


def _ss(page, name: str):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"kseoms_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"    📸 {path.name}")
    except Exception:
        pass


def _write_code(page, row_idx: int, code: str) -> bool:
    """AG Grid API로 옵션코드 셀 업데이트 + AJAX 저장 트리거."""
    return page.evaluate(f"""() => {{
        const api = window.gridOptions_orders && window.gridOptions_orders.api;
        if (!api) return false;
        let updated = false;
        api.forEachNode(node => {{
            if (node.rowIndex === {row_idx} && node.data) {{
                const oldValue = node.data.optionCode || '';
                node.data.optionCode = '{code}';
                // AG Grid UI 반영
                api.applyTransaction({{update: [node.data]}});
                // onCellEditingStopped 이벤트를 시뮬레이션하여 AJAX 저장 트리거
                const colDef = api.getColumnDef ? api.getColumnDef('optionCode') : null;
                const fakeEvent = {{
                    oldValue: oldValue,
                    newValue: '{code}',
                    data: node.data,
                    node: node,
                    column: {{ getId: () => 'optionCode' }}
                }};
                if (typeof gridCellUpdater === 'function') {{
                    gridCellUpdater(fakeEvent);
                }} else if (typeof window.gridCellUpdater === 'function') {{
                    window.gridCellUpdater(fakeEvent);
                }}
                updated = true;
            }}
        }});
        return updated;
    }}""")


def run(dry_run: bool = False, headless: bool = True):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print("=" * 56)
    print("KSE OMS 옵션코드 자동 입력 + 검증")
    if dry_run:
        print("[DRY-RUN] 실제 입력은 하지 않습니다")
    print("=" * 56)

    if not LOGIN_ID or not LOGIN_PW:
        print("✗ KSEOMS_LOGIN_ID / KSEOMS_LOGIN_PASSWORD 가 .env에 없습니다")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=300)
        page = browser.new_page()

        try:
            # ── Step 1: 로그인 ───────────────────────────────────────
            print("\n[1] KSE OMS 로그인 중...")
            page.goto(KSEOMS_LOGIN_URL, wait_until="networkidle", timeout=60000)
            _ss(page, "01_login")

            _retry(lambda: page.wait_for_selector("input[type=text], input[type=email]", timeout=15000),
                   retries=5, delay=2.0, label="login form selector")
            id_input = (
                page.query_selector("input[name*=id]")
                or page.query_selector("input[name*=user]")
                or page.query_selector("input[type=text]")
                or page.query_selector("input[type=email]")
            )
            pw_input = page.query_selector("input[type=password]")

            _retry(lambda: id_input.fill(LOGIN_ID), label="fill login ID")
            _retry(lambda: pw_input.fill(LOGIN_PW), label="fill login PW")

            submit = (
                page.query_selector("button[type=submit]")
                or page.query_selector("input[type=submit]")
                or page.query_selector("button:has-text('로그인')")
            )
            if submit:
                _retry(lambda: submit.click(), label="click submit")
            else:
                _retry(lambda: pw_input.press("Enter"), label="press Enter")

            page.wait_for_load_state("domcontentloaded", timeout=15000)
            _ss(page, "02_after_login")
            print("  ✓ 로그인 완료")

            # ── Step 2: 팩킹리스트 이동 ─────────────────────────────
            print("\n[2] 팩킹리스트로 이동 중...")
            page.goto(KSEOMS_SHIP_URL, wait_until="domcontentloaded", timeout=30000)
            print(f"  현재 URL: {page.url}")

            # 검색 버튼 클릭
            try:
                search_btn = _retry(
                    lambda: page.wait_for_selector("button:has-text('검 색'), button:has-text('검색')", timeout=5000),
                    label="search button selector")
                _retry(lambda: search_btn.click(), label="click search")
                print("  검색 버튼 클릭")
                page.wait_for_timeout(2000)
            except PWTimeout:
                print("  검색 버튼 없음, 계속 진행")

            # AG Grid 로드 대기
            _retry(lambda: page.wait_for_selector(".ag-row", timeout=15000),
                   label="AG Grid .ag-row")

            # HTML 저장 (검색 후)
            html = page.content()
            (TMP_DIR / "kseoms_debug.html").write_text(html, encoding="utf-8")
            print(f"  HTML 저장: .tmp/kseoms_debug.html")
            _ss(page, "03_packing_list")
            print("  ✓ 팩킹리스트 로드 완료")

            # ── Step 3: AG Grid JS API로 데이터 읽기 ────────────────
            print("\n[3] 옵션코드 비어있는 행 검색 중...")

            # JS API로 전체 row 데이터 추출 (일본어 상품명 포함)
            all_rows = page.evaluate("""() => {
                const api = window.gridOptions_orders && window.gridOptions_orders.api;
                if (!api) return [];
                const result = [];
                api.forEachNode(node => {
                    if (node.data) result.push({
                        idx: node.data.idx,
                        itemTitle:   node.data.itemTitle   || '',
                        itemTitleKr: node.data.itemTitleKr || '',
                        option:      node.data.option      || '',
                        optionCode:  node.data.optionCode  || '',
                        rowIndex:    node.rowIndex
                    });
                });
                return result;
            }""")

            print(f"  전체 행 수: {len(all_rows)}")
            for r in all_rows[:3]:
                print(f"  [디버그] {r}")

            filled = 0    # 새로 입력
            fixed  = 0    # 잘못된 값 수정
            no_map = 0    # 매핑 없음
            ok     = 0    # 이미 정확하게 입력됨

            for row_data in all_rows:
                item_title  = row_data.get("itemTitle", "")
                item_kr     = row_data.get("itemTitleKr", "")
                option_name = row_data.get("option", "")
                current_val = row_data.get("optionCode", "")
                row_idx     = row_data.get("rowIndex", 0)
                display     = (item_title or item_kr)[:35]

                # option 필드에 사이즈/색상이 명시된 경우: itemTitleKr(단일 사이즈) + option만 사용.
                # Amazon 리스팅 타이틀(itemTitle)은 "200ml / 300ml"처럼 여러 사이즈가 섞여 오탐을 유발하므로 제외.
                if option_name:
                    lookup_name = item_kr or item_title
                else:
                    lookup_name = (item_title + " " + item_kr).strip()

                expected = lookup_option_code(lookup_name, option_name)

                if not current_val:
                    # ── 빈 칸: 채우기 ────────────────────────────────
                    if expected:
                        print(f"  행 {row_idx+1}: [빈 칸] [{display}] → {expected}")
                        if not dry_run:
                            ok_ = _write_code(page, row_idx, expected)
                            print(f"    {'✓ 입력 완료' if ok_ else '⚠ 업데이트 실패'}")
                        filled += 1
                    else:
                        print(f"  ⚠ 행 {row_idx+1}: [빈 칸] [{display}] → 매핑 없음")
                        no_map += 1

                elif expected and current_val != expected:
                    # ── 잘못된 값: 수정 ───────────────────────────────
                    print(f"  행 {row_idx+1}: [오류] [{display}]")
                    print(f"    현재: {current_val}  →  정확: {expected}")
                    if not dry_run:
                        ok_ = _write_code(page, row_idx, expected)
                        print(f"    {'✓ 수정 완료' if ok_ else '⚠ 업데이트 실패'}")
                    fixed += 1

                elif not expected:
                    # 매핑 없는 상품 (예: 신제품) — 기존 값 유지
                    print(f"  ℹ 행 {row_idx+1}: [매핑미정] [{display}] 현재값={current_val}")
                    no_map += 1

                else:
                    # 정확하게 입력된 행
                    ok += 1

            # ── Step 4: 저장 버튼 클릭 ───────────────────────────────
            if (filled > 0 or fixed > 0) and not dry_run:
                print(f"\n[4] 저장 중...")
                _ss(page, "04_before_save")
                page.wait_for_timeout(500)
                # 구성품 추가 or 저장 버튼
                save_btn = (
                    page.query_selector("button:has-text('저장')")
                )
                if save_btn:
                    _retry(lambda: save_btn.click(), label="click save")
                    page.wait_for_timeout(2000)
                    _ss(page, "05_after_save")
                    print("  ✓ 저장 완료")
                else:
                    print("  저장 버튼 없음 — 수동 확인 필요")

            print(f"\n── 결과 ──────────────────────────")
            print(f"  새로 입력:  {filled}건")
            print(f"  오류 수정:  {fixed}건")
            print(f"  정상 확인:  {ok}건")
            print(f"  매핑 미정:  {no_map}건")

            if dry_run:
                print("\n[DRY-RUN] 실제 입력은 하지 않았습니다. --dry-run 제거 후 재실행하세요.")

        except PWTimeout as e:
            print(f"\n✗ 타임아웃: {e}")
            _ss(page, "error_timeout")
        except Exception as e:
            print(f"\n✗ 오류: {e}")
            _ss(page, "error_unknown")
            import traceback
            traceback.print_exc()
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="KSE OMS 옵션코드 자동 입력")
    parser.add_argument("--dry-run", action="store_true", help="매핑 결과 확인만 (실제 입력 안 함)")
    parser.add_argument("--headed",  action="store_true", help="브라우저 표시 (디버그용)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, headless=not args.headed)


if __name__ == "__main__":
    main()
