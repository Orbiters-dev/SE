"""
KSE OMS Amazon JP 주문 처리 파이프라인 (4번부터)

선행조건 (세은 직접 처리):
  세은이 Amazon Seller Central에서 TXT 다운받아 Excel 변환 후 KSE OMS에 직접 업로드한 상태.
  → 대기목록(/orders) 탭에 주문이 떠있어야 함.

마존이 자동화 (4~7):
  4. /orders 대기목록 탭 → 옵션코드 입력
  5. 전체 선택 → 배송접수(국제)
  6. 팩킹리스트(/shipping2) 이동 확인
  7. 아마존 엑셀 다운로드 → {MMDD}_amazon_주문서.xlsx 저장
  8. 주문 요약 출력 (Teams 발송 X — 별도 --send-teams 플래그로만)

Usage:
    python tools/kse_amazon_order.py --headed              # 옵션코드 → 배송접수 → 다운로드 → 요약
    python tools/kse_amazon_order.py --headed --dry-run    # 옵션코드만 (배송접수 X)
    python tools/kse_amazon_order.py --headed --date 0317  # 날짜 지정 (다운로드 파일명)
    python tools/kse_amazon_order.py --headed --send-teams # 끝나면 요약 Teams 발송
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

    removed = page.evaluate("""() => {
        let count = 0;
        const selectors = [
            '.notice-area', '.notice-wrap', '.notice-container',
            '.board-notice', '[class*=notice]', '.alert-area',
            '#noticeArea', '#notice_area',
        ];
        for (const sel of selectors) {
            document.querySelectorAll(sel).forEach(el => {
                if (el.innerText && el.innerText.length > 500) {
                    el.remove();
                    count++;
                }
            });
        }
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


def _login(page):
    """KSE OMS 로그인."""
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
        raise RuntimeError("로그인 폼을 찾을 수 없습니다")

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


def run(dry_run=False, headless=False, date_str=None, send_teams=False, from_packing=False):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    if not date_str:
        date_str = date.today().strftime("%m%d")
    download_name = f"{date_str}_amazon_주문서.xlsx"

    print("=" * 60)
    print("  Amazon JP 주문 처리 (4번부터 — 옵션코드 → 배송접수 → 다운로드)")
    print(f"  다운로드 이름: {download_name}")
    if dry_run:
        print("  [DRY-RUN] 배송접수는 하지 않습니다")
    if send_teams:
        print("  [Teams 발송 ON]")
    else:
        print("  [Teams 발송 OFF] 요약은 출력만. 발송하려면 --send-teams")
    print("  ※ 선행조건: 세은이 KSE에 Amazon Excel 직접 업로드 완료 상태")
    print("=" * 60)

    if not LOGIN_ID or not LOGIN_PW:
        print("ERROR: KSEOMS_LOGIN_ID / KSEOMS_LOGIN_PASSWORD 가 .env에 없습니다")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=500)
        page = browser.new_page(viewport={"width": 1600, "height": 900})

        def _safe_accept(dialog):
            try:
                print(f"  [다이얼로그] {dialog.message}")
                dialog.accept()
            except Exception:
                pass
        page.on("dialog", _safe_accept)

        try:
            # ══════════════════════════════════════════════════════════
            # Step A: 로그인 (자동화 진입에 필요)
            # ══════════════════════════════════════════════════════════
            print("\n[A] KSE OMS 로그인...")
            _login(page)
            _ss(page, "A_logged_in")
            print(f"  로그인 완료 (URL: {page.url})")

            # ══════════════════════════════════════════════════════════
            # FROM-PACKING 모드: /shipping2에서 옵션코드 입력 + 다운로드만
            # (세은이 배송접수까지 완료한 상태 가정)
            # ══════════════════════════════════════════════════════════
            if from_packing:
                print("\n[FROM-PACKING] /shipping2에서 옵션코드 + 다운로드...")
                page.goto(KSEOMS_SHIP_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                _close_notices(page)

                try:
                    sb = page.query_selector("button:has-text('검 색')") or page.query_selector("button:has-text('검색')")
                    if sb:
                        sb.click(timeout=5000)
                        page.wait_for_timeout(8000)
                        print("  검색 완료")
                except Exception as e:
                    print(f"  검색 실패: {e}")

                try:
                    page.wait_for_selector(".ag-row", timeout=15000)
                    print("  AG Grid 로드")
                except Exception:
                    print("  AG Grid 미로드, 5초 대기")
                    page.wait_for_timeout(5000)

                all_rows = page.evaluate("""() => {
                    let api = null;
                    for (const key of Object.keys(window)) {
                        try {
                            if (window[key] && window[key].api && typeof window[key].api.forEachNode === 'function') {
                                api = window[key].api; break;
                            }
                        } catch(e) {}
                    }
                    if (!api) return [];
                    const result = [];
                    api.forEachNode(node => {
                        if (node.data) result.push({
                            rowIndex: node.rowIndex,
                            itemTitle: node.data.itemTitle || '',
                            itemTitleKr: node.data.itemTitleKr || '',
                            option: node.data.option || '',
                            optionCode: node.data.optionCode || '',
                            market: node.data.market || '',
                            shopName: node.data.shopName || '',
                            deliveryCode: node.data.deliveryCode || '',
                        });
                    });
                    return result;
                }""")
                print(f"  팩킹리스트 전체: {len(all_rows)}건")

                # 아마존 행만 (라쿠텐 제외)
                amz_rows = []
                for r in all_rows:
                    market_low = (r.get("market") or "").lower()
                    ship = (r.get("shopName") or "") + " " + (r.get("deliveryCode") or "")
                    if market_low in ("rakuten", "rakutenjp"):
                        continue
                    if "rakuten" in ship.lower() or "라쿠텐" in ship or "楽天" in ship or "435776" in ship:
                        continue
                    amz_rows.append(r)
                print(f"  아마존 행: {len(amz_rows)}건")

                if not amz_rows:
                    print("  [중단] 아마존 행 없음. .tmp/packing_grid_dump.json 덤프")
                    TMP_DIR.mkdir(parents=True, exist_ok=True)
                    with open(TMP_DIR / "packing_grid_dump.json", "w", encoding="utf-8") as f:
                        json.dump(all_rows, f, ensure_ascii=False, indent=2)
                    _ss(page, "from_packing_no_amz")
                    return

                # 옵션코드 입력
                filled = 0
                for r in amz_rows:
                    idx = r.get("rowIndex", 0)
                    item = r.get("itemTitleKr") or r.get("itemTitle") or ""
                    option = r.get("option", "")
                    current = (r.get("optionCode") or "").strip()
                    expected = lookup_option_code(item, option)
                    if not expected:
                        print(f"  [{idx}] 매핑 없음: {item[:40]}")
                        continue
                    if current == expected:
                        print(f"  [{idx}] 이미 정확: {expected}")
                        continue
                    print(f"  [{idx}] {current or '(빈칸)'} → {expected}")
                    ok = _write_code(page, idx, expected)
                    if ok:
                        filled += 1
                        print(f"    OK")
                    else:
                        print(f"    실패")

                if filled > 0:
                    save_btn = page.query_selector("button:has-text('저장')")
                    if save_btn:
                        _retry(lambda: save_btn.click(), label="click save")
                        page.wait_for_timeout(3000)
                        print(f"  저장 {filled}건")
                else:
                    print("  신규 입력 없음 (모두 이미 채워짐 또는 매핑 없음)")

                _ss(page, "from_packing_options")

                # 다운로드 (Step 7과 동일 로직 인라인)
                print("\n[다운로드] 아마존 엑셀...")
                page.evaluate("""() => {
                    document.querySelectorAll('.modal.in, .modal.show').forEach(m => {
                        m.classList.remove('in', 'show'); m.style.display = 'none';
                    });
                    document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                    document.body.classList.remove('modal-open');
                    document.body.style.overflow = '';
                }""")
                page.wait_for_timeout(500)

                dl_btn = None
                for btn in page.query_selector_all("button, a"):
                    try:
                        txt = btn.inner_text().strip()
                    except Exception:
                        txt = ""
                    if "다운로드" in txt:
                        dl_btn = btn
                        print(f"  다운로드 버튼: '{txt}'")
                        break

                if dl_btn:
                    page.evaluate("(b) => b.scrollIntoView({block:'center'})", dl_btn)
                    page.wait_for_timeout(500)
                    _retry(lambda: dl_btn.click(), label="click download")
                    page.wait_for_timeout(1500)
                    _ss(page, "from_packing_dropdown")

                    amazon_dl = None
                    for it in page.query_selector_all("a, button, li a, .dropdown-item, .dropdown-menu a"):
                        try:
                            txt = it.inner_text().strip()
                        except Exception:
                            txt = ""
                        if "아마존" in txt and ("엑셀" in txt or "Excel" in txt.lower()):
                            amazon_dl = it
                            print(f"  메뉴: '{txt}'")
                            break

                    if amazon_dl:
                        ORDER_DIR.mkdir(parents=True, exist_ok=True)
                        with page.expect_download(timeout=30000) as di:
                            _retry(lambda: amazon_dl.click(), label="click amazon excel")
                        save_path = ORDER_DIR / download_name
                        di.value.save_as(str(save_path))
                        print(f"  다운로드 완료: {save_path}")
                    else:
                        print("  WARNING: '아마존 엑셀' 메뉴 못 찾음")
                        _ss(page, "from_packing_no_menu")
                else:
                    print("  WARNING: 다운로드 버튼 못 찾음")
                    _ss(page, "from_packing_no_dlbtn")

                # 요약
                print("\n[요약]")
                sys.path.insert(0, str(PROJECT_ROOT / "tools"))
                from kse_order_summary import build_summary, send_to_teams
                summary_text = build_summary(amz_rows)
                print(summary_text)
                TMP_DIR.mkdir(parents=True, exist_ok=True)
                with open(TMP_DIR / "order_summary.txt", "w", encoding="utf-8") as f:
                    f.write(summary_text)
                with open(TMP_DIR / "packing_grid_data.json", "w", encoding="utf-8") as f:
                    json.dump(all_rows, f, ensure_ascii=False, indent=2)

                if send_teams:
                    print("\n  Teams 전송 중...")
                    send_to_teams(summary_text)
                else:
                    print("\n  [Teams 발송 OFF] 승인 후 --send-teams")

                print(f"\n{'=' * 60}\n  FROM-PACKING 완료: {download_name}\n{'=' * 60}")
                return

            # ══════════════════════════════════════════════════════════
            # Step 4: /orders 대기목록 탭 → 옵션코드 입력
            # ══════════════════════════════════════════════════════════
            print("\n[4/8] /orders 대기목록 탭으로 이동 + 옵션코드 입력...")
            page.goto(KSEOMS_ORDERS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            _close_notices(page)

            # 대기목록 탭 클릭
            waitlist_tab = None
            for link in page.query_selector_all("a"):
                try:
                    txt = link.inner_text().strip()
                except Exception:
                    txt = ""
                if "대기목록" in txt or "Waiting List" in txt:
                    waitlist_tab = link
                    print(f"  탭 발견: '{txt}'")
                    break

            if waitlist_tab:
                try:
                    waitlist_tab.click(timeout=5000)
                    page.wait_for_timeout(3000)
                    print("  대기목록 탭 클릭 완료")
                except Exception:
                    pass

            # 검색 (retry 3회 + 대기 강화)
            search_clicked = False
            for attempt in range(3):
                try:
                    search_btn = page.query_selector("button:has-text('검 색')") or page.query_selector("button:has-text('검색')")
                    if search_btn:
                        search_btn.click(timeout=5000)
                        page.wait_for_timeout(8000)
                        print(f"  검색 완료 (attempt {attempt+1})")
                        search_clicked = True
                        break
                except Exception as e:
                    print(f"  검색 attempt {attempt+1} 실패: {e}")
                    page.wait_for_timeout(2000)
            if not search_clicked:
                print("  [WARN] 검색 버튼 클릭 실패 — 그래도 grid 시도")

            # AG Grid 로드 대기 (셀렉터 다양화 + retry)
            grid_loaded = False
            for sel in [".ag-row", ".ag-center-cols-container .ag-row", "[role='row']"]:
                try:
                    page.wait_for_selector(sel, timeout=10000)
                    print(f"  AG Grid 로드 확인 ({sel})")
                    grid_loaded = True
                    break
                except Exception:
                    continue
            if not grid_loaded:
                print("  AG Grid 미로드 — 검색 재시도")
                try:
                    search_btn = page.query_selector("button:has-text('검 색')") or page.query_selector("button:has-text('검색')")
                    if search_btn:
                        search_btn.click(timeout=5000)
                        page.wait_for_timeout(10000)
                        print("  검색 재시도 완료")
                except Exception:
                    pass
            page.wait_for_timeout(5000)

            # AG Grid 데이터 읽기
            rows = page.evaluate("""() => {
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

            print(f"  대기목록 주문 건수: {len(rows)}건")

            if not rows:
                # DOM 직접 카운트로 교차검증
                dom_row_count = page.evaluate("""() => {
                    const rows = document.querySelectorAll('.ag-row, .ag-center-cols-container .ag-row');
                    return rows.length;
                }""")
                print(f"  [교차검증] DOM .ag-row 카운트: {dom_row_count}")
                print(f"  [현재 URL] {page.url}")
                print("  [중단] 대기목록 0건 — 세은이 KSE에 업로드했는지 확인 필요.")
                _ss(page, "04_no_rows")
                return

            filled = 0
            for row in rows:
                item_title = row.get("itemTitle", "")
                item_kr = row.get("itemTitleKr", "")
                option = row.get("option", "")
                current = row.get("optionCode", "").strip()
                idx = row.get("rowIndex", 0)
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
                    ok = _write_code(page, idx, expected)
                    if ok:
                        print(f"    OK (API+AJAX)")
                    else:
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
                return

            # ══════════════════════════════════════════════════════════
            # Step 5: 전체 선택 → 배송접수(국제)
            # ══════════════════════════════════════════════════════════
            print("\n[5/8] 전체 선택 + 배송접수(국제)...")

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

            ship_btn = (
                page.query_selector("button:has-text('배송접수(국제)')")
                or page.query_selector("a:has-text('배송접수(국제)')")
            )
            if not ship_btn:
                for btn in page.query_selector_all("button, a, input[type=button]"):
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
                return

            _ss(page, "05_shipped")

            # ══════════════════════════════════════════════════════════
            # Step 6: 팩킹리스트(/shipping2) 이동 확인
            # ══════════════════════════════════════════════════════════
            print("\n[6/8] 팩킹리스트 이동 확인...")

            if "shipping2" in page.url:
                print("  /shipping2로 자동 이동됨!")
            else:
                print(f"  현재 URL: {page.url}")
                print("  /shipping2로 수동 이동...")
                page.goto(KSEOMS_SHIP_URL, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

            _close_notices(page)

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

            page.evaluate("""() => {
                document.querySelectorAll('.modal.in, .modal.show').forEach(m => {
                    m.classList.remove('in', 'show'); m.style.display = 'none';
                });
                document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
            }""")
            page.wait_for_timeout(500)

            download_btn = None
            for btn in page.query_selector_all("button, a"):
                try:
                    txt = btn.inner_text().strip()
                except Exception:
                    txt = ""
                if "다운로드" in txt or "download" in txt.lower():
                    download_btn = btn
                    print(f"  다운로드 버튼 발견: '{txt}'")
                    break

            if download_btn:
                page.evaluate("""(btn) => {
                    btn.scrollIntoView({block: 'center'});
                }""", download_btn)
                page.wait_for_timeout(500)

                _retry(lambda: download_btn.click(), label="click download")
                page.wait_for_timeout(1500)
                print("  다운로드 드롭다운 클릭")

                _ss(page, "07_dropdown_open")

                amazon_dl = None
                for item in page.query_selector_all("a, button, li a, .dropdown-item, .dropdown-menu a"):
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
            else:
                print("  WARNING: 다운로드 버튼 못 찾음")
                _ss(page, "07_no_download_btn")

            _ss(page, "07_downloaded")

            # ══════════════════════════════════════════════════════════
            # Step 8: 주문 요약 생성 (Teams 발송은 --send-teams일 때만)
            # ══════════════════════════════════════════════════════════
            print(f"\n[8/8] 주문 요약 생성...")

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

            # 디버그용 JSON 저장
            TMP_DIR.mkdir(parents=True, exist_ok=True)
            with open(TMP_DIR / "packing_grid_data.json", "w", encoding="utf-8") as f:
                json.dump(packing_rows, f, ensure_ascii=False, indent=2)

            if packing_rows:
                # kse_order_summary.build_summary 사용 (정확한 옵션코드 기반 분류)
                sys.path.insert(0, str(PROJECT_ROOT / "tools"))
                from kse_order_summary import build_summary, send_to_teams

                # 라쿠텐 행 제외 (KSE에서 더 이상 처리 X)
                amazon_rows = [
                    r for r in packing_rows
                    if (r.get("market") or "").lower() not in ("rakuten", "rakutenjp")
                ]
                summary_text = build_summary(amazon_rows)

                print()
                print(summary_text)

                # .tmp에 저장
                with open(TMP_DIR / "order_summary.txt", "w", encoding="utf-8") as f:
                    f.write(summary_text)

                if send_teams:
                    print("\n  Teams 전송 중...")
                    send_to_teams(summary_text)
                else:
                    print("\n  [Teams 발송 OFF] 위 요약은 출력만. 세은 승인 후 별도 실행:")
                    print("    python tools/kse_order_summary.py --from-file .tmp/packing_grid_data.json")
            else:
                print("  팩킹리스트 데이터 없음")

            print(f"\n{'=' * 60}")
            print(f"  Amazon JP 주문 처리 완료!")
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
    parser = argparse.ArgumentParser(description="KSE OMS Amazon JP 주문 처리 (4번부터)")
    parser.add_argument("--dry-run", action="store_true", help="옵션코드만, 배송접수 X")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시")
    parser.add_argument("--date", type=str, help="날짜 (MMDD, 다운로드 파일명용)")
    parser.add_argument("--send-teams", action="store_true", help="요약 Teams 자동 발송 (디폴트 OFF)")
    parser.add_argument("--from-packing", action="store_true", help="세은이 배송접수까지 완료한 상태 — /shipping2에서 옵션코드+다운로드만")
    args = parser.parse_args()
    run(
        dry_run=args.dry_run,
        headless=not args.headed,
        date_str=args.date,
        send_teams=args.send_teams,
        from_packing=args.from_packing,
    )
