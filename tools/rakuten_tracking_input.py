"""
Rakuten RMS 송장번호(トラッキング番号) 입력 자동화

흐름:
  1. KSE OMS 팩킹리스트에서 주문별 송장번호 읽기
  2. Rakuten RMS 発送待ち 주문 상세에 진입
  3. 配送会社: 日本郵便 선택
  4. 発送日: 今日 클릭
  5. お荷物伝票番号: 송장번호 입력
  6. 저장

Usage:
    python tools/rakuten_tracking_input.py --headed           # 브라우저 표시
    python tools/rakuten_tracking_input.py --headed --dry-run # 조회만
"""

import argparse
import io
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# KSE OMS
KSEOMS_LOGIN_URL = "https://kseoms.com/login"
KSEOMS_SHIP_URL  = "https://kseoms.com/shipping2"
KSE_LOGIN_ID     = os.getenv("KSEOMS_LOGIN_ID", "")
KSE_LOGIN_PW     = os.getenv("KSEOMS_LOGIN_PASSWORD", "")

# Rakuten RMS
RMS_LOGIN_URL    = "https://glogin.rms.rakuten.co.jp/"
RMS_LOGIN_ID     = os.getenv("RAKUTEN_RMS_LOGIN_ID", "")
RMS_LOGIN_PW     = os.getenv("RAKUTEN_RMS_LOGIN_PASSWORD", "")
SSO_ID           = os.getenv("RAKUTEN_SSO_ID", "")
SSO_PW           = os.getenv("RAKUTEN_SSO_PASSWORD", "")
SHIP_WAIT_URL    = "https://order-rp.rms.rakuten.co.jp/order-rb/order-list-sc/init?&SEARCH_MODE=1&ORDER_PROGRESS=300"

TMP_DIR = PROJECT_ROOT / ".tmp"


def _ss(page, name: str):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"tracking_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"    ss: {path.name}")
    except Exception:
        pass


# ─────────────────────────────────────────────────
#  Phase 1: KSE 팩킹리스트에서 송장번호 수집
# ─────────────────────────────────────────────────

def read_kse_tracking(pw, headless: bool) -> list[dict]:
    """KSE 팩킹리스트에서 {orderNo, trackingNo} 목록을 반환한다."""
    print("\n" + "=" * 56)
    print("Phase 1: KSE 팩킹리스트 → 송장번호 읽기")
    print("=" * 56)

    browser = pw.chromium.launch(headless=headless, slow_mo=300)
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    results = []

    try:
        # ── 로그인 ──
        print("\n[K1] KSE OMS 로그인...")
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
            print("  ERROR: 로그인 폼 없음")
            return results

        id_input.fill(KSE_LOGIN_ID)
        pw_input.fill(KSE_LOGIN_PW)

        submit = (
            page.query_selector("button[type=submit]")
            or page.query_selector("input[type=submit]")
            or page.query_selector("button:has-text('로그인')")
        )
        if submit:
            submit.click()
        else:
            pw_input.press("Enter")

        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        print(f"  로그인 완료 (URL: {page.url})")

        # ── 팩킹리스트 이동 ──
        print("\n[K2] 팩킹리스트로 이동...")
        page.goto(KSEOMS_SHIP_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # 검색 버튼 클릭
        try:
            search_btn = page.wait_for_selector(
                "button:has-text('검 색'), button:has-text('검색')", timeout=5000
            )
            search_btn.click()
            page.wait_for_timeout(3000)
        except Exception:
            pass

        # AG Grid 로드 대기
        page.wait_for_selector(".ag-row", timeout=15000)
        _ss(page, "kse_01_packing_list")

        # ── AG Grid 컬럼 키 확인 ──
        col_keys = page.evaluate("""() => {
            const api = window.gridOptions_orders && window.gridOptions_orders.api;
            if (!api) return [];
            let keys = [];
            api.forEachNode(node => {
                if (node.data && keys.length === 0) {
                    keys = Object.keys(node.data);
                }
            });
            return keys;
        }""")
        print(f"  [디버그] 컬럼 키: {col_keys}")

        # ── 주문번호 + 송장번호 읽기 ──
        print("\n[K3] 주문번호 + 송장번호 읽기...")
        rows = page.evaluate("""() => {
            const api = window.gridOptions_orders && window.gridOptions_orders.api;
            if (!api) return [];
            const result = [];
            api.forEachNode(node => {
                if (!node.data) return;
                const d = node.data;
                result.push({
                    rowIndex: node.rowIndex,
                    // packNo = RMS 주문번호 형식 (435776-20260313-XXXXXXXXXX)
                    packNo: d.packNo || '',
                    // orderNo = 라쿠텐 내부 주문번호 (숫자)
                    orderNo: d.orderNo || d.orderId || '',
                    // 송장번호(도착지) = LocalTrackingNo (143516... JP Post 번호)
                    trackingNo: d.LocalTrackingNo || d.localTrackingNo || '',
                    // KSE 내부 트래킹 (K번호, 참조용)
                    kseTracking: d.TrackingNo || '',
                    // 마켓 구분
                    market: d.market || '',
                });
            });
            return result;
        }""")

        if not rows:
            print("  팩킹리스트 비어있음")
            return results

        print(f"  전체 행: {len(rows)}건")

        # 첫 행의 전체 키 출력 (디버깅)
        if rows:
            print(f"  [디버그] 첫 행 키: {rows[0].get('allKeys', '')}")
            print(f"  [디버그] 첫 행 데이터: {rows[0].get('allData', '')[:300]}")

        # Rakuten 주문만 필터 + 송장번호 있는 것만
        for r in rows:
            pack_no = r.get("packNo", "").strip()
            order_no = r.get("orderNo", "").strip()
            tracking = r.get("trackingNo", "").strip()
            market = r.get("market", "").lower()

            # Rakuten 주문 판별
            is_rakuten = "rakuten" in market

            if tracking and is_rakuten and pack_no:
                results.append({
                    "packNo": pack_no,       # RMS 매칭용
                    "orderNo": order_no,     # 참조용
                    "trackingNo": tracking,
                })
                print(f"  [{r.get('rowIndex')}] pack: {pack_no} → 송장: {tracking}")
            elif tracking and not is_rakuten:
                print(f"  [{r.get('rowIndex')}] (Rakuten 아님) 마켓: {market}")
            elif is_rakuten and not tracking:
                print(f"  [{r.get('rowIndex')}] (송장번호 없음) pack: {pack_no}")

        # ── packNo별 송장번호 그룹핑 + 검증 ──
        # 같은 packNo에 여러 아이템 → 송장번호가 같아야 정상
        from collections import defaultdict
        pack_tracking_groups = defaultdict(set)
        for r in results:
            pack_tracking_groups[r["packNo"]].add(r["trackingNo"])

        # 충돌 검사: 같은 주문인데 송장번호가 다르면 경고
        conflicts = {k: v for k, v in pack_tracking_groups.items() if len(v) > 1}
        if conflicts:
            print("\n  주의: 같은 주문에 다른 송장번호가 있습니다!")
            for pack, trackings in conflicts.items():
                print(f"    {pack} → {trackings}")
            print("    → 첫 번째 송장번호를 사용합니다")

        # packNo 기준 1건으로 통합 (중복 제거)
        unique = {}
        for r in results:
            if r["packNo"] not in unique:
                unique[r["packNo"]] = r
        results = list(unique.values())

        print(f"\n  Rakuten 송장 건수: {len(results)}건 (packNo 기준 중복 제거)")
        for r in results:
            item_count = sum(
                1 for row in rows
                if row.get("packNo", "").strip() == r["packNo"]
            )
            print(f"    {r['packNo']} → {r['trackingNo']} (아이템 {item_count}개)")

    except Exception as e:
        print(f"\nERROR (KSE): {e}")
        _ss(page, "kse_error")
        import traceback
        traceback.print_exc()
    finally:
        browser.close()

    return results


# ─────────────────────────────────────────────────
#  Phase 2: Rakuten RMS에 송장번호 입력
# ─────────────────────────────────────────────────

def rms_login(page, context):
    """RMS 로그인 (R-Login → SSO 2단계) — rakuten_ship_mail.py와 동일"""
    from playwright.sync_api import TimeoutError as PWTimeout

    page.goto(RMS_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # R-Login 폼
    rlogin_id = page.query_selector("input[placeholder*='R-Login ID']")
    rlogin_pw = page.query_selector("input[placeholder*='パスワード']")

    if rlogin_id and rlogin_pw:
        rlogin_id.fill(RMS_LOGIN_ID)
        rlogin_pw.fill(RMS_LOGIN_PW)
        page.wait_for_timeout(500)
        try:
            page.click("button:has-text('楽天会員ログインへ'), input[value*='ログイン'], button[type='submit']", timeout=5000)
        except Exception:
            rlogin_pw.press("Enter")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)
        print(f"  R-Login 제출 완료")

    # SSO
    if "login.account.rakuten.com" in page.url:
        print("  Rakuten SSO 로그인...")
        uid = (
            page.query_selector("input[id='loginInner_u']")
            or page.query_selector("input[type='text'], input[type='email']")
        )
        if uid:
            uid.fill(SSO_ID or RMS_LOGIN_ID)
            page.wait_for_timeout(1000)
            try:
                page.click("text=次へ", timeout=5000)
            except Exception:
                uid.press("Enter")
            page.wait_for_timeout(4000)

            try:
                page.wait_for_selector("input[type='password']", timeout=10000)
            except PWTimeout:
                pass
            pw_fld = page.query_selector("input[type='password']")
            if pw_fld:
                pw_fld.fill(SSO_PW or RMS_LOGIN_PW)
                page.wait_for_timeout(1000)
                try:
                    page.click("text=ログイン", timeout=5000)
                except Exception:
                    pw_fld.press("Enter")
                page.wait_for_timeout(5000)
                try:
                    page.wait_for_url("**/mainmenu**", timeout=15000)
                except PWTimeout:
                    page.wait_for_timeout(5000)

    # R-Login 中間ページ
    if "glogin.rms.rakuten.co.jp" in page.url and "mainmenu" not in page.url:
        next_btn = page.query_selector("a:has-text('次へ'), button:has-text('次へ'), input[value='次へ']")
        if next_btn:
            next_btn.click()
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(3000)
        rms_link = (
            page.query_selector("a[href*='mainmenu.rms.rakuten.co.jp']")
            or page.query_selector("a:has-text('ＲＭＳ')")
        )
        if rms_link:
            rms_link.click()
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(3000)

    # ガイドライン同意
    agree = page.query_selector("a:has-text('RMSを利用します'), button:has-text('RMSを利用します')")
    if agree:
        agree.click()
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

    # 置き配 안내 등 인터스티셜 페이지 → 「RMSメインメニューへ進む」클릭
    main_menu_btn = page.query_selector("a:has-text('メインメニューへ進む'), button:has-text('メインメニューへ進む')")
    if main_menu_btn:
        print("  置き配 안내 페이지 → 「RMSメインメニューへ進む」클릭")
        main_menu_btn.click()
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

    print(f"  로그인 완료 (URL: {page.url})")


def input_tracking_to_rms(pw, tracking_data: list[dict], dry_run: bool, headless: bool):
    """Rakuten RMS 発送待ち 주문에 송장번호를 입력한다."""
    print("\n" + "=" * 56)
    print("Phase 2: Rakuten RMS → 송장번호 입력")
    if dry_run:
        print("[DRY-RUN] 입력하지 않습니다")
    print("=" * 56)

    if not tracking_data:
        print("  입력할 송장번호 없음. 종료.")
        return

    browser = pw.chromium.launch(headless=headless, slow_mo=500)
    context = browser.new_context(locale="ja-JP", viewport={"width": 1400, "height": 900})
    page = context.new_page()

    try:
        # ── 로그인 ──
        print("\n[R1] RMS 로그인 중...")
        rms_login(page, context)
        _ss(page, "rms_01_logged_in")

        # ── 発送待ち 목록 ──
        print("\n[R2] 発送待ち 주문목록 진입...")
        page.goto(SHIP_WAIT_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # お知らせ 팝업 닫기
        confirm_notice = page.query_selector("button:has-text('確認した'), input[value='確認した']")
        if confirm_notice:
            confirm_notice.click()
            page.wait_for_timeout(2000)

        _ss(page, "rms_02_ship_wait_list")

        # ── 주문번호 읽기 ──
        print("\n[R3] 주문 목록 읽기...")
        all_links = page.query_selector_all("a")
        rms_orders = []
        seen = set()
        for link in all_links:
            text = (link.inner_text() or "").strip()
            if re.match(r"\d{6}-\d{8}-\d+", text) and text not in seen:
                seen.add(text)
                rms_orders.append(text)

        if not rms_orders:
            print("  発送待ち 주문 없음")
            _ss(page, "rms_03_no_orders")
            return

        print(f"  RMS 発送待ち: {len(rms_orders)}건")
        for o in rms_orders:
            print(f"    {o}")

        # ── KSE 송장 데이터와 매칭 ──
        # KSE packNo = RMS 주문번호 (동일 형식)
        tracking_map = {}
        for td in tracking_data:
            tracking_map[td["packNo"]] = td["trackingNo"]

        # 매칭 시도
        matched = []
        for rms_order in rms_orders:
            # packNo와 정확히 일치
            if rms_order in tracking_map:
                matched.append({"orderNo": rms_order, "trackingNo": tracking_map[rms_order]})
                continue
            # 부분 매칭 (혹시 형식 차이가 있을 경우)
            for pack_no, tracking in tracking_map.items():
                if pack_no in rms_order or rms_order in pack_no:
                    matched.append({"orderNo": rms_order, "trackingNo": tracking})
                    break

        print(f"\n  매칭 결과: {len(matched)}/{len(rms_orders)}건")
        for m in matched:
            print(f"    {m['orderNo']} → {m['trackingNo']}")

        unmatched = [o for o in rms_orders if o not in [m["orderNo"] for m in matched]]
        if unmatched:
            print(f"  매칭 안 됨: {unmatched}")

        if dry_run:
            print("\n[DRY-RUN] 조회 완료.")
            return

        # ── 각 주문에 송장번호 입력 ──
        filled = 0
        for idx, m in enumerate(matched):
            order_no = m["orderNo"]
            tracking = m["trackingNo"]
            print(f"\n[R4-{idx+1}] {order_no} → {tracking}")

            # 주문번호 클릭 → 새 탭
            detail_link = page.query_selector(f"a:has-text('{order_no}')")
            if not detail_link:
                print("  주문 링크 없음, 스킵")
                continue

            with context.expect_page() as new_page_info:
                detail_link.click()
            dp = new_page_info.value
            dp.wait_for_load_state("domcontentloaded", timeout=15000)
            dp.wait_for_timeout(3000)
            _ss(dp, f"rms_04_detail_{idx+1}")
            print("  상세 페이지 진입")

            # ── 配送会社 드롭다운 → 日本郵便 선택 ──
            print("  配送会社 선택: 日本郵便...")
            carrier_selected = False

            # select 요소에서 日本郵便 찾기
            selects = dp.query_selector_all("select")
            for sel in selects:
                has_jp_post = sel.evaluate("""el => {
                    return Array.from(el.options).some(o =>
                        o.text.includes('日本郵便') || o.value.includes('日本郵便')
                    )
                }""")
                if has_jp_post:
                    sel.evaluate("""el => {
                        for (const o of el.options) {
                            if (o.text.includes('日本郵便')) {
                                el.value = o.value;
                                el.dispatchEvent(new Event('change', {bubbles: true}));
                                return true;
                            }
                        }
                        return false;
                    }""")
                    carrier_selected = True
                    print("    日本郵便 선택 완료")
                    break

            if not carrier_selected:
                # 모든 select 내용 덤프
                for i, sel in enumerate(selects):
                    opts = sel.evaluate("""el =>
                        Array.from(el.options).map(o => o.text).join(', ')
                    """)
                    print(f"    select[{i}]: {opts[:200]}")
                print("    WARNING: 日本郵便 선택 실패")

            dp.wait_for_timeout(1000)

            # ── 発送日 → 今日 클릭 ──
            print("  発送日: 今日 클릭...")
            today_clicked = False

            # 今日 버튼/링크 찾기
            today_btn = (
                dp.query_selector("a:has-text('今日')")
                or dp.query_selector("button:has-text('今日')")
                or dp.query_selector("input[value='今日']")
                or dp.query_selector("span:has-text('今日')")
            )
            if today_btn:
                today_btn.click()
                today_clicked = True
                print("    今日 클릭 완료")
            else:
                # 넓은 범위 탐색
                all_elements = dp.query_selector_all("a, button, span, input")
                for el in all_elements:
                    text = ""
                    try:
                        tag = el.evaluate("el => el.tagName")
                        if tag == "INPUT":
                            text = el.get_attribute("value") or ""
                        else:
                            text = (el.inner_text() or "").strip()
                    except Exception:
                        continue
                    if text == "今日":
                        el.click()
                        today_clicked = True
                        print("    今日 클릭 완료 (넓은 범위)")
                        break

            if not today_clicked:
                print("    WARNING: 今日 버튼 못 찾음")

            dp.wait_for_timeout(1000)

            # ── お荷物伝票番号 입력 ──
            print(f"  お荷物伝票番号: {tracking}...")
            tracking_entered = False

            # 伝票番号 입력 필드 — RMS 실제 name: parcelNumber
            tracking_input = (
                dp.query_selector("input[name='parcelNumber']")
                or dp.query_selector("input[id*='parcel-number']")
                or dp.query_selector("input[placeholder='入力してください']")
            )

            if tracking_input:
                try:
                    tracking_input.click()
                    dp.wait_for_timeout(300)
                    tracking_input.fill("")
                    tracking_input.type(tracking)
                    dp.wait_for_timeout(500)
                    tracking_entered = True
                    print(f"    입력 완료: {tracking}")
                except Exception as e:
                    print(f"    입력 오류: {e}")
            else:
                print("    WARNING: 伝票番号 입력 필드 못 찾음")
                # 페이지 내 모든 input 덤프
                inputs_debug = dp.evaluate("""() => {
                    const inputs = document.querySelectorAll('input');
                    return Array.from(inputs).map(inp => ({
                        name: inp.name || '',
                        type: inp.type || '',
                        placeholder: inp.placeholder || '',
                        value: inp.value || '',
                        id: inp.id || '',
                    })).filter(i => i.type !== 'hidden');
                }""")
                for inp in (inputs_debug or [])[:20]:
                    print(f"    input: name={inp.get('name')} type={inp.get('type')} placeholder={inp.get('placeholder')} id={inp.get('id')}")

            _ss(dp, f"rms_05_filled_{idx+1}")

            # ── 「✔入力内容を反映」빨간 버튼 클릭 ──
            if carrier_selected and tracking_entered:
                print("  入力内容を反映 버튼 클릭...")

                # 페이지 상단으로 스크롤 (버튼이 상단에 위치)
                dp.evaluate("window.scrollTo(0, 0)")
                dp.wait_for_timeout(2000)

                # 방법 1: Playwright selector
                reflect_btn = None
                for selector in [
                    "button:has-text('入力内容')",
                    "a:has-text('入力内容')",
                    "div:has-text('入力内容を反映')",
                    "[class*='btn']:has-text('入力内容')",
                ]:
                    try:
                        reflect_btn = dp.wait_for_selector(
                            selector, timeout=5000, state="visible"
                        )
                        if reflect_btn:
                            break
                    except Exception:
                        continue

                # 방법 2: JS로 텍스트 기반 검색 (모든 요소)
                if not reflect_btn:
                    print("    셀렉터 실패, JS로 검색...")
                    reflect_btn = dp.evaluate_handle("""() => {
                        const all = document.querySelectorAll('*');
                        for (const el of all) {
                            const text = (el.innerText || el.textContent || '').trim();
                            if (text.includes('入力内容') && text.includes('反映')
                                && el.offsetParent !== null
                                && el.children.length < 5) {
                                return el;
                            }
                        }
                        return null;
                    }""")
                    reflect_btn = reflect_btn.as_element() if reflect_btn else None

                if reflect_btn:
                    reflect_btn.click()
                    dp.wait_for_timeout(5000)
                    _ss(dp, f"rms_06_reflected_{idx+1}")
                    print(f"  入力内容を反映 완료!")
                    filled += 1
                else:
                    print("  WARNING: 入力内容を反映 버튼 못 찾음")

            dp.close()
            page.wait_for_timeout(1000)

        print(f"\n{'=' * 40}")
        print(f"  RMS 발送待ち: {len(rms_orders)}건")
        print(f"  KSE 매칭:     {len(matched)}건")
        print(f"  송장 입력:    {filled}건")
        print(f"{'=' * 40}")

    except Exception as e:
        print(f"\nERROR (RMS): {e}")
        _ss(page, "rms_error")
        import traceback
        traceback.print_exc()
    finally:
        print("\n30초 후 브라우저 종료...")
        page.wait_for_timeout(30000)
        browser.close()


# ─────────────────────────────────────────────────
#  메인 실행
# ─────────────────────────────────────────────────

def run(dry_run=False, headless=True, expected_count=0):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw_ctx:
        # Phase 1: KSE에서 송장번호 읽기
        tracking_data = read_kse_tracking(pw_ctx, headless)

        if not tracking_data:
            print("\n송장번호가 있는 Rakuten 주문이 없습니다. 종료.")
            if expected_count > 0:
                print(f"  ✗ 기대 {expected_count}건 vs 실제 0건 — NO_DATA")
            return 2  # NO_DATA

        if expected_count > 0 and len(tracking_data) < expected_count:
            print(f"\n⚠ 기대 {expected_count}건 vs 실제 {len(tracking_data)}건 — 누락 가능성")

        # Phase 2: RMS에 송장번호 입력
        input_tracking_to_rms(pw_ctx, tracking_data, dry_run, headless)
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rakuten RMS 송장번호 입력 자동화")
    parser.add_argument("--dry-run", action="store_true", help="조회만 (입력 안 함)")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시")
    parser.add_argument("--expected-count", type=int, default=0,
                        help="상위 파이프라인이 전달한 기대 건수 (0건 시 exit 2)")
    args = parser.parse_args()
    exit_code = run(dry_run=args.dry_run, headless=not args.headed,
                    expected_count=args.expected_count)
    sys.exit(exit_code if isinstance(exit_code, int) else 0)
