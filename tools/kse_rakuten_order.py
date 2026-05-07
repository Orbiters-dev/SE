"""
KSE OMS Rakuten 주문수집 + 옵션코드 입력 + 배송접수(국제) 자동화

흐름:
  1. kseoms.com 로그인
  2. 배송접수(대기목록) → 주문수집(API) 탭
  3. 마켓: rakuten_jp, 계정: 라쿠텐JP 선택
  4. 날짜 설정 (화~금: 어제~오늘, 월: 금~오늘)
  5. "주문서 가져오기" 클릭
  6. 주문 목록에서 옵션코드 입력 (바코드)
  7. 전체 선택 → 배송접수(국제) 클릭

Usage:
    python tools/kse_rakuten_order.py --headed           # 브라우저 표시
    python tools/kse_rakuten_order.py --headed --dry-run # 조회만 (배송접수 안 함)
"""

import argparse
import io
import os
import re
import sys
import time
from datetime import date, timedelta
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

# ── 옵션코드 매핑 테이블 (바코드) ──────────────────────────────────────
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
    # PPSU FLIP TOP 300ml
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
}

JP_TO_EN = {
    "ステンレス": "stainless",
    "フリップ":   "flip",
    "ワンタッチ": "flip",
    "ワンタッチ式": "flip",
    "シリコン":   "silicone",
    "交換用":     "replacement",
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
    "ストローニップル": "silicone nipple",
    "4個入":      "4pcs",
    "4個":        "4pcs",
    "2個":        "2pack",
    "2セット":    "2pack",
    "4pcs":       "4pcs",
    "2pack":      "2pack",
    "チェリーピーチ": "cherry",
}


def _normalize(text: str) -> str:
    result = text.lower()
    # 긴 키워드를 먼저 치환해야 부분 매칭 방지 (ex: ストローニップル > ストロー)
    for jp, en in sorted(JP_TO_EN.items(), key=lambda x: len(x[0]), reverse=True):
        result = result.replace(jp.lower(), " " + en + " ")
    return result


def lookup_option_code(item_name: str, option_name: str = "") -> str | None:
    """옵션명에서 사이즈/컬러를 우선 추출하고, 상품명에서 타입을 추출하여 매핑."""
    norm_item = _normalize(item_name)
    norm_opt = _normalize(option_name)

    # 옵션명에서 사이즈 추출 (サイズ:300ml → 300)
    import re
    size_from_opt = None
    size_match = re.search(r'(\d{3})ml', norm_opt)
    if size_match:
        size_from_opt = size_match.group(1)  # "200" or "300"

    # 옵션명 + 상품명 합침
    combined = norm_item + " " + norm_opt

    for keywords, code in OPTION_MAP.items():
        # 사이즈가 옵션명에 명시되어 있으면 그 사이즈만 매칭
        if size_from_opt:
            size_kw = [k for k in keywords if k in ("200", "300")]
            if size_kw and size_kw[0] != size_from_opt:
                continue  # 옵션명의 사이즈와 다르면 스킵
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
    path = TMP_DIR / f"kse_rakuten_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"    ss: {path.name}")
    except Exception:
        pass


def get_date_range():
    """날짜 범위 계산: 편의점 결제(コンビニ前払) 늦은 입금 대비 14일 전~오늘"""
    today = date.today()
    start = today - timedelta(days=14)
    return start, today


def run(dry_run=False, headless=True, expected_count=0):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    start_date, end_date = get_date_range()

    print("=" * 56)
    print("KSE OMS Rakuten 주문수집 + 옵션코드 + 배송접수")
    print(f"날짜 범위: {start_date} ~ {end_date}")
    if expected_count > 0:
        print(f"기대 건수: {expected_count}건 (상위 파이프라인 전달)")
    if dry_run:
        print("[DRY-RUN] 배송접수는 하지 않습니다")
    print("=" * 56)

    if not LOGIN_ID or not LOGIN_PW:
        print("ERROR: KSEOMS_LOGIN_ID / KSEOMS_LOGIN_PASSWORD 가 .env에 없습니다")
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=500)
        page = browser.new_page(viewport={"width": 1600, "height": 900})

        try:
            # ── Step 1: 로그인 ──
            print("\n[1] KSE OMS 로그인 중...")
            page.goto(KSEOMS_LOGIN_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            _ss(page, "01_login_page")

            # 로그인 폼
            id_input = (
                page.query_selector("input[name*=id]")
                or page.query_selector("input[name*=user]")
                or page.query_selector("input[type=text]")
                or page.query_selector("input[type=email]")
            )
            pw_input = page.query_selector("input[type=password]")

            if not id_input or not pw_input:
                print("  ERROR: 로그인 폼을 찾을 수 없습니다")
                _ss(page, "01_error_no_form")
                return

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
            page.wait_for_timeout(3000)
            _ss(page, "02_logged_in")
            print(f"  로그인 완료 (URL: {page.url})")

            # ── 공지 팝업 "모두닫기"만 클릭 (다른 곳의 일반 "닫기" 버튼 오클릭 방지) ──
            closed_popups = 0
            for _ in range(80):
                btn = (
                    page.query_selector("button:has-text('모두닫기')")
                    or page.query_selector("a:has-text('모두닫기')")
                )
                if not btn:
                    break
                try:
                    btn.click()
                    closed_popups += 1
                    page.wait_for_timeout(150)
                except Exception:
                    break
            if closed_popups:
                print(f"  공지 팝업 {closed_popups}개 닫음")

            # ── Step 2: 주문수집(API) 페이지로 직접 이동 ──
            print("\n[2] 주문수집(API) 페이지로 이동...")
            page.goto("https://kseoms.com/integration_api/getOrders", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            _ss(page, "04_api_tab")
            print(f"  현재 URL: {page.url}")

            # ── Step 3: 마켓 선택 (rakuten_jp) ──
            print("\n[3] 마켓 선택: rakuten_jp...")

            # 첫 번째 드롭다운 (마켓)
            selects = page.query_selector_all("select")
            print(f"  select 요소 수: {len(selects)}")
            for i, sel in enumerate(selects):
                options_text = sel.evaluate("""el => {
                    return Array.from(el.options).map(o => o.text + '=' + o.value).join(', ')
                }""")
                print(f"  select[{i}]: {options_text[:200]}")

            market_selected = False
            for sel in selects:
                has_rakuten = sel.evaluate("""el => {
                    return Array.from(el.options).some(o =>
                        o.value.includes('rakuten') || o.text.includes('rakuten')
                    )
                }""")
                if has_rakuten:
                    sel.select_option(label="rakuten_jp") if not sel.evaluate("""el => {
                        const opt = Array.from(el.options).find(o => o.value === 'rakuten_jp');
                        return !!opt;
                    }""") else None
                    # value로 시도
                    try:
                        sel.select_option(value="rakuten_jp")
                        market_selected = True
                        print("  rakuten_jp 선택 완료 (value)")
                    except Exception:
                        # label로 시도
                        try:
                            sel.select_option(label="rakuten_jp")
                            market_selected = True
                            print("  rakuten_jp 선택 완료 (label)")
                        except Exception:
                            # text 포함 옵션 찾기
                            sel.evaluate("""el => {
                                for (const o of el.options) {
                                    if (o.text.includes('rakuten') || o.value.includes('rakuten')) {
                                        el.value = o.value;
                                        el.dispatchEvent(new Event('change', {bubbles: true}));
                                        return true;
                                    }
                                }
                                return false;
                            }""")
                            market_selected = True
                            print("  rakuten 관련 옵션 선택 (JS)")
                    break

            if not market_selected:
                print("  WARNING: rakuten_jp 마켓을 선택하지 못함")

            page.wait_for_timeout(2000)
            _ss(page, "05_market_selected")

            # ── Step 4: 계정 선택 (라쿠텐JP) ──
            print("\n[4] 계정 선택: 라쿠텐JP...")
            # 마켓 선택 후 두 번째 드롭다운이 나타남
            page.wait_for_timeout(2000)
            selects2 = page.query_selector_all("select")
            account_selected = False

            for sel in selects2:
                # 옵션 목록 읽기 — label 매칭용
                options_info = sel.evaluate("""el => {
                    return Array.from(el.options).map(o => ({text: o.text, value: o.value}));
                }""")
                # 라쿠텐/ラクテン/Rakuten 포함 옵션 찾기
                match = None
                for opt in options_info:
                    text = opt.get("text", "") or ""
                    if "라쿠텐" in text or "ラクテン" in text or "Rakuten" in text:
                        match = opt
                        break
                if not match:
                    continue

                # Playwright 정식 API로 선택 (UI 이벤트 시뮬레이션 완전 처리)
                try:
                    sel.select_option(value=match["value"])
                    account_selected = True
                    print(f"  라쿠텐JP 계정 선택 완료 (value={match['value']}, label={match['text']})")
                except Exception as e1:
                    try:
                        sel.select_option(label=match["text"])
                        account_selected = True
                        print(f"  라쿠텐JP 계정 선택 완료 (label)")
                    except Exception as e2:
                        print(f"  ERROR: select_option 실패 — {e1} / {e2}")
                break

            if not account_selected:
                print("  WARNING: 라쿠텐JP 계정을 선택하지 못함")

            page.wait_for_timeout(2000)
            _ss(page, "06_account_selected")

            # ── DEBUG: 페이지 HTML 저장 ──
            html_dump = page.content()
            dump_path = TMP_DIR / "kse_rakuten_page_dump.html"
            dump_path.write_text(html_dump, encoding="utf-8")
            print(f"  [DEBUG] 페이지 HTML 저장: {dump_path}")

            # ── Step 5: 날짜 설정 ──
            print(f"\n[5] 날짜 설정: {start_date} ~ {end_date}...")

            # date input 찾기
            date_inputs = page.query_selector_all("input[type=date], input[type=text][placeholder*='날짜'], input[type=text][placeholder*='date']")
            if len(date_inputs) < 2:
                # 더 넓게 검색
                date_inputs = page.query_selector_all("input[type=date]")
            if len(date_inputs) < 2:
                # 모든 input에서 날짜 형태 찾기
                all_inputs = page.query_selector_all("input")
                date_inputs = []
                for inp in all_inputs:
                    inp_type = inp.get_attribute("type") or ""
                    placeholder = inp.get_attribute("placeholder") or ""
                    val = inp.get_attribute("value") or ""
                    if inp_type == "date" or "날짜" in placeholder or "date" in placeholder.lower() or re.match(r"\d{4}-\d{2}-\d{2}", val):
                        date_inputs.append(inp)

            print(f"  날짜 입력 필드: {len(date_inputs)}개")

            if len(date_inputs) >= 2:
                start_str = start_date.strftime("%Y-%m-%d")
                end_str = end_date.strftime("%Y-%m-%d")

                # 순수 DOM value 세팅 + change 이벤트 (datepicker update 호출은 포맷 망가뜨림)
                page.evaluate(f"""() => {{
                    const inputs = document.querySelectorAll('input[name=start_date_time], input.datepicker_sdate');
                    inputs.forEach(i => {{
                        i.value = '{start_str}';
                        i.dispatchEvent(new Event('input', {{bubbles: true}}));
                        i.dispatchEvent(new Event('change', {{bubbles: true}}));
                        i.dispatchEvent(new Event('blur', {{bubbles: true}}));
                    }});
                }}""")
                page.evaluate(f"""() => {{
                    const inputs = document.querySelectorAll('input[name=end_date_time], input.datepicker_edate');
                    inputs.forEach(i => {{
                        i.value = '{end_str}';
                        i.dispatchEvent(new Event('input', {{bubbles: true}}));
                        i.dispatchEvent(new Event('change', {{bubbles: true}}));
                        i.dispatchEvent(new Event('blur', {{bubbles: true}}));
                    }});
                }}""")
                page.wait_for_timeout(500)

                # 실제 value 검증
                actual_start = page.evaluate("() => document.querySelector('input[name=start_date_time]')?.value || ''")
                actual_end = page.evaluate("() => document.querySelector('input[name=end_date_time]')?.value || ''")
                print(f"  날짜 입력 완료: {start_str} ~ {end_str}")
                print(f"  [검증] 실제 input value: start='{actual_start}', end='{actual_end}'")
            else:
                print("  WARNING: 날짜 입력 필드 부족, 기본값으로 진행")

            _ss(page, "07_date_set")

            # ── Step 6: "주문서 가져오기" 클릭 ──
            print("\n[6] 주문서 가져오기 클릭...")
            fetch_btn = (
                page.query_selector("button:has-text('주문서 가져오기')")
                or page.query_selector("a:has-text('주문서 가져오기')")
                or page.query_selector("input[value*='주문서 가져오기']")
            )
            if not fetch_btn:
                # 넓은 범위 탐색
                all_btns = page.query_selector_all("button, a, input[type=button], input[type=submit]")
                for btn in all_btns:
                    txt = (btn.inner_text() or "").strip() if btn.evaluate("el => el.tagName") != "INPUT" else (btn.get_attribute("value") or "")
                    if "주문서" in txt and "가져오기" in txt:
                        fetch_btn = btn
                        break

            if fetch_btn:
                # alert/dialog 핸들러: 텍스트 캡처 후 수락
                alert_messages = []
                def on_dialog(d):
                    try:
                        alert_messages.append(f"{d.type}: {d.message}")
                        print(f"  [DIALOG] {d.type}: {d.message}")
                        d.accept()
                    except Exception:
                        # 이미 처리된 dialog는 무시 (Playwright handler 중복 호출 방지)
                        pass
                page.on("dialog", on_dialog)

                # 네트워크 응답 캡처
                api_responses = []
                def on_response(resp):
                    if "api_search_order" in resp.url.lower() or "integration_api" in resp.url.lower():
                        try:
                            body_preview = resp.text()[:500]
                        except Exception:
                            body_preview = "(body read failed)"
                        api_responses.append({"url": resp.url, "status": resp.status, "body": body_preview})
                        print(f"  [NET] {resp.status} {resp.url}")
                        print(f"  [NET body] {body_preview}")
                page.on("response", on_response)

                _retry(lambda: fetch_btn.click(), label="click fetch orders")
                print("  주문서 가져오기 클릭 완료")
                # AG Grid 로딩 대기 (API 응답 + 렌더링)
                try:
                    page.wait_for_selector(".ag-row", timeout=30000)
                    page.wait_for_timeout(2000)  # 추가 렌더링 대기
                    print("  AG Grid 로드 완료")
                except Exception:
                    print("  AG Grid 로드 타임아웃 (30s) — 주문 없을 수 있음")
                    page.wait_for_timeout(5000)

                # 응답 메시지 캡처
                try:
                    api_guide_msg = page.evaluate("() => document.querySelector('#api_guide')?.innerText || ''")
                    total_success = page.evaluate("() => document.querySelector('#total_success_cnt')?.innerText || ''")
                    total_fail = page.evaluate("() => document.querySelector('#total_fail_cnt')?.innerText || ''")
                    print(f"  [응답] api_guide: {api_guide_msg!r}")
                    print(f"  [응답] total_success_cnt: {total_success}")
                    print(f"  [응답] total_fail_cnt: {total_fail}")
                except Exception as e:
                    print(f"  [응답 캡처 실패] {e}")

                # 클릭 후 HTML 덤프
                try:
                    post_html = page.content()
                    post_dump_path = TMP_DIR / "kse_rakuten_page_dump_POST_fetch.html"
                    post_dump_path.write_text(post_html, encoding="utf-8")
                    print(f"  [DEBUG] 주문서가져오기 후 HTML 저장: {post_dump_path}")
                except Exception as e:
                    print(f"  [HTML dump 실패] {e}")
            else:
                print("  ERROR: '주문서 가져오기' 버튼을 찾지 못함")
                _ss(page, "08_no_fetch_btn")
                return

            _ss(page, "08_orders_loaded")

            # ── Step 7: 주문 목록 읽기 + 옵션코드 입력 ──
            print("\n[7] 주문 목록 읽기 + 옵션코드 입력...")

            # AG Grid에서 데이터 읽기 — 모든 컬럼 키를 먼저 덤프
            col_keys = page.evaluate("""() => {
                const apis = [
                    window.gridOptions && window.gridOptions.api,
                    window.gridOptions_orders && window.gridOptions_orders.api,
                ];
                for (const api of apis) {
                    if (!api) continue;
                    let keys = [];
                    api.forEachNode(node => {
                        if (node.data && keys.length === 0) {
                            keys = Object.keys(node.data);
                        }
                    });
                    if (keys.length > 0) return keys;
                }
                // AG Grid DOM에서 col-id 추출
                const cells = document.querySelectorAll('.ag-header-cell');
                return Array.from(cells).map(c => c.getAttribute('col-id') || c.innerText?.trim());
            }""")
            print(f"  [디버그] 컬럼 키: {col_keys}")

            # AG Grid API로 데이터 읽기
            rows = page.evaluate("""() => {
                const apis = [
                    window.gridOptions && window.gridOptions.api,
                    window.gridOptions_orders && window.gridOptions_orders.api,
                ];
                for (const api of apis) {
                    if (!api) continue;
                    const result = [];
                    api.forEachNode(node => {
                        if (node.data) {
                            const d = node.data;
                            result.push({
                                rowIndex: node.rowIndex,
                                allData: JSON.stringify(d).substring(0, 500),
                                itemTitle: d.itemTitle || d['상품명'] || d['상품명-Admin'] || d.productName || '',
                                option: d.option || d['옵션명'] || d.optionName || d.optionTitle || '',
                                optionCode: d.optionCode || d['옵션코드'] || '',
                                productCode: d.productCode || d['상품코드'] || '',
                            });
                        }
                    });
                    if (result.length > 0) return result;
                }
                return [];
            }""")

            if not rows:
                # AG Grid API 없으면 DOM에서 직접 읽기
                print("  AG Grid API 없음, DOM에서 직접 읽기...")
                page.wait_for_timeout(3000)
                _ss(page, "09_checking_table")

                ag_rows = page.query_selector_all(".ag-row")
                print(f"  .ag-row 수: {len(ag_rows)}")

                if ag_rows:
                    rows = page.evaluate("""() => {
                        const rows = document.querySelectorAll('.ag-row');
                        return Array.from(rows).map((row, i) => {
                            const cells = row.querySelectorAll('.ag-cell');
                            const data = {};
                            cells.forEach(cell => {
                                const colId = cell.getAttribute('col-id') || '';
                                data[colId] = cell.innerText.trim();
                            });
                            return {
                                rowIndex: i,
                                allData: JSON.stringify(data).substring(0, 500),
                                itemTitle: data['상품명-Admin'] || data['상품명'] || '',
                                option: data['옵션명'] || data['option'] || '',
                                optionCode: data['옵션코드'] || data['optionCode'] || '',
                                productCode: data['상품코드'] || data['productCode'] || '',
                            };
                        });
                    }""")

            if not rows:
                print("  주문 목록이 비어 있습니다 (0건)")
                _ss(page, "09_no_orders")
                if expected_count > 0:
                    print(f"  ✗ 기대 {expected_count}건 vs 실제 0건 — 파이프라인 NO_DATA")
                return 2  # NO_DATA

            print(f"  주문 건수: {len(rows)}건")
            if expected_count > 0 and len(rows) < expected_count:
                print(f"  ⚠ 기대 {expected_count}건 vs 실제 {len(rows)}건 — 누락 가능성")
            for r in rows:
                print(f"  [{r.get('rowIndex', '?')}] 상품: {r.get('itemTitle', '?')[:40]}")
                print(f"       옵션명: {r.get('option', '(없음)')}")
                print(f"       옵션코드: {r.get('optionCode', '(빈칸)')}")
                if r.get('allData'):
                    print(f"       [raw] {r.get('allData', '')[:200]}")

            # ── 옵션코드 컬럼 편집 가능 여부 체크 ──
            col_editable = page.evaluate("""() => {
                const apis = [
                    window.gridOptions && window.gridOptions.api,
                    window.gridOptions_orders && window.gridOptions_orders.api,
                ];
                for (const api of apis) {
                    if (!api) continue;
                    const cols = api.getColumnDefs ? api.getColumnDefs() : [];
                    const optCol = cols.find(c =>
                        c.field === 'optionCode' || c.field === '옵션코드' ||
                        c.colId === 'optionCode' || c.colId === '옵션코드'
                    );
                    if (optCol) return {
                        found: true,
                        field: optCol.field || optCol.colId,
                        editable: !!optCol.editable,
                        cellEditor: optCol.cellEditor || null,
                        headerName: optCol.headerName || '',
                        raw: JSON.stringify(optCol).substring(0, 300)
                    };
                }
                // columnApi 시도
                for (const api of apis) {
                    if (!api) continue;
                    try {
                        const allCols = api.getAllGridColumns ? api.getAllGridColumns() :
                                        (api.columnModel ? api.columnModel.getAllGridColumns() : []);
                        for (const col of allCols) {
                            const colDef = col.getColDef ? col.getColDef() : col.colDef;
                            if (colDef && (colDef.field === 'optionCode' || colDef.field === '옵션코드')) {
                                return {
                                    found: true,
                                    field: colDef.field,
                                    editable: !!colDef.editable,
                                    cellEditor: colDef.cellEditor || null,
                                    headerName: colDef.headerName || '',
                                    raw: JSON.stringify(colDef).substring(0, 300)
                                };
                            }
                        }
                    } catch(e) {}
                }
                return {found: false};
            }""")
            print(f"  [디버그] 옵션코드 컬럼 정보: {col_editable}")

            # ── 셀 구조 디버그 ──
            cell_debug = page.evaluate("""() => {
                // 첫 번째 AG row에서 옵션코드 셀 구조 확인
                const row = document.querySelector('.ag-row[row-index="0"]');
                if (!row) return {error: 'no ag-row[0]'};
                const cells = row.querySelectorAll('.ag-cell');
                const result = [];
                cells.forEach(c => {
                    result.push({
                        colId: c.getAttribute('col-id'),
                        text: c.innerText?.trim().substring(0, 50),
                        innerHTML: c.innerHTML?.substring(0, 200),
                        hasInput: !!c.querySelector('input'),
                        hasTextarea: !!c.querySelector('textarea'),
                        classes: c.className?.substring(0, 100)
                    });
                });
                return result;
            }""")
            print(f"  [디버그] 첫 번째 row 셀 구조:")
            for cd in (cell_debug if isinstance(cell_debug, list) else []):
                print(f"    col={cd.get('colId')} text='{cd.get('text','')}' hasInput={cd.get('hasInput')} html={cd.get('innerHTML','')[:100]}")

            # 옵션코드 입력
            filled = 0
            for row in rows:
                item = row.get("itemTitle", "")
                option = row.get("option", "")
                current = row.get("optionCode", "").strip()
                idx = row.get("rowIndex", 0)

                expected = lookup_option_code(item, option)

                if not expected:
                    print(f"  [{idx}] 매핑 없음: {item[:40]}")
                    continue

                if current == expected:
                    print(f"  [{idx}] 이미 정확: {expected}")
                    continue

                print(f"  [{idx}] 입력 시도: {expected} (상품: {item[:40]})")

                if dry_run:
                    filled += 1
                    continue

                ok = False

                # 스크롤
                page.evaluate(f"""() => {{
                    const apis = [
                        window.gridOptions && window.gridOptions.api,
                        window.gridOptions_orders && window.gridOptions_orders.api,
                    ];
                    for (const api of apis) {{
                        if (!api) continue;
                        try {{ api.ensureColumnVisible('optionCode'); }} catch(e) {{}}
                        try {{ api.ensureColumnVisible('옵션코드'); }} catch(e) {{}}
                        try {{ api.ensureIndexVisible({idx}); }} catch(e) {{}}
                    }}
                }}""")
                page.wait_for_timeout(500)

                # 옵션코드 셀 찾기
                cell = (
                    page.query_selector(f".ag-row[row-index='{idx}'] .ag-cell[col-id='optionCode']")
                    or page.query_selector(f".ag-row[row-index='{idx}'] .ag-cell[col-id='옵션코드']")
                )

                if not cell:
                    print(f"    WARNING: 옵션코드 셀 못 찾음 (row-index={idx})")
                    # 모든 셀의 col-id 나열
                    all_col_ids = page.evaluate(f"""() => {{
                        const row = document.querySelector('.ag-row[row-index="{idx}"]');
                        if (!row) return ['row not found'];
                        return Array.from(row.querySelectorAll('.ag-cell')).map(c => c.getAttribute('col-id'));
                    }}""")
                    print(f"    가용 col-id: {all_col_ids}")
                    filled += 1
                    continue

                print(f"    셀 찾음: col-id={cell.get_attribute('col-id')}, text='{cell.inner_text()[:30]}'")
                print(f"    셀 innerHTML: {cell.evaluate('el => el.innerHTML')[:200]}")

                # ── 방법 1: 셀 안에 이미 input이 있는지 확인 ──
                inner_input = cell.query_selector("input")
                if inner_input:
                    print(f"    방법1: 셀 내 input 발견")
                    _retry(lambda: (inner_input.click(), None)[-1], label="method1 click")
                    page.wait_for_timeout(300)
                    _retry(lambda: (inner_input.fill(""), inner_input.type(expected), inner_input.press("Tab")),
                           label="method1 fill+type")
                    page.wait_for_timeout(500)
                    ok = True
                    _ss(page, f"09a_method1_input_{idx}")
                    print(f"    입력 완료 (셀 내 input)")

                # ── 방법 2: 더블클릭 → 편집 모드 ──
                if not ok:
                    _retry(lambda: cell.dblclick(), label="method2 dblclick")
                    page.wait_for_timeout(1000)
                    _ss(page, f"09b_after_dblclick_{idx}")

                    # 편집 input/textarea 찾기 (셀 내부 + 전역)
                    edit_input = (
                        cell.query_selector("input")
                        or cell.query_selector("textarea")
                        or page.query_selector(".ag-cell-editor input")
                        or page.query_selector(".ag-cell-editor textarea")
                        or page.query_selector(".ag-popup-editor input")
                        or page.query_selector(".ag-cell-edit-input")
                        or page.query_selector("input.ag-input-field-input")
                    )

                    if edit_input:
                        tag = edit_input.evaluate("el => el.tagName + '.' + el.className")
                        print(f"    방법2: 편집 input 발견 ({tag})")
                        _retry(lambda: (edit_input.fill(""),), label="method2 fill")
                        page.wait_for_timeout(200)
                        _retry(lambda: (edit_input.type(expected),), label="method2 type")
                        page.wait_for_timeout(200)
                        _ss(page, f"09c_after_type_{idx}")
                        _retry(lambda: edit_input.press("Tab"), label="method2 Tab")
                        page.wait_for_timeout(500)

                        # ★ commit 보강: 다른 셀을 명시적으로 클릭해 cellValueChanged 트리거
                        # AG Grid 마지막 행은 Tab만으로 commit 안 되는 경우가 있음 (서버 저장 누락)
                        try:
                            other_idx = (idx + 1) % max(len(rows), 1)
                            target_row = idx if other_idx == idx else other_idx
                            other_cell = page.query_selector(
                                f".ag-row[row-index='{target_row}'] .ag-cell[col-id='idx']"
                            )
                            if other_cell:
                                other_cell.click()
                                page.wait_for_timeout(800)
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(300)
                        except Exception:
                            pass

                        ok = True
                        print(f"    입력 완료 (더블클릭 → input → commit 보강)")
                    else:
                        print(f"    방법2: 더블클릭 후 input 없음")

                # ── 방법 3: 클릭 → F2 (AG Grid 표준 편집 키) ──
                if not ok:
                    _retry(lambda: cell.click(), label="method3 click")
                    page.wait_for_timeout(300)
                    _retry(lambda: page.keyboard.press("F2"), label="method3 F2")
                    page.wait_for_timeout(1000)
                    _ss(page, f"09d_after_F2_{idx}")

                    edit_input = (
                        cell.query_selector("input")
                        or cell.query_selector("textarea")
                        or page.query_selector(".ag-cell-editor input")
                        or page.query_selector(".ag-popup-editor input")
                    )

                    if edit_input:
                        tag = edit_input.evaluate("el => el.tagName + '.' + el.className")
                        print(f"    방법3: F2 후 input 발견 ({tag})")
                        _retry(lambda: (edit_input.fill(""), edit_input.type(expected), edit_input.press("Tab")),
                               label="method3 fill+type")
                        page.wait_for_timeout(500)
                        ok = True
                        print(f"    입력 완료 (F2 → input)")
                    else:
                        print(f"    방법3: F2 후 input 없음")

                # ── 방법 4: 클릭 → 직접 키보드 타이핑 ──
                if not ok:
                    _retry(lambda: cell.click(), label="method4 click")
                    page.wait_for_timeout(300)
                    # 기존 값 지우기
                    _retry(lambda: page.keyboard.press("Delete"), label="method4 Delete")
                    page.wait_for_timeout(200)
                    # 직접 타이핑
                    _retry(lambda: page.keyboard.type(expected), label="method4 type")
                    page.wait_for_timeout(300)
                    _retry(lambda: page.keyboard.press("Tab"), label="method4 Tab")
                    page.wait_for_timeout(500)
                    _ss(page, f"09e_after_direct_type_{idx}")
                    # 값 확인
                    new_val = cell.inner_text().strip()
                    print(f"    방법4: 직접 타이핑 후 셀 값: '{new_val}'")
                    if expected in new_val:
                        ok = True
                        print(f"    입력 완료 (직접 타이핑)")

                # ── 방법 5: AG Grid startEditingCell API ──
                if not ok:
                    col_field = col_editable.get("field", "optionCode") if isinstance(col_editable, dict) else "optionCode"
                    edit_started = page.evaluate(f"""() => {{
                        const apis = [
                            window.gridOptions && window.gridOptions.api,
                            window.gridOptions_orders && window.gridOptions_orders.api,
                        ];
                        for (const api of apis) {{
                            if (!api) continue;
                            try {{
                                api.startEditingCell({{
                                    rowIndex: {idx},
                                    colKey: '{col_field}'
                                }});
                                return true;
                            }} catch(e) {{
                                return 'error: ' + e.message;
                            }}
                        }}
                        return false;
                    }}""")
                    print(f"    방법5: startEditingCell 결과: {edit_started}")

                    if edit_started is True:
                        page.wait_for_timeout(500)
                        _ss(page, f"09f_after_startEdit_{idx}")
                        edit_input = (
                            cell.query_selector("input")
                            or page.query_selector(".ag-cell-editor input")
                            or page.query_selector(".ag-popup-editor input")
                        )
                        if edit_input:
                            _retry(lambda: (edit_input.fill(""), edit_input.type(expected), edit_input.press("Tab")),
                                   label="method5 fill+type")
                            page.wait_for_timeout(500)
                            ok = True
                            print(f"    입력 완료 (startEditingCell API)")

                # ── 입력 후 값 검증 ──
                if ok:
                    page.wait_for_timeout(300)
                    verify_val = page.evaluate(f"""() => {{
                        // DOM에서 값 확인
                        const cell = document.querySelector('.ag-row[row-index="{idx}"] .ag-cell[col-id="optionCode"]')
                            || document.querySelector('.ag-row[row-index="{idx}"] .ag-cell[col-id="옵션코드"]');
                        const domVal = cell ? (cell.querySelector('input') ? cell.querySelector('input').value : cell.innerText.trim()) : null;

                        // AG Grid 데이터에서 값 확인
                        const apis = [
                            window.gridOptions && window.gridOptions.api,
                            window.gridOptions_orders && window.gridOptions_orders.api,
                        ];
                        let gridVal = null;
                        for (const api of apis) {{
                            if (!api) continue;
                            api.forEachNode(node => {{
                                if (node.rowIndex === {idx} && node.data) {{
                                    gridVal = node.data.optionCode || node.data['옵션코드'] || null;
                                }}
                            }});
                        }}
                        return {{domVal: domVal, gridVal: gridVal}};
                    }}""")
                    print(f"    검증: DOM값='{verify_val.get('domVal')}' Grid값='{verify_val.get('gridVal')}'")
                    if verify_val.get('domVal') != expected and verify_val.get('gridVal') != expected:
                        print(f"    ⚠ 값이 일치하지 않음! 입력 실패일 수 있음")
                        ok = False

                if not ok:
                    print(f"    ✗ 모든 방법 실패. 수동 입력 필요")

                filled += 1

            _ss(page, "09_options_filled")

            print(f"\n  옵션코드 입력: {filled}건")

            if dry_run:
                print("\n[DRY-RUN] 조회 완료. 배송접수는 하지 않았습니다.")
                _ss(page, "10_dryrun_done")
                return

            # ── Step 8: 전체 선택 + 배송접수(국제) ──
            print("\n[8] 전체 선택 + 배송접수(국제)...")

            # 전체 체크박스 (헤더의 체크박스)
            select_all = (
                page.query_selector(".ag-header-select-all input[type=checkbox]")
                or page.query_selector(".ag-header-cell input[type=checkbox]")
                or page.query_selector("th input[type=checkbox]")
            )
            if not select_all:
                # 더 넓게 — 첫 번째 헤더 체크박스
                checkboxes = page.query_selector_all("input[type=checkbox]")
                if checkboxes:
                    select_all = checkboxes[0]

            if select_all:
                # 이미 체크되어 있으면 해제 후 다시 체크
                is_checked = select_all.is_checked()
                if not is_checked:
                    _retry(lambda: select_all.click(), label="click select-all")
                    page.wait_for_timeout(1000)
                print("  전체 선택 완료")
            else:
                print("  WARNING: 전체 선택 체크박스를 찾지 못함")

            _ss(page, "10_all_selected")

            # 배송접수(국제) 버튼
            ship_btn = (
                page.query_selector("button:has-text('배송접수(국제)')")
                or page.query_selector("a:has-text('배송접수(국제)')")
                or page.query_selector("input[value*='배송접수(국제)']")
            )
            if not ship_btn:
                all_btns = page.query_selector_all("button, a, input[type=button], input[type=submit]")
                for btn in all_btns:
                    txt = (btn.inner_text() or "").strip() if btn.evaluate("el => el.tagName") != "INPUT" else (btn.get_attribute("value") or "")
                    if "배송접수" in txt and "국제" in txt:
                        ship_btn = btn
                        break

            # ── Step 7.5: 옵션코드 저장 버튼 확인 ──
            print("\n[7.5] 옵션코드 저장 버튼 확인...")
            save_btn = (
                page.query_selector("button:has-text('저장')")
                or page.query_selector("a:has-text('저장')")
                or page.query_selector("input[value*='저장']")
                or page.query_selector("button:has-text('Save')")
            )
            if save_btn:
                print("  저장 버튼 발견! 클릭...")
                _retry(lambda: save_btn.click(), label="click save")
                page.wait_for_timeout(3000)
                _ss(page, "09g_after_save")
                print("  저장 완료")
            else:
                # 페이지 내 모든 버튼 텍스트 출력
                all_btns = page.query_selector_all("button, a.btn, input[type=button], input[type=submit]")
                btn_texts = []
                for btn in all_btns:
                    try:
                        txt = (btn.inner_text() or "").strip()
                        if not txt:
                            txt = btn.get_attribute("value") or ""
                        if txt:
                            btn_texts.append(txt[:30])
                    except Exception:
                        pass
                print(f"  저장 버튼 없음. 페이지 버튼 목록: {btn_texts}")

            ship_outcome = "unknown"  # success / fail / unknown
            if ship_btn:
                # confirm/alert 다이얼로그 자동 수락 + 메시지 캡처
                dialog_msgs = []
                def handle_dialog(dialog):
                    try:
                        dialog_msgs.append(dialog.message)
                        dialog.accept()
                    except Exception:
                        pass
                page.on("dialog", handle_dialog)

                _retry(lambda: ship_btn.click(), label="click ship intl")
                # ★ 15초 대기 — 두 번째 "Success!" alert 확보
                page.wait_for_timeout(15000)
                _ss(page, "11_shipped")
                print("  배송접수(국제) 클릭 완료!")

                # 다이얼로그 메시지 검사 (Success / 성공 / 배송관리 키워드)
                success_alert = False
                if dialog_msgs:
                    for msg in dialog_msgs:
                        print(f"  [다이얼로그] {msg}")
                        if any(kw in msg for kw in ["Success", "성공", "배송관리"]):
                            success_alert = True

                # URL 검증 — getOrders 그대로면 실패, /shipping2 또는 packing 으로 이동했으면 성공
                current_url = page.url
                print(f"  현재 URL: {current_url}")
                url_ok = (
                    ("/shipping2" in current_url and "getOrders" not in current_url)
                    or "packing" in current_url.lower()
                )

                # 페이지 텍스트에서 실패/성공 키워드
                page_text = page.evaluate("""() => document.body.innerText.substring(0, 3000)""")
                page_has_error = any(
                    kw in page_text for kw in ["실패하", "오류", "에러", "ERROR"]
                )
                for line in page_text.split('\n'):
                    line = line.strip()
                    if line and any(kw in line for kw in ['실패', '성공', '오류', 'error', 'fail', 'success', '완료']):
                        print(f"  [페이지] {line[:150]}")

                # 종합 판정
                if success_alert and url_ok:
                    ship_outcome = "success"
                    print("  ✓ 배송접수 성공 (Success alert + URL 이동)")
                elif page_has_error:
                    ship_outcome = "fail"
                    print("  ✗ 배송접수 실패 (페이지 에러 메시지 감지)")
                    _ss(page, "11_ship_failed")
                elif success_alert and not url_ok:
                    ship_outcome = "fail"
                    print(f"  ✗ Success alert는 떴으나 URL 미이동 — 실패 가능성 높음: {current_url}")
                    _ss(page, "11_ship_failed_no_url")
                elif url_ok and not success_alert:
                    # URL은 이동했으나 alert 못 잡음 — 보수적으로 success
                    ship_outcome = "success"
                    print("  ⚠ Success alert 미감지지만 URL 이동 확인 → 성공으로 간주")
                else:
                    ship_outcome = "fail"
                    print(f"  ✗ 배송접수 실패 의심 (alert/URL 모두 신호 없음)")
                    _ss(page, "11_ship_failed_no_signal")
            else:
                print("  ERROR: 배송접수(국제) 버튼을 찾지 못함")
                _ss(page, "11_no_ship_btn")
                ship_outcome = "fail"

            # 결과 확인
            _ss(page, "12_final")
            print(f"\n{'=' * 40}")
            print(f"  처리 완료!")
            print(f"  주문: {len(rows)}건")
            print(f"  옵션코드 입력: {filled}건")
            print(f"  배송접수: {ship_outcome}")
            print(f"{'=' * 40}")

            # 배송접수 실패면 exit code 3 — 상위 파이프라인이 Auditor를 강제 실행하게 함
            if ship_outcome == "fail":
                return 3
            return 0

        except PWTimeout as e:
            print(f"\nERROR 타임아웃: {e}")
            _ss(page, "error_timeout")
            return 1
        except Exception as e:
            print(f"\nERROR: {e}")
            _ss(page, "error")
            import traceback
            traceback.print_exc()
            return 1
        finally:
            print("\n30초 후 브라우저 종료...")
            page.wait_for_timeout(30000)
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KSE OMS Rakuten 주문수집 + 옵션코드 + 배송접수")
    parser.add_argument("--dry-run", action="store_true", help="조회만 (배송접수 안 함)")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시")
    parser.add_argument("--expected-count", type=int, default=0,
                        help="상위 파이프라인이 전달한 기대 주문 건수 (0건 시 exit 2)")
    args = parser.parse_args()
    exit_code = run(dry_run=args.dry_run, headless=not args.headed,
                    expected_count=args.expected_count)
    sys.exit(exit_code if isinstance(exit_code, int) else 0)
