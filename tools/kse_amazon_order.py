"""
KSE OMS Amazon JP 주문 처리 파이프라인

흐름:
  1. kseoms.com 로그인
  2. /orders → 주문등록(Excel) 탭
  3. 세은이 준비한 Excel 파일 업로드 (예: 0317.xlsx)
  4. 주문 목록에서 옵션코드 입력
  5. 전체 선택 → 배송접수(국제)
  6. 팩킹리스트(/shipping2) 이동 확인
  7. 아마존 엑셀 다운로드 → {MMDD}_amazon_주문서.xlsx 저장
  8. 주문 요약 생성 → Teams 전송

Usage:
    python tools/kse_amazon_order.py --headed              # 브라우저 표시 (기본)
    python tools/kse_amazon_order.py --headed --dry-run    # 조회만 (배송접수 X)
    python tools/kse_amazon_order.py --headed --date 0317  # 날짜 지정
"""

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

KSEOMS_LOGIN_URL = "https://kseoms.com/login"
KSEOMS_ORDERS_URL = "https://kseoms.com/orders"
KSEOMS_SHIP_URL = "https://kseoms.com/shipping2"
LOGIN_ID = os.getenv("KSEOMS_LOGIN_ID", "")
LOGIN_PW = os.getenv("KSEOMS_LOGIN_PASSWORD", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
TMP_DIR = PROJECT_ROOT / ".tmp"
ORDER_DIR = Path(r"C:\Users\orbit\Desktop\s\아마존 주문서")

# ── 옵션코드 매핑 (fill_kseoms_option_code.py와 동일) ──
OPTION_MAP = {
    ("ppsu", "200", "white"):           "8809466584558",
    ("ppsu", "200", "charcoal"):        "8809466584541",
    ("ppsu", "200", "pink"):            "8809466580956",
    ("ppsu", "200", "skyblue"):         "8809466582554",
    ("ppsu", "300", "white"):           "8809466584527",
    ("ppsu", "300", "charcoal"):        "8809466584510",
    ("ppsu", "300", "pink"):            "8809466581038",
    ("ppsu", "300", "skyblue"):         "8809466582561",
    ("flip", "300", "unicorn"):         "8809466588174",
    ("flip", "300", "dino"):            "8809466588181",
    ("stainless", "200", "cherry"):     "8809466587740",
    ("stainless", "200", "bear"):       "8809466587733",
    ("stainless", "200", "olive"):      "8809466587726",
    ("stainless", "300", "cherry"):     "8809466587771",
    ("stainless", "300", "bear"):       "8809466587764",
    ("stainless", "300", "olive"):      "8809466587757",
    ("replacement", "straw", "2pack"):  "8809466582110",
    ("silicone", "nipple", "4pcs"):     "8809466583414",
    ("straw", "nipple", "replacement"): "8809466582110",
}

JP_TO_EN = {
    "ステンレス": "stainless", "フリップ": "flip", "ワンタッチ": "flip",
    "ワンタッチ式": "flip", "シリコン": "silicone", "交換用": "replacement",
    "ストローニップル": "silicone nipple", "ストロー": "straw", "乳首": "nipple",
    "チェリー": "cherry", "ベア": "bear", "オリーブ": "olive",
    "ホワイト": "white", "チャコール": "charcoal", "ピンク": "pink",
    "スカイブルー": "skyblue", "ユニコーン": "unicorn", "ダイノ": "dino",
    "恐竜": "dino", "4個入": "4pcs", "4個": "4pcs", "2個": "2pack",
    "4pcs": "4pcs", "2pack": "2pack", "チェリーピーチ": "cherry",
    "ストロー&ニップル": "straw nipple", "ストロー＆ニップル": "straw nipple",
}


def _normalize(text: str) -> str:
    result = text.lower()
    for jp, en in sorted(JP_TO_EN.items(), key=lambda x: len(x[0]), reverse=True):
        result = result.replace(jp.lower(), " " + en + " ")
    return result


def lookup_option_code(item_name: str, option_name: str = "") -> str | None:
    norm_item = _normalize(item_name)
    norm_opt = _normalize(option_name)
    size_match = re.search(r'(\d{3})ml', norm_opt)
    size_from_opt = size_match.group(1) if size_match else None
    combined = norm_item + " " + norm_opt
    for keywords, code in OPTION_MAP.items():
        if size_from_opt:
            size_kw = [k for k in keywords if k in ("200", "300")]
            if size_kw and size_kw[0] != size_from_opt:
                continue
        if all(kw in combined for kw in keywords):
            return code
    return None


def _retry(fn, retries=3, delay=1.0, label=""):
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
    path = TMP_DIR / f"kse_amazon_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"    ss: {path.name}")
    except Exception:
        pass


def _write_code(page, row_idx: int, code: str) -> bool:
    """AG Grid API로 옵션코드 셀 업데이트 + AJAX 저장 트리거."""
    return page.evaluate(f"""() => {{
        // 여러 grid API 후보 탐색
        let api = null;
        const candidates = [
            window.gridOptions_orders && window.gridOptions_orders.api,
            window.gridOptions && window.gridOptions.api,
        ];
        for (const a of candidates) {{
            if (a && typeof a.forEachNode === 'function') {{ api = a; break; }}
        }}
        if (!api) {{
            for (const key of Object.keys(window)) {{
                try {{
                    if (window[key] && window[key].api && typeof window[key].api.forEachNode === 'function') {{
                        api = window[key].api; break;
                    }}
                }} catch(e) {{}}
            }}
        }}
        if (!api) return false;
        let updated = false;
        api.forEachNode(node => {{
            if (node.rowIndex === {row_idx} && node.data) {{
                const oldValue = node.data.optionCode || '';
                node.data.optionCode = '{code}';
                api.applyTransaction({{update: [node.data]}});
                // gridCellUpdater 호출하여 AJAX 저장 트리거
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


def _close_notices(page):
    """KSE OMS 공지사항 처리: 모두닫기 버튼 클릭 → DOM에서 공지 요소 완전 제거."""
    # 1. "모두닫기" 버튼 클릭 시도 (다이얼로그 자동 수락됨)
    for attempt in range(3):
        try:
            btn = (
                page.query_selector("button.btn-notice-hide:visible")
                or page.query_selector("button:visible:has-text('모두닫기')")
                or page.query_selector("button:visible:has-text('모두 닫기')")
            )
            if btn:
                btn.click(timeout=5000)
                page.wait_for_timeout(2000)
                print(f"  공지사항 모두닫기 클릭 (attempt {attempt+1})")
            else:
                break
        except Exception:
            page.wait_for_timeout(1000)
            break

    # 2. 공지 DOM 요소 완전 제거 + 모달 잔여물 정리
    removed = page.evaluate("""() => {
        let count = 0;
        // 공지 컨테이너 제거 (다양한 셀렉터 시도)
        const selectors = [
            '.notice-area', '.notice-wrap', '.notice-container',
            '.board-notice', '[class*=notice]', '.alert-area',
            '#noticeArea', '#notice_area',
        ];
        for (const sel of selectors) {
            document.querySelectorAll(sel).forEach(el => {
                // 공지 내용이 많은 큰 요소만 제거 (업로드 폼 보호)
                if (el.innerText && el.innerText.length > 500) {
                    el.remove();
                    count++;
                }
            });
        }
        // 모달/백드롭 정리
        document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
        document.querySelectorAll('.modal.in, .modal.show').forEach(m => {
            m.classList.remove('in', 'show');
            m.style.display = 'none';
        });
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
        return count;
    }""")
    if removed:
        print(f"  공지 DOM 제거: {removed}개 요소")
    page.wait_for_timeout(1000)


def find_excel_file(date_str: str) -> Path | None:
    """날짜 문자열(MMDD)로 업로드용 Excel 파일 찾기.
    예: 0317 → 0317.xlsx (NOT 0317_amazon_주문서.xlsx)
    """
    target = ORDER_DIR / f"{date_str}.xlsx"
    if target.exists():
        return target
    # .xls도 시도
    target2 = ORDER_DIR / f"{date_str}.xls"
    if target2.exists():
        return target2
    return None


def run(dry_run=False, headless=False, date_str=None):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    import urllib.request
    import urllib.error

    # 날짜 결정
    if not date_str:
        date_str = date.today().strftime("%m%d")

    excel_path = find_excel_file(date_str)
    if not excel_path:
        print(f"ERROR: {ORDER_DIR / f'{date_str}.xlsx'} 파일이 없습니다!")
        print(f"  세은이 Excel 변환 후 저장했는지 확인해 주세요.")
        return

    download_name = f"{date_str}_amazon_주문서.xlsx"

    print("=" * 60)
    print("  Amazon JP 주문 처리 파이프라인")
    print(f"  업로드 파일: {excel_path.name}")
    print(f"  다운로드 이름: {download_name}")
    if dry_run:
        print("  [DRY-RUN] 배송접수는 하지 않습니다")
    print("=" * 60)

    if not LOGIN_ID or not LOGIN_PW:
        print("ERROR: KSEOMS_LOGIN_ID / KSEOMS_LOGIN_PASSWORD 가 .env에 없습니다")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=500)
        page = browser.new_page(viewport={"width": 1600, "height": 900})

        # 다이얼로그 자동 수락 (한 번만 등록)
        def _safe_accept(dialog):
            try:
                print(f"  [다이얼로그] {dialog.message}")
                dialog.accept()
            except Exception:
                pass
        page.on("dialog", _safe_accept)

        try:
            # ══════════════════════════════════════════════════════════
            # Step 1: 로그인
            # ══════════════════════════════════════════════════════════
            print("\n[1/8] KSE OMS 로그인...")
            page.goto(KSEOMS_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            id_input = (
                page.query_selector("input[name*=id]")
                or page.query_selector("input[name*=user]")
                or page.query_selector("input[type=text]")
                or page.query_selector("input[type=email]")
            )
            pw_input = page.query_selector("input[type=password]")

            if not id_input or not pw_input:
                print("  ERROR: 로그인 폼을 찾을 수 없습니다")
                _ss(page, "01_error")
                return

            _retry(lambda: id_input.fill(LOGIN_ID), label="fill ID")
            _retry(lambda: pw_input.fill(LOGIN_PW), label="fill PW")

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
            page.wait_for_timeout(3000)
            _ss(page, "01_logged_in")
            print(f"  로그인 완료 (URL: {page.url})")

            # ── 재로그인 헬퍼 (세션 만료 대응) ──
            def _ensure_logged_in():
                """현재 페이지가 로그인 페이지면 재로그인."""
                if "/login" not in page.url and not page.query_selector("input[type=password]"):
                    return
                print("  [재로그인] 세션 만료 감지, 재로그인...")
                page.goto(KSEOMS_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                id_inp = (
                    page.query_selector("input[name*=id]")
                    or page.query_selector("input[name*=user]")
                    or page.query_selector("input[type=text]")
                    or page.query_selector("input[type=email]")
                )
                pw_inp = page.query_selector("input[type=password]")
                if id_inp and pw_inp:
                    _retry(lambda: id_inp.fill(LOGIN_ID), label="re-fill ID")
                    _retry(lambda: pw_inp.fill(LOGIN_PW), label="re-fill PW")
                    sub = (
                        page.query_selector("button[type=submit]")
                        or page.query_selector("input[type=submit]")
                        or page.query_selector("button:has-text('로그인')")
                    )
                    if sub:
                        _retry(lambda: sub.click(), label="re-click submit")
                    else:
                        _retry(lambda: pw_inp.press("Enter"), label="re-press Enter")
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)
                    print(f"  [재로그인] 완료 (URL: {page.url})")

            # ══════════════════════════════════════════════════════════
            # Step 2: /orders → 주문등록(Excel) 탭
            # ══════════════════════════════════════════════════════════
            print("\n[2/8] 주문등록(Excel) 페이지로 이동...")
            page.goto(KSEOMS_ORDERS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # 공지 팝업 "모두닫기" 버튼 클릭
            _close_notices(page)

            _ss(page, "02_orders_page")

            # "주문등록(Excel)" 탭 찾기
            excel_tab = (
                page.query_selector("a:has-text('주문등록(Excel)')")
                or page.query_selector("button:has-text('주문등록(Excel)')")
                or page.query_selector("li:has-text('주문등록(Excel)') a")
                or page.query_selector("[data-tab*='excel'], [href*='excel']")
            )
            if not excel_tab:
                # 탭 목록에서 검색
                tabs = page.query_selector_all("a, button, li a, .nav-link, .tab-link")
                for tab in tabs:
                    txt = tab.inner_text().strip()
                    if "주문등록" in txt and ("Excel" in txt or "엑셀" in txt):
                        excel_tab = tab
                        print(f"  탭 발견: '{txt}'")
                        break

            if excel_tab:
                _retry(lambda: excel_tab.click(), label="click Excel tab")
                page.wait_for_timeout(2000)
                print("  주문등록(Excel) 탭 클릭 완료")
            else:
                # 직접 URL로 이동 시도
                print("  주문등록(Excel) 탭 못 찾음, URL 직접 이동 시도...")
                page.goto("https://kseoms.com/orders/excel", wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)

            _ss(page, "02_excel_tab")

            # ══════════════════════════════════════════════════════════
            # Step 3: Excel 파일 업로드
            # ══════════════════════════════════════════════════════════
            print(f"\n[3/8] Excel 업로드: {excel_path.name}...")

            # ── Amazon 라디오 버튼 선택 (업로드 모달 좌측) ──
            amazon_radio = page.evaluate("""() => {
                // 모달 내 라디오 버튼에서 amazon 찾기
                const radios = document.querySelectorAll('input[type=radio]');
                for (const r of radios) {
                    const val = (r.value || '').toLowerCase();
                    const label = r.parentElement ? r.parentElement.innerText.toLowerCase() : '';
                    if (val.includes('amazon') || label.includes('amazon')) {
                        r.click();
                        r.checked = true;
                        // change 이벤트 트리거
                        r.dispatchEvent(new Event('change', {bubbles: true}));
                        return {found: true, value: r.value, label: label.trim().substring(0, 50)};
                    }
                }
                return {found: false};
            }""")
            if amazon_radio.get("found"):
                print(f"  Amazon 라디오 선택: {amazon_radio.get('value', '')}")
            else:
                print("  WARNING: Amazon 라디오 버튼 못 찾음 - 수동 확인 필요")
                # 디버그: 모든 라디오 버튼 나열
                all_radios = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('input[type=radio]')).map(r => ({
                        value: r.value, name: r.name, checked: r.checked,
                        label: r.parentElement ? r.parentElement.innerText.trim().substring(0, 50) : ''
                    }));
                }""")
                print(f"  라디오 목록: {json.dumps(all_radios, ensure_ascii=False, indent=2)}")
            page.wait_for_timeout(1000)

            # ── 파일 업로드 ──
            file_input = page.query_selector("input[type=file]")
            if not file_input:
                file_input = page.query_selector("input[type=file][accept*='.xls']")

            if file_input:
                file_input.set_input_files(str(excel_path))
                page.wait_for_timeout(2000)
                print(f"  파일 선택 완료: {excel_path.name}")
            else:
                print("  WARNING: file input을 찾지 못함")
                _ss(page, "03_no_file_input")

            _ss(page, "03_file_selected")

            # 업로드/등록 버튼 클릭
            upload_btn = (
                page.query_selector("button:has-text('업로드')")
                or page.query_selector("button:has-text('등록')")
                or page.query_selector("button:has-text('Upload')")
                or page.query_selector("input[type=submit][value*='업로드']")
                or page.query_selector("input[type=submit][value*='등록']")
            )
            if not upload_btn:
                all_btns = page.query_selector_all("button, input[type=submit], input[type=button]")
                for btn in all_btns:
                    txt = btn.inner_text().strip() if btn.evaluate("el => el.tagName") != "INPUT" else (btn.get_attribute("value") or "")
                    if any(kw in txt for kw in ["업로드", "등록", "확인", "저장"]):
                        upload_btn = btn
                        print(f"  업로드 버튼 발견: '{txt}'")
                        break

            if upload_btn:
                _retry(lambda: upload_btn.click(), label="click upload")
                page.wait_for_timeout(5000)
                print("  업로드 버튼 클릭 완료")
            else:
                print("  WARNING: 업로드 버튼 찾지 못함")

            _ss(page, "03_uploaded")

            # 업로드 결과 확인
            page_text = page.evaluate("() => document.body.innerText.substring(0, 2000)")
            for line in page_text.split('\n'):
                line = line.strip()
                if any(kw in line for kw in ['성공', '실패', '오류', '건', 'error', '등록']):
                    print(f"  [결과] {line[:100]}")

            _ss(page, "03_after_upload")

            # ── 모달 닫기 ──
            print("  모달 닫기 시도...")
            # 방법 1: 닫기/X 버튼
            modal_closed = False
            close_btn = (
                page.query_selector(".modal.in .close")
                or page.query_selector(".modal.in button[data-dismiss='modal']")
                or page.query_selector("#upload_orders_form .close")
                or page.query_selector("#upload_orders_form button[data-dismiss='modal']")
            )
            if close_btn:
                try:
                    close_btn.click()
                    page.wait_for_timeout(1000)
                    modal_closed = True
                    print("  모달 닫기 (버튼)")
                except Exception:
                    pass

            # 방법 2: Escape 키
            if not modal_closed:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
                print("  모달 닫기 (Escape)")

            # 방법 3: JS로 강제 닫기
            modal_still_open = page.evaluate("""() => {
                const modal = document.querySelector('#upload_orders_form');
                if (modal && (modal.classList.contains('in') || modal.classList.contains('show'))) return true;
                const anyModal = document.querySelector('.modal.in, .modal.show');
                return !!anyModal;
            }""")
            if modal_still_open:
                page.evaluate("""() => {
                    document.querySelectorAll('.modal').forEach(m => {
                        m.classList.remove('in', 'show');
                        m.style.display = 'none';
                    });
                    document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                    document.body.classList.remove('modal-open');
                    document.body.style.overflow = '';
                    document.body.style.paddingRight = '';
                }""")
                page.wait_for_timeout(500)
                print("  모달 닫기 (JS 강제)")

            page.wait_for_timeout(2000)
            _ss(page, "03_modal_closed")

            # ── 배송접수(대기목록) 탭으로 전환 ──
            # /orders 페이지 새로 로드
            print("  /orders 페이지로 이동...")
            page.goto(KSEOMS_ORDERS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # 세션 만료 시 재로그인
            _ensure_logged_in()
            if "/login" in page.url or "/top" in page.url:
                page.goto(KSEOMS_ORDERS_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

            # 공지 팝업 "모두닫기" 버튼 클릭
            _close_notices(page)

            # "배송접수(대기목록/All)" 탭 클릭 (기본이 주문등록(Excel) 탭일 수 있음)
            print("  배송접수(대기목록) 탭 클릭...")
            waitlist_tab = None
            tab_links = page.query_selector_all("a")
            for link in tab_links:
                try:
                    txt = link.inner_text().strip()
                except Exception:
                    txt = ""
                if "대기목록" in txt or "Waiting List" in txt:
                    waitlist_tab = link
                    print(f"  탭 발견: '{txt}'")
                    break

            if waitlist_tab:
                waitlist_tab.click(timeout=5000)
                page.wait_for_timeout(3000)
                print("  대기목록 탭 클릭 완료")
            else:
                print("  WARNING: 대기목록 탭 못 찾음")

            # 검색 버튼 클릭
            try:
                search_btn = page.query_selector("button:has-text('검 색')") or page.query_selector("button:has-text('검색')")
                if search_btn:
                    search_btn.click(timeout=5000)
                    page.wait_for_timeout(4000)
                    print("  검색 완료")
            except Exception:
                pass

            _ss(page, "03_after_tab_switch")

            # 디버그: 현재 탭 및 그리드 상태 확인
            tab_debug = page.evaluate("""() => {
                const activeTabs = Array.from(document.querySelectorAll('.active, .nav-link.active, [aria-selected=true]'));
                const tabTexts = activeTabs.map(t => t.innerText?.trim().substring(0, 50));
                // AG Grid 상태
                let gridRows = 0;
                for (const key of Object.keys(window)) {
                    try {
                        if (window[key] && window[key].api && typeof window[key].api.forEachNode === 'function') {
                            window[key].api.forEachNode(n => { if (n.data) gridRows++; });
                            break;
                        }
                    } catch(e) {}
                }
                return {activeTabs: tabTexts, gridRows: gridRows};
            }""")
            print(f"  [디버그] 활성 탭: {tab_debug.get('activeTabs', [])}")
            print(f"  [디버그] 그리드 행수: {tab_debug.get('gridRows', 0)}")

            # ══════════════════════════════════════════════════════════
            # Step 4: 옵션코드 입력
            # ══════════════════════════════════════════════════════════
            print("\n[4/8] 옵션코드 입력...")

            # AG Grid 로드 대기
            try:
                page.wait_for_selector(".ag-row", timeout=10000)
                print("  AG Grid 로드 확인")
            except Exception:
                print("  AG Grid 아직 미로드, 3초 추가 대기...")
            page.wait_for_timeout(3000)

            # AG Grid에서 데이터 읽기
            rows = page.evaluate("""() => {
                let api = null;
                const candidates = [
                    window.gridOptions && window.gridOptions.api,
                    window.gridOptions_orders && window.gridOptions_orders.api,
                ];
                for (const a of candidates) {
                    if (a && typeof a.forEachNode === 'function') { api = a; break; }
                }
                if (!api) {
                    // 모든 window 키에서 찾기
                    for (const key of Object.keys(window)) {
                        try {
                            if (window[key] && window[key].api &&
                                typeof window[key].api.forEachNode === 'function') {
                                api = window[key].api;
                                break;
                            }
                        } catch(e) {}
                    }
                }
                if (!api) return [];
                const result = [];
                api.forEachNode(node => {
                    if (node.data) result.push({
                        rowIndex: node.rowIndex,
                        itemTitle: node.data.itemTitle || node.data['상품명'] || '',
                        itemTitleKr: node.data.itemTitleKr || '',
                        option: node.data.option || node.data['옵션명'] || '',
                        optionCode: node.data.optionCode || node.data['옵션코드'] || '',
                    });
                });
                return result;
            }""")

            print(f"  주문 건수: {len(rows)}건")

            if rows:
                filled = 0
                for row in rows:
                    item_title = row.get("itemTitle", "")
                    item_kr = row.get("itemTitleKr", "")
                    option = row.get("option", "")
                    current = row.get("optionCode", "").strip()
                    idx = row.get("rowIndex", 0)
                    # option이 있으면 itemTitleKr만 사용 (Amazon itemTitle은 "200ml/300ml" 중복 포함해 오탐 유발)
                    if option:
                        item = item_kr or item_title
                    else:
                        item = (item_title + " " + item_kr).strip()
                    expected = lookup_option_code(item, option)

                    if not expected:
                        print(f"  [{idx}] 매핑 없음: {item[:40]}")
                        continue
                    if current == expected:
                        print(f"  [{idx}] 이미 정확: {expected}")
                        continue

                    print(f"  [{idx}] {current or '(빈칸)'} → {expected}")

                    if not dry_run:
                        # 방법 1: _write_code (API + gridCellUpdater AJAX 저장)
                        ok = _write_code(page, idx, expected)
                        if ok:
                            print(f"    OK (API+AJAX)")
                        else:
                            # 방법 2: DOM 기반 셀 더블클릭 → 입력
                            print(f"    API 실패, DOM 방식 시도...")
                            page.evaluate(f"""() => {{
                                const apis = [
                                    window.gridOptions_orders && window.gridOptions_orders.api,
                                    window.gridOptions && window.gridOptions.api,
                                ];
                                for (const api of apis) {{
                                    if (!api) continue;
                                    try {{ api.ensureIndexVisible({idx}); }} catch(e) {{}}
                                    try {{ api.ensureColumnVisible('optionCode'); }} catch(e) {{}}
                                }}
                            }}""")
                            page.wait_for_timeout(500)
                            cell = (
                                page.query_selector(f".ag-row[row-index='{idx}'] .ag-cell[col-id='optionCode']")
                                or page.query_selector(f".ag-row[row-index='{idx}'] .ag-cell[col-id='옵션코드']")
                            )
                            if cell:
                                _retry(lambda: cell.dblclick(), label="dblclick cell")
                                page.wait_for_timeout(800)
                                edit_input = (
                                    cell.query_selector("input")
                                    or cell.query_selector("textarea")
                                    or page.query_selector(".ag-cell-editor input")
                                    or page.query_selector(".ag-popup-editor input")
                                )
                                if edit_input:
                                    edit_input.fill("")
                                    edit_input.type(expected)
                                    edit_input.press("Tab")
                                    page.wait_for_timeout(500)
                                    print(f"    OK (DOM 더블클릭)")
                                else:
                                    print(f"    WARN: 편집 input 없음")
                            else:
                                print(f"    WARN: 셀 못 찾음")
                    filled += 1

                print(f"  옵션코드 입력: {filled}건")

                # 저장 버튼
                if filled > 0 and not dry_run:
                    save_btn = page.query_selector("button:has-text('저장')")
                    if save_btn:
                        _retry(lambda: save_btn.click(), label="click save")
                        page.wait_for_timeout(3000)
                        print("  저장 완료")

            _ss(page, "04_options_filled")

            if dry_run:
                print("\n[DRY-RUN] 여기까지. 배송접수는 하지 않았습니다.")
                _ss(page, "dryrun_done")
                page.wait_for_timeout(10000)
                browser.close()
                return

            # ══════════════════════════════════════════════════════════
            # Step 5: 전체 선택 → 배송접수(국제)
            # ══════════════════════════════════════════════════════════
            print("\n[5/8] 전체 선택 + 배송접수(국제)...")

            # 전체 체크박스
            select_all = (
                page.query_selector(".ag-header-select-all input[type=checkbox]")
                or page.query_selector(".ag-header-cell input[type=checkbox]")
                or page.query_selector("th input[type=checkbox]")
            )
            if not select_all:
                checkboxes = page.query_selector_all("input[type=checkbox]")
                if checkboxes:
                    select_all = checkboxes[0]

            if select_all:
                if not select_all.is_checked():
                    _retry(lambda: select_all.click(), label="click select-all")
                    page.wait_for_timeout(1000)
                print("  전체 선택 완료")
            else:
                print("  WARNING: 전체 선택 체크박스 못 찾음")

            _ss(page, "05_all_selected")

            # 배송접수(국제) 버튼
            ship_btn = (
                page.query_selector("button:has-text('배송접수(국제)')")
                or page.query_selector("a:has-text('배송접수(국제)')")
            )
            if not ship_btn:
                all_btns = page.query_selector_all("button, a, input[type=button]")
                for btn in all_btns:
                    try:
                        txt = btn.inner_text().strip()
                    except Exception:
                        txt = btn.get_attribute("value") or ""
                    if "배송접수" in txt and "국제" in txt:
                        ship_btn = btn
                        break

            if ship_btn:
                _retry(lambda: ship_btn.click(), label="click ship intl")
                page.wait_for_timeout(8000)
                print("  배송접수(국제) 클릭 완료!")
                print(f"  현재 URL: {page.url}")
            else:
                print("  ERROR: 배송접수(국제) 버튼 못 찾음")
                _ss(page, "05_no_ship_btn")

            _ss(page, "05_shipped")

            # ══════════════════════════════════════════════════════════
            # Step 6: 팩킹리스트(/shipping2) 이동 확인
            # ══════════════════════════════════════════════════════════
            print("\n[6/8] 팩킹리스트 이동 확인...")

            # 자동으로 /shipping2로 넘어갔는지 확인
            if "shipping2" in page.url:
                print("  /shipping2로 자동 이동됨!")
            else:
                print(f"  현재 URL: {page.url}")
                print("  /shipping2로 수동 이동...")
                page.goto(KSEOMS_SHIP_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

            # 공지 팝업 "모두닫기" 버튼 클릭
            _close_notices(page)

            # 검색 버튼 클릭
            try:
                search_btn = (
                    page.query_selector("button:has-text('검 색')")
                    or page.query_selector("button:has-text('검색')")
                )
                if search_btn:
                    search_btn.click(timeout=5000)
                    page.wait_for_timeout(3000)
                    print("  검색 완료")
            except Exception as e:
                print(f"  검색 버튼 클릭 실패: {e}")

            # AG Grid 로드 대기
            try:
                page.wait_for_selector(".ag-row", timeout=10000)
                print("  AG Grid 로드 확인")
            except Exception:
                print("  AG Grid 미로드, 계속 진행...")

            _ss(page, "06_packing_list")
            print(f"  팩킹리스트 확인 (URL: {page.url})")

            # ══════════════════════════════════════════════════════════
            # Step 7: 아마존 엑셀 다운로드
            # ══════════════════════════════════════════════════════════
            print(f"\n[7/8] 아마존 엑셀 다운로드...")

            # 모달/팝업이 남아있으면 강제 닫기
            page.evaluate("""() => {
                document.querySelectorAll('.modal.in, .modal.show').forEach(m => {
                    m.classList.remove('in', 'show'); m.style.display = 'none';
                });
                document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
            }""")
            page.wait_for_timeout(500)

            # 다운로드 버튼 찾기 (드롭다운 토글)
            download_btn = None
            all_btns = page.query_selector_all("button, a")
            for btn in all_btns:
                try:
                    txt = btn.inner_text().strip()
                except Exception:
                    txt = ""
                if "다운로드" in txt or "download" in txt.lower():
                    download_btn = btn
                    print(f"  다운로드 버튼 발견: '{txt}'")
                    break

            if download_btn:
                # 스크롤하여 버튼 보이게
                page.evaluate("""(btn) => {
                    btn.scrollIntoView({block: 'center'});
                }""", download_btn)
                page.wait_for_timeout(500)

                _retry(lambda: download_btn.click(), label="click download")
                page.wait_for_timeout(1500)
                print("  다운로드 드롭다운 클릭")

                _ss(page, "07_dropdown_open")

                # "아마존 엑셀" 메뉴 찾기
                amazon_dl = None
                menu_items = page.query_selector_all("a, button, li a, .dropdown-item, .dropdown-menu a")
                for item in menu_items:
                    try:
                        txt = item.inner_text().strip()
                    except Exception:
                        txt = ""
                    if "아마존" in txt and ("엑셀" in txt or "Excel" in txt or "excel" in txt):
                        amazon_dl = item
                        print(f"  메뉴 발견: '{txt}'")
                        break

                if amazon_dl:
                    with page.expect_download(timeout=30000) as download_info:
                        _retry(lambda: amazon_dl.click(), label="click amazon excel")

                    download = download_info.value
                    save_path = ORDER_DIR / download_name
                    download.save_as(str(save_path))
                    print(f"  다운로드 완료: {save_path}")
                else:
                    print("  WARNING: '아마존 엑셀' 메뉴 못 찾음")
                    menu_texts = page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('.dropdown-menu a, .dropdown-item, .dropdown-menu li'))
                            .map(a => a.innerText.trim()).filter(t => t);
                    }""")
                    print(f"  드롭다운 메뉴: {menu_texts}")
            else:
                print("  WARNING: 다운로드 버튼 못 찾음")
                _ss(page, "07_no_download_btn")

            _ss(page, "07_downloaded")

            # ══════════════════════════════════════════════════════════
            # Step 8: 주문 요약 생성 → Teams 전송
            # ══════════════════════════════════════════════════════════
            print(f"\n[8/8] 주문 요약 생성 + Teams 전송...")

            # AG Grid에서 팩킹리스트 데이터 읽기
            packing_rows = page.evaluate("""() => {
                let api = null;
                for (const key of Object.keys(window)) {
                    try {
                        if (window[key] && window[key].api &&
                            typeof window[key].api.forEachNode === 'function') {
                            api = window[key].api;
                            break;
                        }
                    } catch(e) {}
                }
                if (!api) return [];
                const result = [];
                api.forEachNode(node => {
                    if (node.data) result.push(JSON.parse(JSON.stringify(node.data)));
                });
                return result;
            }""")

            print(f"  팩킹리스트 데이터: {len(packing_rows)}건")

            if packing_rows:
                # kse_order_summary.py의 build_summary 로직 직접 실행
                from collections import defaultdict

                channel_map = {
                    "amazonjp": "아마존", "amazon": "아마존",
                    "rakuten": "라쿠텐", "rakutenjp": "라쿠텐",
                }

                def classify_product(t_kr):
                    t = t_kr.lower()
                    size_match = re.search(r"(\d+)\s*ml", t)
                    size = f"{size_match.group(1)}ml" if size_match else ""
                    if "replacement straw" in t:
                        return ("replacement straw", "")
                    if "silicone" in t and "nipple" in t:
                        return ("silicone nipple", "")
                    if any(kw in t for kw in ["dino", "unicorn", "flip"]):
                        return ("PPSU", size)
                    if "stainless" in t:
                        return ("스테인리스", size)
                    if "ppsu" in t:
                        return ("PPSU", size)
                    return ("기타", size)

                summary = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
                for row in packing_rows:
                    market = (row.get("market") or "").lower()
                    channel = channel_map.get(market, market)
                    title_kr = row.get("itemTitleKr") or ""
                    qty = int(row.get("orderQty") or 1)
                    cat, size = classify_product(title_kr)
                    summary[channel][cat][size] += qty

                channel_order = ["아마존", "라쿠텐"]
                cat_order = ["PPSU", "스테인리스", "replacement straw", "silicone nipple", "기타"]
                lines = []
                for ch in channel_order:
                    if ch not in summary:
                        continue
                    cats = summary[ch]
                    first = True
                    for cat in cat_order:
                        if cat not in cats:
                            continue
                        sizes = cats[cat]
                        if "" in sizes:
                            size_str = f"x {sizes['']}"
                        else:
                            parts = []
                            for s in sorted(sizes.keys()):
                                if s:
                                    parts.append(f"{s} x {sizes[s]}")
                            size_str = "/ ".join(parts)
                        prefix = f"{ch}: " if first else "            "
                        lines.append(f"{prefix}({cat}) {size_str}")
                        first = False

                lines.append("")
                lines.append("주문 들어온 것 공유드립니다.")
                summary_text = "\n".join(lines)

                print()
                print(summary_text)

                # .tmp에 저장
                out = PROJECT_ROOT / ".tmp" / "order_summary.txt"
                out.parent.mkdir(parents=True, exist_ok=True)
                with open(out, "w", encoding="utf-8") as f:
                    f.write(summary_text)

                # Teams 직접 전송 (심플 텍스트)
                print("\n  Teams 전송 중...")
                teams_webhook = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", "")
                if teams_webhook:
                    import urllib.request as urllib_req
                    payload = json.dumps({"text": f"**{date.today().isoformat()} 주문 처리 완료**\n\n{summary_text}"}).encode("utf-8")
                    req = urllib_req.Request(teams_webhook, data=payload, method="POST")
                    req.add_header("Content-Type", "application/json")
                    try:
                        with urllib_req.urlopen(req, timeout=15) as r:
                            if r.status in (200, 202):
                                print("  [OK] Teams 직접 전송 완료!")
                            else:
                                print(f"  [WARN] Teams 응답: {r.status}")
                    except Exception as e:
                        print(f"  [WARN] Teams 전송 실패: {e}")
                else:
                    print("  [WARN] TEAMS_WEBHOOK_URL_SEEUN 미설정")
            else:
                print("  팩킹리스트 데이터 없음")

            # ══════════════════════════════════════════════════════════
            # 완료
            # ══════════════════════════════════════════════════════════
            print(f"\n{'=' * 60}")
            print(f"  Amazon JP 주문 처리 완료!")
            print(f"  업로드: {excel_path.name}")
            print(f"  다운로드: {download_name}")
            print(f"{'=' * 60}")

        except PWTimeout as e:
            print(f"\nERROR 타임아웃: {e}")
            _ss(page, "error_timeout")
        except Exception as e:
            print(f"\nERROR: {e}")
            _ss(page, "error")
            import traceback
            traceback.print_exc()
        finally:
            print("\n30초 후 브라우저 종료...")
            page.wait_for_timeout(30000)
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KSE OMS Amazon JP 주문 처리")
    parser.add_argument("--dry-run", action="store_true", help="조회만 (배송접수 X)")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시")
    parser.add_argument("--date", type=str, help="날짜 (MMDD, 예: 0317)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, headless=not args.headed, date_str=args.date)
