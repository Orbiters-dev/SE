"""
楽天処理中 (ORDER_PROGRESS=200) 칸 확인 스크립트.
누락된 주문이 어떤 사유로 처리중에 머물러 있는지 확인.

사용법:
  python tools/rakuten_check_processing.py --order 435776-20260428-0161824590 --headed
"""
import argparse
import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

RMS_LOGIN_ID  = os.getenv("RAKUTEN_RMS_LOGIN_ID", "")
RMS_LOGIN_PW  = os.getenv("RAKUTEN_RMS_LOGIN_PASSWORD", "")
SSO_ID        = os.getenv("RAKUTEN_SSO_ID", "")
SSO_PW        = os.getenv("RAKUTEN_SSO_PASSWORD", "")
RMS_LOGIN_URL = "https://glogin.rms.rakuten.co.jp/"

TMP_DIR = ROOT / ".tmp"
TMP_DIR.mkdir(exist_ok=True)


def _ss(page, name):
    try:
        page.screenshot(path=str(TMP_DIR / f"check_processing_{name}.png"))
    except Exception:
        pass


def login_rms(page):
    from playwright.sync_api import TimeoutError as PWTimeout

    page.goto(RMS_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    rlogin_id = page.query_selector("input[placeholder*='R-Login ID']")
    rlogin_pw = page.query_selector("input[placeholder*='パスワード']")
    if rlogin_id and rlogin_pw:
        rlogin_id.fill(RMS_LOGIN_ID)
        rlogin_pw.fill(RMS_LOGIN_PW)
        page.wait_for_timeout(500)
        submit = (page.query_selector("button:has-text('楽天会員ログインへ')")
                  or page.query_selector("button[type='submit']"))
        if submit:
            submit.click()
        else:
            rlogin_pw.press("Enter")
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

    if "login.account.rakuten.com" in page.url:
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
            pw = page.query_selector("input[type='password']")
            if pw:
                pw.fill(SSO_PW or RMS_LOGIN_PW)
                page.wait_for_timeout(1000)
                try:
                    page.click("text=ログイン", timeout=5000)
                except Exception:
                    pw.press("Enter")
                page.wait_for_timeout(5000)
                try:
                    page.wait_for_url("**/mainmenu**", timeout=15000)
                except PWTimeout:
                    page.wait_for_timeout(5000)

    if "glogin.rms.rakuten.co.jp" in page.url and "mainmenu" not in page.url:
        nxt = page.query_selector("a:has-text('次へ'), button:has-text('次へ'), input[value='次へ']")
        if nxt:
            nxt.click()
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_timeout(3000)
        try:
            page.wait_for_selector("a[href*='mainmenu.rms.rakuten.co.jp'], a:has-text('ＲＭＳ')", timeout=10000)
        except PWTimeout:
            pass
        rms_link = page.query_selector("a[href*='mainmenu.rms.rakuten.co.jp']") or page.query_selector("a:has-text('ＲＭＳ')")
        if rms_link:
            rms_link.click()
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_timeout(3000)

    agree = page.query_selector("a:has-text('RMSを利用します'), button:has-text('RMSを利用します'), input[value*='RMSを利用します']")
    if agree:
        agree.click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

    main_btn = page.query_selector("a:has-text('メインメニューへ進む'), button:has-text('メインメニューへ進む')")
    if main_btn:
        main_btn.click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)

    return "mainmenu.rms.rakuten.co.jp" in page.url


def check_processing(target_orders, headless=True):
    from playwright.sync_api import sync_playwright

    print("=" * 56)
    print("楽天処理中 (ORDER_PROGRESS=200) 확인")
    print(f"대상 주문: {target_orders}")
    print("=" * 56)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=400)
        context = browser.new_context(locale="ja-JP", viewport={"width": 1400, "height": 900})
        page = context.new_page()

        try:
            print("\n[1] RMS 로그인...")
            if not login_rms(page):
                print(f"✗ 로그인 실패 (URL: {page.url})")
                return False
            print(f"  ✓ 로그인 완료")

            print("\n[2] 楽天処理中 페이지로 이동...")
            url = "https://order-rp.rms.rakuten.co.jp/order-rb/order-list-sc/init?&SEARCH_MODE=1&ORDER_PROGRESS=200"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            _ss(page, "01_processing_list")
            print(f"  URL: {page.url}")

            html = page.content()
            (TMP_DIR / "rms_processing_list.html").write_text(html, encoding="utf-8")

            print("\n[3] 주문 목록 스캔...")
            order_links = page.query_selector_all("a")
            found_orders = []
            seen = set()
            for link in order_links:
                txt = (link.inner_text() or "").strip()
                if re.match(r"\d{6}-\d{8}-\d+", txt) and txt not in seen:
                    seen.add(txt)
                    found_orders.append(txt)

            print(f"  楽天処理中 전체: {len(found_orders)}건")
            for o in found_orders:
                marker = "  ⬅ 대상" if o in target_orders else ""
                print(f"    {o}{marker}")

            results = []
            for tgt in target_orders:
                if tgt in found_orders:
                    print(f"\n[4] {tgt} 상세 진입...")
                    detail_url = f"https://order-rp.rms.rakuten.co.jp/order-rb/individual-order-detail-sc/init?orderNumber={tgt}"
                    page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(4000)
                    _ss(page, f"02_detail_{tgt}")

                    body = page.inner_text("body")
                    (TMP_DIR / f"rms_processing_detail_{tgt}.txt").write_text(body, encoding="utf-8")

                    payment = "(불명)"
                    notice = "(없음)"

                    for line in body.split("\n"):
                        s = line.strip()
                        if any(k in s for k in ["銀行振込", "コンビニ前払", "クレジットカード", "代金引換", "後払い", "楽天ペイ"]):
                            if len(s) < 60 and "決済方法" not in s:
                                payment = s
                                break

                    m = re.search(r"楽天からのお知らせ[\s\S]{0,300}", body)
                    if m:
                        seg = m.group(0)
                        lines = [l.strip() for l in seg.split("\n") if l.strip()]
                        for l in lines[1:6]:
                            if l and "楽天からのお知らせ" not in l and len(l) < 80:
                                notice = l
                                break

                    if "ユーザ対応待ち" in body:
                        notice = "ユーザ対応待ち"
                    if "銀行振込" in body and "未入金" in body:
                        notice = "銀行振込 未入金"
                    if "コンビニ前払" in body and ("未入金" in body or "入金待ち" in body):
                        notice = "コンビニ前払 未入金"

                    print(f"    決済: {payment}")
                    print(f"    お知らせ: {notice}")
                    results.append({"order": tgt, "found": True, "payment": payment, "notice": notice})
                else:
                    print(f"\n[4] {tgt} → 楽天処理中에 없음")
                    results.append({"order": tgt, "found": False, "payment": "-", "notice": "楽天処理中에 없음"})

            print("\n" + "=" * 56)
            print("결과")
            print("=" * 56)
            for r in results:
                print(f"  {r['order']}: 決済={r['payment']} / お知らせ={r['notice']}")

            return results

        finally:
            page.wait_for_timeout(2000)
            context.close()
            browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--order", action="append", required=True, help="확인할 주문번호 (반복 가능)")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    check_processing(args.order, headless=not args.headed)


if __name__ == "__main__":
    main()
