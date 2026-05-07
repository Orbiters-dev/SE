"""
Rakuten RMS 発送待ち → 発送メール送信 자동화

흐름:
  1. RMS 로그인
  2. 発送待ち 주문목록 직접 진입 (ORDER_PROGRESS=300)
  3. 주문번호 클릭 → 상세 페이지
  4. メール送信 버튼 → 次へ → 本送信

Usage:
    python tools/rakuten_ship_mail.py                # headless
    python tools/rakuten_ship_mail.py --headed       # 브라우저 표시
    python tools/rakuten_ship_mail.py --dry-run      # 조회만
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

RMS_LOGIN_URL = "https://glogin.rms.rakuten.co.jp/"
RMS_LOGIN_ID  = os.getenv("RAKUTEN_RMS_LOGIN_ID", "")
RMS_LOGIN_PW  = os.getenv("RAKUTEN_RMS_LOGIN_PASSWORD", "")
SSO_ID        = os.getenv("RAKUTEN_SSO_ID", "")
SSO_PW        = os.getenv("RAKUTEN_SSO_PASSWORD", "")
TMP_DIR       = PROJECT_ROOT / ".tmp"

# 発送待ち 주문목록 URL (ORDER_PROGRESS=300)
SHIP_WAIT_URL = "https://order-rp.rms.rakuten.co.jp/order-rb/order-list-sc/init?&SEARCH_MODE=1&ORDER_PROGRESS=300"


def ss(page, name):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(TMP_DIR / f"rms_{name}.png"), full_page=True)
        print(f"    ss: {name}.png")
    except Exception:
        pass


def rms_login(page, context):
    """RMS 로그인 (R-Login → SSO 2단계)"""
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
        uid = page.query_selector("input[id='loginInner_u']") or page.query_selector("input[type='text'], input[type='email']")
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
            pw_input = page.query_selector("input[type='password']")
            if pw_input:
                pw_input.fill(SSO_PW or RMS_LOGIN_PW)
                page.wait_for_timeout(1000)
                try:
                    page.click("text=ログイン", timeout=5000)
                except Exception:
                    pw_input.press("Enter")
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
        rms_link = page.query_selector("a[href*='mainmenu.rms.rakuten.co.jp']") or page.query_selector("a:has-text('ＲＭＳ')")
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

    print(f"  ✓ 로그인 완료 (URL: {page.url})")


def run(dry_run=False, headless=True):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print("=" * 56)
    print("Rakuten RMS 発送待ち → 発送メール送信")
    if dry_run:
        print("[DRY-RUN] 조회만 합니다")
    print("=" * 56)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=500)
        context = browser.new_context(locale="ja-JP", viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:
            # ── Step 1: 로그인 ──
            print("\n[1] RMS 로그인 중...")
            rms_login(page, context)
            ss(page, "ship_01_logged_in")

            # ── Step 2: 発送待ち 목록 직접 진입 ──
            print("\n[2] 発送待ち 주문목록 진입...")
            page.goto(SHIP_WAIT_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # お知らせ 확인 팝업 닫기
            confirm_notice = page.query_selector("button:has-text('確認した'), input[value='確認した']")
            if confirm_notice:
                confirm_notice.click()
                page.wait_for_timeout(2000)

            ss(page, "ship_02_list")
            print(f"  URL: {page.url}")

            # ── Step 3: 주문번호 읽기 ──
            print("\n[3] 주문 목록 읽기...")
            all_links = page.query_selector_all("a")
            orders = []
            seen = set()
            for link in all_links:
                text = (link.inner_text() or "").strip()
                if re.match(r"\d{6}-\d{8}-\d+", text) and text not in seen:
                    seen.add(text)
                    orders.append(text)

            if not orders:
                print("  発送待ち 주문 없음")
                ss(page, "ship_03_no_orders")
                return

            print(f"  주문 건수: {len(orders)}건")
            for i, o in enumerate(orders):
                print(f"    {i+1}. {o}")

            if dry_run:
                print("\n[DRY-RUN] 조회 완료.")
                return

            # ── Step 4: 각 주문 → 주문번호 클릭 → メール送信 → 次へ → 本送信 ──
            sent = 0
            for idx, order_num in enumerate(orders):
                print(f"\n[4-{idx+1}] {order_num}")

                # 주문번호 클릭 → 새 탭 열림
                detail_link = page.query_selector(f"a:has-text('{order_num}')")
                if not detail_link:
                    print("  ⚠ 주문 링크 없음")
                    continue

                with context.expect_page() as new_page_info:
                    detail_link.click()
                dp = new_page_info.value
                dp.wait_for_load_state("domcontentloaded", timeout=15000)
                dp.wait_for_timeout(3000)
                ss(dp, f"ship_04_detail_{idx+1}")
                print(f"  상세 페이지 진입")

                # メール送信 버튼 (주문번호 바로 밑)
                mail_btn = (
                    dp.query_selector("button:has-text('メール送信')")
                    or dp.query_selector("a:has-text('メール送信')")
                    or dp.query_selector("input[value*='メール送信']")
                )
                if not mail_btn:
                    print("  ⚠ メール送信 버튼 없음")
                    ss(dp, f"ship_05_no_mail_{idx+1}")
                    dp.close()
                    page.wait_for_timeout(1000)
                    continue

                mail_btn.click()
                dp.wait_for_load_state("domcontentloaded", timeout=15000)
                dp.wait_for_timeout(3000)
                ss(dp, f"ship_05_mail_{idx+1}")
                print("  メール送信 클릭 완료")

                # 次へ 버튼 (テンプレート 기본 선택 유지)
                next_btn = (
                    dp.query_selector("input[value='次へ']")
                    or dp.query_selector("button:has-text('次へ')")
                    or dp.query_selector("a:has-text('次へ')")
                )
                if not next_btn:
                    # broader search
                    all_inputs = dp.query_selector_all("input[type='submit'], input[type='button'], button")
                    for inp in all_inputs:
                        val = inp.get_attribute("value") or ""
                        txt = (inp.inner_text() or "").strip() if inp.evaluate("el => el.tagName") == "BUTTON" else ""
                        if "次へ" in val or "次へ" in txt:
                            next_btn = inp
                            break
                if not next_btn:
                    # last resort: click by text locator
                    try:
                        dp.locator("text=次へ").click()
                        dp.wait_for_load_state("domcontentloaded", timeout=15000)
                        dp.wait_for_timeout(3000)
                        ss(dp, f"ship_06_preview_{idx+1}")
                        print("  次へ 클릭 완료 (locator)")
                        next_btn = True  # flag to continue
                    except Exception:
                        print("  ⚠ 次へ 버튼 없음")
                        ss(dp, f"ship_06_no_next_{idx+1}")
                        dp.close()
                        page.wait_for_timeout(1000)
                        continue

                if next_btn is not True:
                    next_btn.click()
                dp.wait_for_load_state("domcontentloaded", timeout=15000)
                dp.wait_for_timeout(3000)
                ss(dp, f"ship_06_preview_{idx+1}")
                print("  次へ 클릭 완료")

                # 本送信 버튼 (빨간 버튼, 우하단)
                send_btn = (
                    dp.query_selector("button:has-text('本送信')")
                    or dp.query_selector("input[value='本送信']")
                    or dp.query_selector("a:has-text('本送信')")
                )
                if not send_btn:
                    # broader: 모든 input/button에서 本送信 찾기
                    all_inputs = dp.query_selector_all("input[type='submit'], input[type='button'], button, a.btn, a")
                    for inp in all_inputs:
                        val = inp.get_attribute("value") or ""
                        txt = (inp.inner_text() or "").strip()
                        if "本送信" in val or "本送信" in txt:
                            send_btn = inp
                            break
                if not send_btn:
                    # last resort: locator
                    try:
                        dp.locator("text=本送信").click()
                        dp.wait_for_timeout(3000)
                        ss(dp, f"ship_07_sent_{idx+1}")
                        print(f"  ✓ 本送信 완료! 메일 발송됨! (locator)")
                        sent += 1
                        dp.close()
                        page.wait_for_timeout(1000)
                        continue
                    except Exception:
                        print("  ⚠ 本送信 버튼 없음")
                        ss(dp, f"ship_07_no_send_{idx+1}")
                        dp.close()
                        page.wait_for_timeout(1000)
                        continue

                send_btn.scroll_into_view_if_needed()
                dp.wait_for_timeout(1000)
                send_btn.click()
                dp.wait_for_timeout(3000)
                ss(dp, f"ship_07_sent_{idx+1}")
                print(f"  ✓ 本送信 완료! 메일 발송됨!")
                sent += 1

                dp.close()
                page.wait_for_timeout(1000)

            print(f"\n{'=' * 40}")
            print(f"  총 주문: {len(orders)}건")
            print(f"  메일 발송: {sent}건")
            print(f"{'=' * 40}")

        except PWTimeout as e:
            print(f"\n✗ 타임아웃: {e}")
            ss(page, "ship_error_timeout")
        except Exception as e:
            print(f"\n✗ 오류: {e}")
            ss(page, "ship_error")
            import traceback
            traceback.print_exc()
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rakuten RMS 発送待ち 메일발송")
    parser.add_argument("--dry-run", action="store_true", help="조회만")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시")
    args = parser.parse_args()
    run(dry_run=args.dry_run, headless=not args.headed)
