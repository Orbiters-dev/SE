"""
KSE OMS 팩킹리스트에서 "아마존 엑셀 업로드 양식(KSE 배송번호)"만 다운로드.

용도: 세은이 이미 주문등록 + 옵션코드 + 배송접수까지 완료한 후,
      팩킹리스트에 올라와있는 주문을 엑셀로만 받을 때 사용.

Usage:
    python tools/kse_download_amazon_excel_only.py                    # 기본 (기본 파일명)
    python tools/kse_download_amazon_excel_only.py --suffix 오후       # 파일명 접미어 (0420_amazon_주문서_오후.xlsx)
    python tools/kse_download_amazon_excel_only.py --headed            # 브라우저 표시
    python tools/kse_download_amazon_excel_only.py --date 0420         # 날짜 지정
"""
import argparse
import io
import os
import sys
import time
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

KSEOMS_LOGIN_URL = "https://kseoms.com/login"
KSEOMS_SHIP_URL  = "https://kseoms.com/shipping2"
LOGIN_ID         = os.getenv("KSEOMS_LOGIN_ID", "")
LOGIN_PW         = os.getenv("KSEOMS_LOGIN_PASSWORD", "")
ORDER_DIR        = Path(r"C:\Users\orbit\Desktop\s\아마존 주문서")
TMP_DIR          = PROJECT_ROOT / ".tmp"


def _ss(page, name: str):
    try:
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(TMP_DIR / f"kse_dl_{name}.png"), full_page=True)
    except Exception:
        pass


def _retry(fn, retries=3, delay=1.5, label=""):
    last = None
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            print(f"    [retry {i+1}/{retries}] {label}: {type(e).__name__}")
            time.sleep(delay)
    raise last


def run(headless=True, date_str=None, suffix=""):
    from playwright.sync_api import sync_playwright

    if not date_str:
        date_str = date.today().strftime("%m%d")

    stem = f"{date_str}_amazon_주문서"
    if suffix:
        stem += f"_{suffix}"
    save_path = ORDER_DIR / f"{stem}.xlsx"

    print("=" * 60)
    print("  KSE 팩킹리스트 → 아마존 엑셀 다운로드 전용")
    print(f"  저장 경로: {save_path}")
    print("=" * 60)

    if not LOGIN_ID or not LOGIN_PW:
        print("ERROR: KSEOMS_LOGIN_ID / KSEOMS_LOGIN_PASSWORD 없음")
        return 1

    ORDER_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=400)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("dialog", lambda d: (print(f"  [dialog] {d.message}"), d.accept()))

        try:
            # ── Step 1: 로그인 ─────────────────────────
            print("\n[1/3] 로그인...")
            page.goto(KSEOMS_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)

            id_input = (
                page.query_selector("input[name*=id]")
                or page.query_selector("input[name*=user]")
                or page.query_selector("input[type=text]")
                or page.query_selector("input[placeholder*='Id']")
                or page.query_selector("input[placeholder*='ID']")
            )
            pw_input = page.query_selector("input[type=password]")

            if not id_input or not pw_input:
                print("  ERROR: 로그인 폼 못 찾음")
                _ss(page, "01_no_form")
                return 2

            _retry(lambda: id_input.fill(LOGIN_ID), label="fill ID")
            _retry(lambda: pw_input.fill(LOGIN_PW), label="fill PW")

            submit = (
                page.query_selector("button[type=submit]")
                or page.query_selector("input[type=submit]")
                or page.query_selector("button:has-text('Login')")
                or page.query_selector("button:has-text('로그인')")
            )
            if submit:
                _retry(lambda: submit.click(), label="click submit")
            else:
                _retry(lambda: pw_input.press("Enter"), label="press Enter")

            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_timeout(3000)
            print(f"  로그인 완료 (URL: {page.url})")

            # ── Step 2: 팩킹리스트 이동 ─────────────────────
            print("\n[2/3] 팩킹리스트 이동...")
            page.goto(KSEOMS_SHIP_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            _ss(page, "02_shipping")

            # AG Grid 로드 대기
            try:
                page.wait_for_selector(".ag-row, .ag-center-cols-container", timeout=15000)
            except Exception:
                print("  WARNING: AG Grid 안 나타남, 진행 계속")
            page.wait_for_timeout(1500)

            row_count = page.evaluate("""() => document.querySelectorAll('.ag-row').length""")
            print(f"  팩킹리스트 행 수: {row_count}")

            # ── Step 3: 다운로드 버튼 → 아마존 엑셀 ──────────
            print("\n[3/3] 다운로드 실행...")

            # 모달 강제 닫기
            page.evaluate("""() => {
                document.querySelectorAll('.modal.in, .modal.show').forEach(m => {
                    m.classList.remove('in', 'show'); m.style.display = 'none';
                });
                document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
            }""")
            page.wait_for_timeout(300)

            # 다운로드 드롭다운 토글 찾기
            download_btn = None
            for btn in page.query_selector_all("button, a"):
                try:
                    txt = btn.inner_text().strip()
                except Exception:
                    txt = ""
                if ("다운로드" in txt) or (txt.lower() == "download"):
                    download_btn = btn
                    print(f"  다운로드 버튼: '{txt}'")
                    break

            if not download_btn:
                print("  ERROR: '다운로드' 버튼 못 찾음")
                _ss(page, "03_no_download_btn")
                return 3

            page.evaluate("(btn) => btn.scrollIntoView({block:'center'})", download_btn)
            page.wait_for_timeout(400)
            _retry(lambda: download_btn.click(), label="click download toggle")
            page.wait_for_timeout(1200)
            _ss(page, "03_dropdown_open")

            # "아마존 엑셀 업로드 양식(KSE 배송번호)" 메뉴 찾기
            amazon_dl = None
            for item in page.query_selector_all("a, button, li a, .dropdown-item, .dropdown-menu a, .dropdown-menu li"):
                try:
                    txt = item.inner_text().strip()
                except Exception:
                    txt = ""
                if "아마존" in txt and ("엑셀" in txt or "Excel" in txt or "excel" in txt):
                    amazon_dl = item
                    print(f"  메뉴 선택: '{txt}'")
                    break

            if not amazon_dl:
                menu_texts = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('.dropdown-menu a, .dropdown-item, .dropdown-menu li'))
                        .map(a => a.innerText.trim()).filter(t => t);
                }""")
                print(f"  ERROR: '아마존 엑셀' 메뉴 못 찾음. 메뉴 목록: {menu_texts}")
                _ss(page, "03_no_amazon_menu")
                return 4

            with page.expect_download(timeout=30000) as dl_info:
                _retry(lambda: amazon_dl.click(), label="click amazon excel")

            download = dl_info.value
            download.save_as(str(save_path))

            size = save_path.stat().st_size
            print(f"\n✓ 다운로드 완료: {save_path}")
            print(f"  파일 크기: {size:,} bytes")
            _ss(page, "04_downloaded")
            return 0

        except Exception as e:
            print(f"\n✗ 에러: {type(e).__name__}: {e}")
            _ss(page, "99_error")
            return 99
        finally:
            browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="브라우저 표시")
    ap.add_argument("--date", dest="date_str", default=None, help="날짜 (MMDD)")
    ap.add_argument("--suffix", default="", help="파일명 접미어 (예: 오후)")
    args = ap.parse_args()

    code = run(headless=not args.headed, date_str=args.date_str, suffix=args.suffix)
    sys.exit(code)


if __name__ == "__main__":
    main()
