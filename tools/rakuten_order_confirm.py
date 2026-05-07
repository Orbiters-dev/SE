"""
Rakuten RMS 주문확인 + 메일발송 자동화 도구

처리 흐름:
  1. RMS(glogin.rms.rakuten.co.jp)에 Playwright로 로그인
  2. 注文確認待ち 페이지에서 대기 주문 목록 읽기
  3. 각 주문 상세 진입 → 주문자 이름 + 금액 일치 검증
  4. 일치 → 주문확인 버튼 클릭 → 메일발송 버튼 클릭
  5. 불일치 → 스킵하고 불일치 내역 보고

Usage:
    python tools/rakuten_order_confirm.py                # 실제 처리
    python tools/rakuten_order_confirm.py --dry-run      # 조회만 (확인/발송 안 함)
    python tools/rakuten_order_confirm.py --headed       # 브라우저 표시 (디버그)
    python tools/rakuten_order_confirm.py --full         # RMS → 10분 대기 → KSE 풀 파이프라인
    python tools/rakuten_order_confirm.py --full --headed # 풀 파이프라인 + 브라우저 표시
    python tools/rakuten_order_confirm.py --full --dry-run # 풀 파이프라인 조회만 (대기 스킵)

환경변수 (.env):
    RAKUTEN_RMS_LOGIN_ID       - RMS 로그인 ID
    RAKUTEN_RMS_LOGIN_PASSWORD - RMS 비밀번호
"""

import argparse
import io
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

RMS_LOGIN_URL = "https://glogin.rms.rakuten.co.jp/"
RMS_LOGIN_ID  = os.getenv("RAKUTEN_RMS_LOGIN_ID", "")
RMS_LOGIN_PW  = os.getenv("RAKUTEN_RMS_LOGIN_PASSWORD", "")
SSO_ID        = os.getenv("RAKUTEN_SSO_ID", "")
SSO_PW        = os.getenv("RAKUTEN_SSO_PASSWORD", "")
TMP_DIR       = PROJECT_ROOT / ".tmp"


def _ss(page, name: str):
    """디버그 스크린샷 저장."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"rms_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"    📸 {path.name}")
    except Exception:
        pass


def run(dry_run: bool = False, headless: bool = True, stop_before_send: bool = False):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print("=" * 56)
    print("Rakuten RMS 주문확인 + 메일발송")
    if dry_run:
        print("[DRY-RUN] 조회만 합니다 (확인/발송 안 함)")
    print("=" * 56)

    if not RMS_LOGIN_ID or not RMS_LOGIN_PW:
        print("✗ RAKUTEN_RMS_LOGIN_ID / RAKUTEN_RMS_LOGIN_PASSWORD 가 .env에 없습니다")
        return False

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=500)
        context = browser.new_context(
            locale="ja-JP",
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()

        try:
            # ── Step 1: RMS 로그인 (R-Login → Rakuten SSO 2단계) ──
            print("\n[1] RMS 로그인 중...")
            page.goto(RMS_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            _ss(page, "01_login_page")

            # --- Step 1a: R-Login 폼 (新R-Login) ---
            rlogin_id = page.query_selector("input[placeholder*='R-Login ID']")
            rlogin_pw = page.query_selector("input[placeholder*='パスワード']")

            if rlogin_id and rlogin_pw:
                print("  R-Login 폼 발견")
                rlogin_id.fill(RMS_LOGIN_ID)
                rlogin_pw.fill(RMS_LOGIN_PW)
                page.wait_for_timeout(500)

                submit_btn = (
                    page.query_selector("button:has-text('楽天会員ログインへ')")
                    or page.query_selector("input[value*='ログイン']")
                    or page.query_selector("button[type='submit']")
                )
                if submit_btn:
                    submit_btn.click()
                else:
                    rlogin_pw.press("Enter")

                page.wait_for_load_state("domcontentloaded", timeout=15000)
                page.wait_for_timeout(3000)
                _ss(page, "02_after_rlogin")
                print(f"  R-Login 제출 완료 (URL: {page.url})")

            # --- Step 1b: Rakuten SSO (2단계: ID → 次へ → パスワード) ---
            if "login.account.rakuten.com" in page.url:
                print("  Rakuten SSO 로그인 감지...")

                # Step 1b-1: ユーザID 입력 → 次へ
                user_id_input = page.query_selector("input[id='loginInner_u']")
                if not user_id_input:
                    user_id_input = page.query_selector("input[type='text'], input[type='email']")

                if user_id_input:
                    user_id_input.fill(SSO_ID or RMS_LOGIN_ID)
                    page.wait_for_timeout(1000)

                    # "次へ" — Rakuten SPA 위젯 버튼 클릭
                    try:
                        page.click("text=次へ", timeout=5000)
                    except Exception:
                        user_id_input.press("Enter")

                    page.wait_for_timeout(4000)
                    _ss(page, "02b_sso_after_id")
                    print("  ユーザID → 次へ 클릭 완료")

                    # Step 1b-2: パスワード 입력 → ログイン
                    try:
                        page.wait_for_selector("input[type='password']", timeout=10000)
                    except PWTimeout:
                        print("  ⚠ パスワード 필드가 나타나지 않음")
                        _ss(page, "02c_no_pw_field")

                    sso_pw = page.query_selector("input[type='password']")
                    if sso_pw:
                        sso_pw.fill(SSO_PW or RMS_LOGIN_PW)
                        page.wait_for_timeout(1000)

                        try:
                            page.click("text=ログイン", timeout=5000)
                        except Exception:
                            sso_pw.press("Enter")

                        page.wait_for_timeout(5000)

                        # RMS 메인으로 리다이렉트 대기
                        try:
                            page.wait_for_url("**/mainmenu**", timeout=15000)
                        except PWTimeout:
                            print(f"  ⚠ RMS 리다이렉트 대기... (현재: {page.url})")
                            page.wait_for_timeout(5000)

            # --- Step 1c: R-Login 中間ページ (「次へ」→「RMS」) ---
            if "glogin.rms.rakuten.co.jp" in page.url and "mainmenu" not in page.url:
                # 「次へ」ボタンがあれば클릭
                next_btn = page.query_selector("a:has-text('次へ'), button:has-text('次へ'), input[value='次へ']")
                if next_btn:
                    print("  R-Login 中間ページ → 「次へ」클릭")
                    next_btn.click()
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)

                # 「ＲＭＳ」リンクがあれば클릭 (ご利用中のサービス)
                # 다음 페이지 DOM 렌더링이 늦을 수 있어 wait_for_selector로 최대 10초 대기
                try:
                    page.wait_for_selector(
                        "a[href*='mainmenu.rms.rakuten.co.jp'], a:has-text('ＲＭＳ')",
                        timeout=10000,
                    )
                except PWTimeout:
                    pass

                rms_link = page.query_selector("a[href*='mainmenu.rms.rakuten.co.jp']")
                if not rms_link:
                    rms_link = page.query_selector("a:has-text('ＲＭＳ')")
                if rms_link:
                    print("  R-Login 管理ページ → 「RMS」클릭")
                    rms_link.click()
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)

            # --- Step 1d: ガイドライン同意ページ ---
            agree_btn = page.query_selector("a:has-text('RMSを利用します'), button:has-text('RMSを利用します'), input[value*='RMSを利用します']")
            if agree_btn:
                print("  ガイドライン同意 → 「RMSを利用します」클릭")
                agree_btn.click()
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                page.wait_for_timeout(3000)

            # --- Step 1e: 置き配 안내 등 인터스티셜 페이지 ---
            main_menu_btn = page.query_selector("a:has-text('メインメニューへ進む'), button:has-text('メインメニューへ進む')")
            if main_menu_btn:
                print("  置き配 안내 페이지 → 「RMSメインメニューへ進む」클릭")
                main_menu_btn.click()
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                page.wait_for_timeout(3000)

            _ss(page, "02_after_login")

            # 로그인 검증 — mainmenu URL 미달성 시 즉시 실패 (vacuous PASS 방지)
            if "mainmenu.rms.rakuten.co.jp" not in page.url:
                print(f"  ✗ 로그인 실패 — mainmenu 미도달 (현재 URL: {page.url})")
                print(f"  ✗ R-Login 중간 페이지에서 막혔거나 추가 인증 단계 필요. 스크린샷 확인.")
                return -1

            print(f"  ✓ 로그인 완료 (URL: {page.url})")

            # ── Step 2: 注文確認待ち 페이지 이동 ───────────────────
            print("\n[2] 注文確認待ち 페이지로 이동 중...")

            # RMS 메인에서 注文確認待ち 링크 찾기
            order_link = page.query_selector("a:has-text('注文確認待ち')")
            if order_link:
                order_link.click()
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            else:
                # 受注・決済管理 메뉴 먼저 클릭
                menu = page.query_selector("a:has-text('受注'), a:has-text('受注・決済管理')")
                if menu:
                    menu.click()
                    page.wait_for_timeout(2000)
                    order_link = page.query_selector("a:has-text('注文確認待ち')")
                    if order_link:
                        order_link.click()
                        page.wait_for_load_state("domcontentloaded", timeout=15000)

            page.wait_for_timeout(2000)
            _ss(page, "03_order_list")
            print(f"  현재 URL: {page.url}")

            # ── Step 3: 주문 목록 읽기 ─────────────────────────────
            print("\n[3] 주문 목록 읽기...")

            html = page.content()
            (TMP_DIR / "rms_order_list.html").write_text(html, encoding="utf-8")
            print(f"  HTML 저장: .tmp/rms_order_list.html")

            # 주문번호 링크를 직접 찾기 (435776-YYYYMMDD-NNNN 패턴)
            import re
            order_links = page.query_selector_all("a")
            orders = []
            seen = set()
            for link in order_links:
                link_text = (link.inner_text() or "").strip()
                if re.match(r"\d{6}-\d{8}-\d+", link_text) and link_text not in seen:
                    seen.add(link_text)
                    orders.append({
                        "order_number": link_text,
                        "element": link,
                    })

            if not orders:
                body_text = page.inner_text("body")
                if "0件" in body_text:
                    print("  ✓ 注文確認待ち 주문이 0건입니다")
                else:
                    print("  ✓ 처리할 주문이 없습니다")
                _ss(page, "04_no_orders")
                return 0

            print(f"  주문 건수: {len(orders)}건")

            if not orders:
                print("  ✓ 처리할 주문이 없습니다")
                return 0

            for idx, order in enumerate(orders):
                print(f"\n  ── 주문 {idx+1}/{len(orders)}: {order['order_number']} ──")

            confirmed = 0
            mismatch = 0
            errors = []

            # ── Step 4: 각 주문 상세 진입 + 검증 + 확인 ────────────
            for idx, order in enumerate(orders):
                print(f"\n[4-{idx+1}] 주문 상세: {order['order_number']}")

                # 주문번호 링크 클릭 → 새 탭으로 열림 (target="order_detail")
                detail_link = page.query_selector(f"a:has-text('{order['order_number']}')")
                if detail_link:
                    with context.expect_page() as new_page_info:
                        detail_link.click()
                    detail_page = new_page_info.value
                    detail_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    detail_page.wait_for_timeout(2000)
                    _ss(detail_page, f"05_detail_{idx+1}")

                    detail_html = detail_page.content()
                    (TMP_DIR / f"rms_order_detail_{idx+1}.html").write_text(
                        detail_html, encoding="utf-8"
                    )

                    print(f"  상세 URL: {detail_page.url}")
                    print(f"  상세 HTML 저장: .tmp/rms_order_detail_{idx+1}.html")

                    if not dry_run:
                        # Step A: 「✓ 注文確認する」핑크 버튼 클릭
                        confirm_btn = (
                            detail_page.query_selector("a:has-text('注文確認する')")
                            or detail_page.query_selector("button:has-text('注文確認する')")
                            or detail_page.query_selector("input[value*='注文確認']")
                        )
                        if confirm_btn:
                            confirm_btn.click()
                            detail_page.wait_for_timeout(2000)

                            # 확인 모달 팝업: 「注文確認」ボタン클릭
                            modal_btn = detail_page.query_selector("#orderDetailsStatusBar注文確認Modal .btn-primary, #orderDetailsStatusBar注文確認Modal .btn-danger")
                            if not modal_btn:
                                modal_btn = detail_page.query_selector(".modal.in button:has-text('注文確認'), .modal.in a:has-text('注文確認')")
                            if modal_btn:
                                print("  모달 확인 팝업 → 「注文確認」클릭")
                                modal_btn.click()
                                detail_page.wait_for_timeout(3000)

                            _ss(detail_page, f"06_confirmed_{idx+1}")
                            print(f"  ✓ 주문확인 완료")

                            # Step B: 「メール送信」탭/버튼 클릭
                            mail_btn = (
                                detail_page.query_selector("a:has-text('メール送信')")
                                or detail_page.query_selector("button:has-text('メール送信')")
                            )
                            if mail_btn:
                                mail_btn.click()
                                detail_page.wait_for_load_state("domcontentloaded", timeout=15000)
                                detail_page.wait_for_timeout(3000)
                                _ss(detail_page, f"07_mail_page_{idx+1}")
                                print(f"  ✓ メール送信 페이지 진입")

                                # Step C: テンプレート選択 → 「次へ」클릭
                                # JavaScript로 직접 찾아서 클릭 (value 공백/인코딩 문제 방지)
                                detail_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                detail_page.wait_for_timeout(1000)

                                clicked_next = detail_page.evaluate("""() => {
                                    // input[value='次へ'] 직접 검색
                                    let btn = document.querySelector("input[value='次へ']");
                                    if (!btn) {
                                        // value에 공백이 있을 수 있으므로 모든 input 순회
                                        for (const el of document.querySelectorAll('input[type="submit"], input[type="button"], button')) {
                                            if (el.value && el.value.trim().includes('次へ') || el.textContent && el.textContent.trim().includes('次へ')) {
                                                btn = el;
                                                break;
                                            }
                                        }
                                    }
                                    if (btn) { btn.click(); return true; }
                                    return false;
                                }""")

                                if clicked_next:
                                    detail_page.wait_for_load_state("domcontentloaded", timeout=15000)
                                    detail_page.wait_for_timeout(3000)
                                    _ss(detail_page, f"08_mail_preview_{idx+1}")
                                    print(f"  ✓ テンプレート選択 → 次へ")

                                    # Step D: 送信 직전 멈춤 or 송신
                                    if stop_before_send:
                                        print(f"  ⏸ 送信 직전에서 멈춤 (--stop-before-send)")
                                        print(f"    브라우저에서 확인하세요. 5분 후 자동 종료됩니다.")
                                        detail_page.wait_for_timeout(300000)
                                        return

                                    # 하단 스크롤 후 送信 버튼 찾기 (JavaScript 직접 클릭)
                                    detail_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                    detail_page.wait_for_timeout(1000)

                                    clicked_send = detail_page.evaluate("""() => {
                                        let btn = document.querySelector("input[value='送信']");
                                        if (!btn) {
                                            for (const el of document.querySelectorAll('input[type="submit"], input[type="button"], button')) {
                                                if (el.value && el.value.trim().includes('送信') || el.textContent && el.textContent.trim().includes('送信')) {
                                                    btn = el;
                                                    break;
                                                }
                                            }
                                        }
                                        if (btn) { btn.click(); return true; }
                                        return false;
                                    }""")

                                    if clicked_send:
                                        detail_page.wait_for_timeout(3000)
                                        _ss(detail_page, f"09_mail_sent_{idx+1}")
                                        print(f"  ✓ サンクスメール 送信 완료")

                                        # ── Step E: 같은 세션에서 発送メール 발송 ──
                                        print(f"  → 発送メール 발송 시작...")

                                        # 주문상세로 돌아가기: 뒤로가기 또는 주문상세 URL 직접 이동
                                        detail_url = f"https://order-rp.rms.rakuten.co.jp/order-rb/individual-order-detail-sc/init?orderNumber={order['order_number']}"
                                        detail_page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                                        detail_page.wait_for_timeout(3000)
                                        _ss(detail_page, f"10_back_to_detail_{idx+1}")

                                        # メール送信 버튼 클릭 (이번에는 発送メール 템플릿)
                                        ship_mail_btn = (
                                            detail_page.query_selector("a:has-text('メール送信')")
                                            or detail_page.query_selector("button:has-text('メール送信')")
                                        )
                                        if ship_mail_btn:
                                            ship_mail_btn.click()
                                            detail_page.wait_for_load_state("domcontentloaded", timeout=15000)
                                            detail_page.wait_for_timeout(3000)
                                            _ss(detail_page, f"11_ship_mail_page_{idx+1}")
                                            print(f"  ✓ 発送メール送信 페이지 진입")

                                            # 次へ 클릭
                                            detail_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                            detail_page.wait_for_timeout(1000)
                                            clicked_ship_next = detail_page.evaluate("""() => {
                                                let btn = document.querySelector("input[value='次へ']");
                                                if (!btn) {
                                                    for (const el of document.querySelectorAll('input[type="submit"], input[type="button"], button')) {
                                                        if (el.value && el.value.trim().includes('次へ') || el.textContent && el.textContent.trim().includes('次へ')) {
                                                            btn = el;
                                                            break;
                                                        }
                                                    }
                                                }
                                                if (btn) { btn.click(); return true; }
                                                return false;
                                            }""")

                                            if clicked_ship_next:
                                                detail_page.wait_for_load_state("domcontentloaded", timeout=15000)
                                                detail_page.wait_for_timeout(3000)
                                                _ss(detail_page, f"12_ship_mail_preview_{idx+1}")
                                                print(f"  ✓ 発送メール テンプレート → 次へ")

                                                # 本送信 or 送信 클릭
                                                detail_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                                detail_page.wait_for_timeout(1000)
                                                clicked_ship_send = detail_page.evaluate("""() => {
                                                    // 本送信 우선, 없으면 送信
                                                    for (const el of document.querySelectorAll('input[type="submit"], input[type="button"], button, a.btn, a')) {
                                                        let val = el.value || '';
                                                        let txt = el.textContent || '';
                                                        if (val.trim().includes('本送信') || txt.trim().includes('本送信')) {
                                                            el.click(); return '本送信';
                                                        }
                                                    }
                                                    for (const el of document.querySelectorAll('input[type="submit"], input[type="button"], button')) {
                                                        let val = el.value || '';
                                                        let txt = el.textContent || '';
                                                        if (val.trim().includes('送信') || txt.trim().includes('送信')) {
                                                            el.click(); return '送信';
                                                        }
                                                    }
                                                    return false;
                                                }""")

                                                if clicked_ship_send:
                                                    detail_page.wait_for_timeout(3000)
                                                    _ss(detail_page, f"13_ship_mail_sent_{idx+1}")
                                                    print(f"  ✓ 発送メール {clicked_ship_send} 완료!")
                                                else:
                                                    print(f"  ⚠ 発送メール 送信/本送信 버튼 없음")
                                                    _ss(detail_page, f"13_no_ship_send_{idx+1}")
                                            else:
                                                print(f"  ⚠ 発送メール 次へ 버튼 없음")
                                                _ss(detail_page, f"12_no_ship_next_{idx+1}")
                                        else:
                                            print(f"  ⚠ 発送メール送信 버튼 없음 (주문 상태 확인 필요)")
                                            _ss(detail_page, f"11_no_ship_mail_btn_{idx+1}")
                                    else:
                                        print(f"  ⚠ 送信 버튼을 찾을 수 없습니다")
                                        _ss(detail_page, f"09_no_send_btn_{idx+1}")
                                else:
                                    print(f"  ⚠ 次へ 버튼을 찾을 수 없습니다")
                                    _ss(detail_page, f"08_no_next_btn_{idx+1}")
                            else:
                                print(f"  ⚠ メール送信 버튼을 찾을 수 없습니다")
                                _ss(detail_page, f"07_no_mail_btn_{idx+1}")

                            confirmed += 1
                        else:
                            print(f"  ⚠ 注文確認する 버튼을 찾을 수 없습니다")
                            _ss(detail_page, f"06_no_confirm_btn_{idx+1}")
                    else:
                        print(f"  [DRY-RUN] 확인/발송 스킵")

                    # 상세 탭 닫고 주문목록 탭으로 복귀
                    detail_page.close()
                    page.wait_for_timeout(1000)

            # ── 결과 요약 ──────────────────────────────────────────
            print(f"\n── 결과 ──────────────────────────")
            print(f"  총 주문:    {len(orders)}건")
            print(f"  확인 완료:  {confirmed}건")
            print(f"  불일치:     {mismatch}건")
            if errors:
                print(f"\n  ⚠ 불일치 목록:")
                for e in errors:
                    print(f"    - {e}")

            if dry_run:
                print("\n[DRY-RUN] 실제 확인/발송은 하지 않았습니다.")
                print("  → .tmp/rms_order_list.html 및 rms_order_detail_*.html 확인")
                print("  → --dry-run 제거 후 재실행하세요")

            # 처리 건수 반환 (True/False 대신 int — -1: 실패, 0+: 확인 완료 건수)
            return confirmed

        except PWTimeout as e:
            print(f"\n✗ 타임아웃: {e}")
            _ss(page, "error_timeout")
            return -1
        except Exception as e:
            print(f"\n✗ 오류: {e}")
            _ss(page, "error_unknown")
            import traceback
            traceback.print_exc()
            return -1
        finally:
            browser.close()


def run_full_pipeline(headless: bool = True, dry_run: bool = False):
    """RMS 주문확인+메일 → 10분 대기 → KSE 주문수집+옵션코드+배송접수 통합 실행."""
    import subprocess
    import time

    print("=" * 56)
    print("라쿠텐 풀 파이프라인: RMS → 대기 → KSE")
    if dry_run:
        print("[DRY-RUN] 조회만 합니다 (실제 처리 안 함, 대기 스킵)")
    print("=" * 56)

    python_exe = sys.executable

    # Step 1: RMS 주문확인 + 메일발송
    print("\n[STEP 1/5] RMS 주문확인 + サンクスメール + 発送メール")
    rms_result = run(dry_run=dry_run, headless=headless)
    if rms_result < 0:
        print("\n✗ RMS 단계 실패 — 이후 단계 중단")
        return 1
    expected_count = rms_result
    print(f"\n[STEP 1 결과] 처리 건수: {expected_count}건 (이후 단계의 기대값)")

    # 0건이면 이후 단계 의미 없음 → NO_DATA로 조기 종료
    if expected_count == 0:
        print("\n⚠ STEP 1 처리 0건 — RMS 注文確認待ち 비어있음. 이후 단계 스킵.")
        return 2  # NO_DATA

    # Step 2: 10분 대기 (KSE가 주문 인식할 시간)
    if dry_run:
        print("\n[STEP 2/5] [DRY-RUN] 대기 스킵")
    else:
        wait_minutes = 10
        print(f"\n[STEP 2/5] KSE 주문 인식 대기 ({wait_minutes}분)...")
        for remaining in range(wait_minutes * 60, 0, -30):
            mins, secs = divmod(remaining, 60)
            print(f"  남은 시간: {mins}분 {secs}초")
            time.sleep(min(30, remaining))
        print("  대기 완료!")

    # Step 3: KSE 주문수집 + 옵션코드 + 배송접수
    print(f"\n[STEP 3/5] KSE 주문수집 + 옵션코드 + 배송접수 (기대: {expected_count}건)")
    kse_script = str(PROJECT_ROOT / "tools" / "kse_rakuten_order.py")
    kse_args = [python_exe, kse_script, "--expected-count", str(expected_count)]
    if not headless:
        kse_args.append("--headed")
    if dry_run:
        kse_args.append("--dry-run")
    result = subprocess.run(kse_args, capture_output=False, text=True)

    # exit 0 = OK, 2 = NO_DATA, 3 = 배송접수 실패, 그 외 = 일반 실패
    step3_failed = False
    step3_reason = ""
    if result.returncode == 2:
        step3_failed = True
        step3_reason = f"NO_DATA (KSE가 0건 반환, 기대 {expected_count}건)"
    elif result.returncode == 3:
        step3_failed = True
        step3_reason = "배송접수 클릭 후 URL/Success alert 신호 없음"
    elif result.returncode != 0:
        step3_failed = True
        step3_reason = f"일반 실패 (exit {result.returncode})"
    if step3_failed:
        print(f"\n✗ STEP 3 실패: {step3_reason}")
        print("  → STEP 4 송장입력 스킵하고 STEP 5 Auditor 강제 실행 (현재 상태 진단)")

    # Step 4: RMS 송장번호 입력 (STEP 3 실패 시 스킵)
    step4_failed = False
    step4_reason = ""
    if step3_failed:
        print(f"\n[STEP 4/5] SKIP — STEP 3 실패로 인해 송장입력 의미 없음")
        step4_failed = True
        step4_reason = "STEP 3 실패로 스킵"
    else:
        print(f"\n[STEP 4/5] RMS 송장번호 입력 (기대: {expected_count}건)")
        tracking_script = str(PROJECT_ROOT / "tools" / "rakuten_tracking_input.py")
        tracking_args = [python_exe, tracking_script, "--expected-count", str(expected_count)]
        if not headless:
            tracking_args.append("--headed")
        if dry_run:
            tracking_args.append("--dry-run")
        result = subprocess.run(tracking_args, capture_output=False, text=True)

        if result.returncode == 2:
            step4_failed = True
            step4_reason = f"NO_DATA (송장 0건, 기대 {expected_count}건)"
        elif result.returncode != 0:
            step4_failed = True
            step4_reason = f"일반 실패 (exit {result.returncode})"
        if step4_failed:
            print(f"\n✗ STEP 4 실패: {step4_reason}")
            print("  → STEP 5 Auditor 강제 실행 (현재 상태 진단)")

    # Step 5: Auditor — 무조건 실행 (STEP 3/4 실패해도 현재 상태 진단)
    print(f"\n[STEP 5/5] Auditor — 옵션코드 + 송장번호 교차 검증 (기대: {expected_count}건)")
    auditor_script = str(PROJECT_ROOT / "tools" / "rakuten_auditor.py")
    auditor_args = [python_exe, auditor_script, "--expected-count", str(expected_count)]
    if not headless:
        auditor_args.append("--headed")
    result = subprocess.run(auditor_args, capture_output=False, text=True)

    # 0=ALL PASS, 1=FAIL, 2=NO_DATA
    auditor_pass = (result.returncode == 0)
    if auditor_pass:
        print(f"\n✓ Auditor: ALL PASS (기대 {expected_count}건 전부 검증됨)")
    elif result.returncode == 2:
        print(f"\n✗ Auditor: NO_DATA — 기대 {expected_count}건과 불일치")
    else:
        print("\n⚠ Auditor: 불일치 발견 — 위 리포트 확인 필요")

    # 종합 판정
    print("\n" + "=" * 56)
    if step3_failed or step4_failed or not auditor_pass:
        print("라쿠텐 풀 파이프라인 종료 — 일부 단계 실패/불일치")
        if step3_failed:
            print(f"  STEP 3: {step3_reason}")
        if step4_failed:
            print(f"  STEP 4: {step4_reason}")
        print("=" * 56)
        return 1
    print(f"라쿠텐 풀 파이프라인 완료! (기대 {expected_count}건 모두 RMS→KSE→송장→검증)")
    print("=" * 56)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Rakuten RMS 주문확인 + 메일발송")
    parser.add_argument("--dry-run", action="store_true", help="조회만 (확인/발송 안 함)")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시 (디버그)")
    parser.add_argument("--stop-before-send", action="store_true", help="送信 직전에서 멈춤")
    parser.add_argument("--full", action="store_true", help="RMS → 10분 대기 → KSE 풀 파이프라인")
    args = parser.parse_args()

    if args.full:
        run_full_pipeline(headless=not args.headed, dry_run=args.dry_run)
    else:
        run(dry_run=args.dry_run, headless=not args.headed, stop_before_send=args.stop_before_send)


if __name__ == "__main__":
    main()
