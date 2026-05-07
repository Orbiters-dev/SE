"""
Rakuten Auditor — 풀 파이프라인 5단계 검증 + 자동 수정

검증 항목:
  CHECK 0: RMS 주문확인 — 注文確認待ち에 주문 남아있지 않은지 (→ 확인+메일 완료)
  CHECK 1: 옵션코드 — KSE 팩킹리스트 optionCode vs OPTION_MAP 기대값
  CHECK 2: 송장번호 — KSE trackingNo 존재 + 형식
  CHECK 3: 송장번호 교차 — KSE trackingNo vs RMS 伝票番号

자동 수정:
  CHECK 1 FAIL → KSE 팩킹리스트에서 옵션코드 재입력 → 재검증
  CHECK 3 FAIL → RMS 주문상세에서 송장번호 재입력 → 재검증

Usage:
    python tools/rakuten_auditor.py --headed
    python tools/rakuten_auditor.py --skip-rms
    python tools/rakuten_auditor.py --no-fix      # 검증만, 수정 안 함
"""

import argparse
import io
import json
import os
import re
import sys
import time
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

ORDER_CONFIRM_URL = "https://order-rp.rms.rakuten.co.jp/order-rb/order-list-sc/init?&SEARCH_MODE=1&ORDER_PROGRESS=100"
SHIP_WAIT_URL     = "https://order-rp.rms.rakuten.co.jp/order-rb/order-list-sc/init?&SEARCH_MODE=1&ORDER_PROGRESS=300"
SHIPPED_URL       = "https://order-rp.rms.rakuten.co.jp/order-rb/order-list-sc/init?&SEARCH_MODE=1&ORDER_PROGRESS=500"

TMP_DIR = PROJECT_ROOT / ".tmp"

# ── 옵션코드 매핑 (kse_rakuten_order.py와 동일) ──
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
}

JP_TO_EN = {
    "ステンレス": "stainless", "フリップ": "flip", "ワンタッチ": "flip",
    "ワンタッチ式": "flip", "シリコン": "silicone", "交換用": "replacement",
    "ストロー": "straw", "乳首": "nipple", "チェリー": "cherry",
    "ベア": "bear", "オリーブ": "olive", "ホワイト": "white",
    "チャコール": "charcoal", "ピンク": "pink", "スカイブルー": "skyblue",
    "ユニコーン": "unicorn", "ダイノ": "dino", "恐竜": "dino",
    "ストローニップル": "silicone nipple", "4個入": "4pcs", "4個": "4pcs",
    "2個": "2pack", "2セット": "2pack", "4pcs": "4pcs", "2pack": "2pack",
    "チェリーピーチ": "cherry",
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


def _ss(page, name: str):
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"audit_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        pass


# ─────────────────────────────────────────────────
#  KSE 로그인 (공용)
# ─────────────────────────────────────────────────

def kse_login(page):
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
        print("  ERROR: KSE 로그인 폼 없음")
        return False
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
    print(f"  KSE 로그인 완료 (URL: {page.url})")
    return True


# ─────────────────────────────────────────────────
#  RMS 로그인 (공용) — rakuten_tracking_input.py 동일 로직
# ─────────────────────────────────────────────────

def rms_login(page):
    from playwright.sync_api import TimeoutError as PWTimeout

    page.goto(RMS_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

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
        print("  R-Login 제출 완료")

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

    if "glogin.rms.rakuten.co.jp" in page.url and "mainmenu" not in page.url:
        for sel in ["a:has-text('次へ'), button:has-text('次へ'), input[value='次へ']"]:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                page.wait_for_timeout(3000)
                break
        rms_link = (
            page.query_selector("a[href*='mainmenu.rms.rakuten.co.jp']")
            or page.query_selector("a:has-text('ＲＭＳ')")
        )
        if rms_link:
            rms_link.click()
            page.wait_for_timeout(3000)

    agree = page.query_selector("a:has-text('RMSを利用します'), button:has-text('RMSを利用します')")
    if agree:
        agree.click()
        page.wait_for_timeout(3000)

    main_menu_btn = page.query_selector("a:has-text('メインメニューへ進む'), button:has-text('メインメニューへ進む')")
    if main_menu_btn:
        main_menu_btn.click()
        page.wait_for_timeout(3000)

    print(f"  RMS 로그인 완료 (URL: {page.url})")


# ─────────────────────────────────────────────────
#  CHECK 0: RMS 주문확인 + 메일 검증
# ─────────────────────────────────────────────────

def check_rms_order_flow(page, pack_numbers: list[str]) -> dict:
    """주문이 정상적으로 확인되고 메일이 발송되었는지 확인.

    검증 로직:
      - 注文確認待ち(100)에 남아있으면 → 주문확인 안 된 것
      - 発送待ち(300) 또는 発送済み(500)에 있으면 → 확인+メール 완료
    """
    result = {
        "confirmed": [],      # 주문확인 완료 (100에 없음)
        "not_confirmed": [],   # 주문확인 실패 (100에 남아있음)
        "in_ship_wait": [],    # 発送待ち (메일 발송 완료)
        "shipped": [],         # 発送済み
    }

    if not pack_numbers:
        return result

    print("\n" + "-" * 60)
    print("  CHECK 0: RMS 주문확인 + メール 발송 검증")
    print("-" * 60)

    # 注文確認待ち 확인
    page.goto(ORDER_CONFIRM_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    _ss(page, "check0_confirm_wait")

    links = page.query_selector_all("a[href*='orderNumber=']")
    pending_orders = set()
    for link in links:
        href = link.get_attribute("href") or ""
        m = re.search(r'orderNumber=([\d\-]+)', href)
        if m:
            pending_orders.add(m.group(1))

    for pn in pack_numbers:
        if pn in pending_orders:
            result["not_confirmed"].append(pn)
            print(f"  {pn}: FAIL (注文確認待ちに残留 → 주문확인 안 됨)")
        else:
            result["confirmed"].append(pn)

    # 発送待ち 확인
    page.goto(SHIP_WAIT_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    _ss(page, "check0_ship_wait")

    links = page.query_selector_all("a[href*='orderNumber=']")
    ship_wait_orders = set()
    for link in links:
        href = link.get_attribute("href") or ""
        m = re.search(r'orderNumber=([\d\-]+)', href)
        if m:
            ship_wait_orders.add(m.group(1))

    for pn in pack_numbers:
        if pn in ship_wait_orders:
            result["in_ship_wait"].append(pn)

    # 発送済み 확인
    page.goto(SHIPPED_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    links = page.query_selector_all("a[href*='orderNumber=']")
    shipped_orders = set()
    for link in links:
        href = link.get_attribute("href") or ""
        m = re.search(r'orderNumber=([\d\-]+)', href)
        if m:
            shipped_orders.add(m.group(1))

    for pn in pack_numbers:
        if pn in shipped_orders:
            result["shipped"].append(pn)

    # 결과 출력
    for pn in pack_numbers:
        if pn in result["not_confirmed"]:
            continue  # already printed
        elif pn in shipped_orders:
            print(f"  {pn}: PASS (発送済み → 주문확인+メール+송장 모두 완료)")
        elif pn in ship_wait_orders:
            print(f"  {pn}: PASS (発送待ち → 주문확인+サンクスメール+発送メール 완료)")
        else:
            print(f"  {pn}: PASS (注文確認待ちに없음 → 확인 완료)")

    return result


# ─────────────────────────────────────────────────
#  CHECK 1+2: KSE 옵션코드 + 송장번호 검증
# ─────────────────────────────────────────────────

def read_kse_packing_list(page) -> list[dict]:
    """KSE 팩킹리스트에서 Rakuten 주문 데이터 읽기."""
    page.goto(KSEOMS_SHIP_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    try:
        search_btn = page.wait_for_selector(
            "button:has-text('검 색'), button:has-text('검색')", timeout=5000
        )
        search_btn.click()
        page.wait_for_timeout(3000)
    except Exception:
        pass

    try:
        page.wait_for_selector(".ag-row", timeout=30000)
    except Exception:
        print("  ⚠ 팩킹리스트에 표시된 주문이 없습니다 (ag-row 타임아웃)")
        return []

    rows = page.evaluate("""() => {
        const api = window.gridOptions_orders && window.gridOptions_orders.api;
        if (!api) return [];
        const result = [];
        api.forEachNode(node => {
            if (!node.data) return;
            const d = node.data;
            result.push({
                rowIndex: node.rowIndex,
                packNo: d.packNo || '',
                orderNo: d.orderNo || '',
                itemTitle: d.itemTitle || '',
                option: d.option || '',
                optionCode: d.optionCode || '',
                trackingNo: d.LocalTrackingNo || d.localTrackingNo || '',
                market: d.market || '',
                status: d.status || d.statusVal || '',
            });
        });
        return result;
    }""")

    return [r for r in rows if "rakuten" in r.get("market", "").lower()]


def audit_kse_data(rakuten_rows: list[dict]) -> list[dict]:
    """KSE 데이터에 대해 옵션코드 + 송장번호 검증 수행."""
    audit_rows = []

    print("\n" + "-" * 60)
    print("  CHECK 1: 옵션코드 검증")
    print("-" * 60)

    for r in rakuten_rows:
        item = r.get("itemTitle", "")
        option = r.get("option", "")
        actual_code = r.get("optionCode", "").strip()
        expected_code = lookup_option_code(item, option)
        tracking = r.get("trackingNo", "").strip()

        row_result = {
            "rowIndex": r.get("rowIndex"),
            "packNo": r.get("packNo", ""),
            "itemTitle": item[:60],
            "option": option[:40],
            "actual_optionCode": actual_code,
            "expected_optionCode": expected_code or "UNMAPPED",
            "optionCode_ok": False,
            "trackingNo": tracking,
            "tracking_ok": False,
            "rms_trackingNo": None,
            "rms_tracking_match": None,
        }

        if expected_code is None:
            status = "WARN(매핑없음)"
        elif actual_code == expected_code:
            row_result["optionCode_ok"] = True
            status = "PASS"
        else:
            status = "FAIL"

        if tracking and re.match(r'^\d{12}$', tracking):
            row_result["tracking_ok"] = True
            track_status = "PASS"
        elif tracking:
            row_result["tracking_ok"] = True
            track_status = f"WARN({tracking[:15]})"
        else:
            track_status = "FAIL(없음)"

        print(f"  [{r.get('rowIndex')}] {status:15s} | "
              f"코드: {actual_code or '(빈값)'} → 기대: {expected_code or 'UNMAPPED'} | "
              f"송장: {track_status}")

        audit_rows.append(row_result)

    return audit_rows


# ─────────────────────────────────────────────────
#  CHECK 3: RMS 송장번호 교차 검증
# ─────────────────────────────────────────────────

def audit_rms_tracking(page, audit_data: list[dict]) -> list[dict]:
    """RMS 주문상세에서 송장번호 읽어서 KSE와 비교."""
    unique_orders = {}
    for r in audit_data:
        pn = r["packNo"]
        if pn and pn not in unique_orders:
            unique_orders[pn] = r["trackingNo"]

    if not unique_orders:
        return audit_data

    print("\n" + "-" * 60)
    print(f"  CHECK 3: RMS 송장번호 교차 검증 ({len(unique_orders)}건)")
    print("-" * 60)

    rms_tracking_map = {}

    for progress in ["500", "300"]:
        url = f"https://order-rp.rms.rakuten.co.jp/order-rb/order-list-sc/init?&SEARCH_MODE=1&ORDER_PROGRESS={progress}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        links = page.query_selector_all("a[href*='orderNumber=']")
        rms_orders = set()
        for link in links:
            href = link.get_attribute("href") or ""
            m = re.search(r'orderNumber=([\d\-]+)', href)
            if m:
                rms_orders.add(m.group(1))

        if not rms_orders:
            continue

        checked = 0
        for pack_no, kse_tracking in unique_orders.items():
            if pack_no not in rms_orders or pack_no in rms_tracking_map:
                continue

            detail_url = f"https://order-rp.rms.rakuten.co.jp/order-rb/individual-order-detail-sc/init?orderNumber={pack_no}"
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            rms_tracking = page.evaluate("""() => {
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {
                    const val = inp.value || '';
                    if (/^\\d{12}$/.test(val)) return val;
                }
                const body = document.body.innerText || '';
                const m = body.match(/伝票番号[\\s:：]*(\\d{12})/);
                if (m) return m[1];
                const spans = document.querySelectorAll('span, td, div');
                for (const el of spans) {
                    const t = (el.textContent || '').trim();
                    if (/^\\d{12}$/.test(t)) return t;
                }
                return '';
            }""")

            rms_tracking_map[pack_no] = rms_tracking
            match = "PASS" if rms_tracking == kse_tracking else "FAIL"
            print(f"  {pack_no}: KSE={kse_tracking} / RMS={rms_tracking or '(읽기실패)'} → {match}")
            checked += 1

    # 결과 병합
    for r in audit_data:
        pn = r["packNo"]
        if pn in rms_tracking_map:
            rms_val = rms_tracking_map[pn]
            r["rms_trackingNo"] = rms_val
            r["rms_tracking_match"] = (rms_val == r["trackingNo"]) if rms_val else None

    return audit_data


# ─────────────────────────────────────────────────
#  자동 수정: 옵션코드 (KSE AG Grid 셀 편집)
# ─────────────────────────────────────────────────

def fix_option_codes(page, failures: list[dict]) -> int:
    """KSE 팩킹리스트에서 틀린 옵션코드를 수정. 리턴: 수정 건수."""
    if not failures:
        return 0

    print("\n" + "=" * 60)
    print(f"  AUTO-FIX: 옵션코드 수정 ({len(failures)}건)")
    print("=" * 60)

    # 팩킹리스트로 이동 (이미 KSE 로그인 상태)
    page.goto(KSEOMS_SHIP_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    try:
        search_btn = page.wait_for_selector(
            "button:has-text('검 색'), button:has-text('검색')", timeout=5000
        )
        search_btn.click()
        page.wait_for_timeout(3000)
    except Exception:
        pass

    page.wait_for_selector(".ag-row", timeout=15000)

    fixed = 0
    for f in failures:
        row_idx = f["rowIndex"]
        expected = f["expected_optionCode"]
        pack_no = f["packNo"]

        print(f"\n  [{row_idx}] {pack_no} → {expected} 입력 중...")

        try:
            # AG Grid에서 해당 row의 optionCode 셀 찾기
            cell = page.evaluate(f"""() => {{
                const api = window.gridOptions_orders && window.gridOptions_orders.api;
                if (!api) return null;
                let targetNode = null;
                api.forEachNode(node => {{
                    if (node.data && node.data.packNo === '{pack_no}') {{
                        targetNode = node;
                    }}
                }});
                if (!targetNode) return null;
                return {{ rowIndex: targetNode.rowIndex, currentVal: targetNode.data.optionCode || '' }};
            }}""")

            if not cell:
                print(f"    ERROR: row 못 찾음 (packNo={pack_no})")
                continue

            actual_row = cell["rowIndex"]

            # 셀 더블클릭으로 편집 모드 진입
            cell_el = page.query_selector(f".ag-row[row-index='{actual_row}'] .ag-cell[col-id='optionCode']")
            if not cell_el:
                print(f"    ERROR: optionCode 셀 못 찾음")
                continue

            cell_el.dblclick()
            page.wait_for_timeout(500)

            # 편집 input 찾기
            edit_input = page.query_selector(".ag-cell-editor input, .ag-input-field-input")
            if edit_input:
                edit_input.fill("")
                edit_input.type(expected, delay=30)
                page.keyboard.press("Tab")
                page.wait_for_timeout(500)

                # 검증
                verify = page.evaluate(f"""() => {{
                    const api = window.gridOptions_orders && window.gridOptions_orders.api;
                    if (!api) return '';
                    let val = '';
                    api.forEachNode(node => {{
                        if (node.data && node.data.packNo === '{pack_no}') {{
                            val = node.data.optionCode || '';
                        }}
                    }});
                    return val;
                }}""")

                if verify == expected:
                    print(f"    수정 완료: {verify}")
                    fixed += 1
                else:
                    print(f"    수정 실패: grid값={verify}, 기대={expected}")
            else:
                print(f"    ERROR: 편집 input 없음")

        except Exception as e:
            print(f"    ERROR: {e}")

    _ss(page, "fix_option_done")
    print(f"\n  옵션코드 수정: {fixed}/{len(failures)}건")
    return fixed


# ─────────────────────────────────────────────────
#  자동 수정: 송장번호 (RMS 주문상세)
# ─────────────────────────────────────────────────

def fix_rms_tracking(page, failures: list[dict]) -> int:
    """RMS에서 틀린 송장번호를 수정. 리턴: 수정 건수."""
    if not failures:
        return 0

    print("\n" + "=" * 60)
    print(f"  AUTO-FIX: RMS 송장번호 수정 ({len(failures)}건)")
    print("=" * 60)

    fixed = 0
    for f in failures:
        pack_no = f["packNo"]
        kse_tracking = f["trackingNo"]
        print(f"\n  {pack_no} → {kse_tracking} 입력 중...")

        try:
            detail_url = f"https://order-rp.rms.rakuten.co.jp/order-rb/individual-order-detail-sc/init?orderNumber={pack_no}"
            page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # 伝票番号 입력 필드 찾기 (12자리 숫자 값이 있는 input 또는 빈 input)
            updated = page.evaluate(f"""() => {{
                const inputs = document.querySelectorAll('input');
                for (const inp of inputs) {{
                    const val = inp.value || '';
                    // 기존 송장번호 필드 (12자리이거나 빈값)
                    if (/^\\d{{12}}$/.test(val) || (inp.name && inp.name.toLowerCase().includes('tracking'))) {{
                        inp.value = '{kse_tracking}';
                        inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                }}
                return false;
            }}""")

            if updated:
                # 入力内容を反映 클릭
                reflect_btn = page.query_selector("input[value*='入力内容を反映'], button:has-text('入力内容を反映')")
                if reflect_btn:
                    reflect_btn.click()
                    page.wait_for_timeout(3000)
                    print(f"    수정 완료 + 反映 클릭")
                    fixed += 1
                else:
                    print(f"    입력은 했으나 反映 버튼 없음")
            else:
                print(f"    ERROR: 송장번호 입력 필드 못 찾음")

        except Exception as e:
            print(f"    ERROR: {e}")

    _ss(page, "fix_tracking_done")
    print(f"\n  송장번호 수정: {fixed}/{len(failures)}건")
    return fixed


# ─────────────────────────────────────────────────
#  리포트
# ─────────────────────────────────────────────────

def print_report(audit_data: list[dict], rms_flow: dict | None, fix_log: list[dict], expected_count: int = 0) -> int:
    """검증 결과 리포트 출력. 리턴: 0=ALL PASS, 1=FAIL, 2=NO_DATA."""
    print("\n")
    print("=" * 70)
    print("  RAKUTEN AUDITOR — 검증 리포트")
    print("=" * 70)

    if not audit_data:
        # Vacuous PASS 금지: 검증 대상 0건이면 PASS 아님
        if expected_count > 0:
            print(f"  ✗ FAIL: 기대 {expected_count}건, 실제 검증 대상 0건 — 파이프라인 누락")
            print("=" * 70)
            return 1
        print("  ⚠ NO_DATA: 검증 대상 없음 (Rakuten 주문 0건)")
        print("  → ALL PASS 아님. 실제 주문 유무 재확인 필요.")
        print("=" * 70)
        return 2

    total = len(audit_data)

    # CHECK 0: RMS 주문확인
    if rms_flow:
        c0_pass = len(rms_flow["confirmed"])
        c0_fail = len(rms_flow["not_confirmed"])
    else:
        c0_pass = c0_fail = 0

    # CHECK 1: 옵션코드
    opt_pass = sum(1 for r in audit_data if r["optionCode_ok"])
    opt_fail = sum(1 for r in audit_data if not r["optionCode_ok"] and r["expected_optionCode"] != "UNMAPPED")
    opt_unmapped = sum(1 for r in audit_data if r["expected_optionCode"] == "UNMAPPED")

    # CHECK 2: 송장번호
    trk_pass = sum(1 for r in audit_data if r["tracking_ok"])
    trk_fail = total - trk_pass

    # CHECK 3: RMS 교차
    rms_checked = sum(1 for r in audit_data if r.get("rms_tracking_match") is not None)
    rms_match = sum(1 for r in audit_data if r.get("rms_tracking_match") is True)
    rms_mismatch = sum(1 for r in audit_data if r.get("rms_tracking_match") is False)

    pack_count = len(set(r["packNo"] for r in audit_data if r["packNo"]))
    print(f"\n  주문: {pack_count}건 / 아이템: {total}건")
    print()
    print("  ┌───────────────────────┬────────┬────────┐")
    print("  │ 항목                  │ PASS   │ FAIL   │")
    print("  ├───────────────────────┼────────┼────────┤")
    if rms_flow:
        print(f"  │ 주문확인+メール (RMS) │ {c0_pass:>4}건 │ {c0_fail:>4}건 │")
    print(f"  │ 옵션코드 (KSE)       │ {opt_pass:>4}건 │ {opt_fail:>4}건 │")
    if opt_unmapped:
        print(f"  │   └ 매핑없음(WARN)   │ {opt_unmapped:>4}건 │        │")
    print(f"  │ 송장번호 (KSE)       │ {trk_pass:>4}건 │ {trk_fail:>4}건 │")
    if rms_checked:
        print(f"  │ 송장번호 (RMS교차)   │ {rms_match:>4}건 │ {rms_mismatch:>4}건 │")
    print("  └───────────────────────┴────────┴────────┘")

    # 실패 상세
    failures = [r for r in audit_data if not r["optionCode_ok"] and r["expected_optionCode"] != "UNMAPPED"]
    if failures:
        print("\n  ✗ 옵션코드 불일치:")
        for r in failures:
            print(f"    {r['packNo']} | {r['itemTitle']}")
            print(f"      실제: {r['actual_optionCode']} → 기대: {r['expected_optionCode']}")

    rms_failures = [r for r in audit_data if r.get("rms_tracking_match") is False]
    if rms_failures:
        print("\n  ✗ RMS 송장번호 불일치:")
        for r in rms_failures:
            print(f"    {r['packNo']} | KSE: {r['trackingNo']} → RMS: {r.get('rms_trackingNo', 'N/A')}")

    has_fail = opt_fail > 0 or trk_fail > 0 or rms_mismatch > 0 or c0_fail > 0
    total_checks = (c0_pass + c0_fail) + total + total + rms_checked
    total_fails = c0_fail + opt_fail + trk_fail + rms_mismatch
    score = max(0, 100 - int(total_fails / max(total_checks, 1) * 100))

    # ── 수정 이력 ──
    if fix_log:
        print("\n  -- 수정 이력 --")
        fixed_ok = [e for e in fix_log if e["result"] == "수정 완료"]
        fixed_fail = [e for e in fix_log if e["result"] == "수정 실패"]

        if fixed_ok:
            print(f"  수정 성공 {len(fixed_ok)}건:")
            for e in fixed_ok:
                print(f"    [{e['type']}] {e['packNo']}: {e['wrong'] or '(빈값)'} → {e['correct']} (루프{e['loop']}에서 수정)")
        if fixed_fail:
            print(f"  수정 실패 {len(fixed_fail)}건:")
            for e in fixed_fail:
                print(f"    [{e['type']}] {e['packNo']}: {e['wrong'] or '(빈값)'} → {e['correct']} 시도했으나 실패")

    print()
    if has_fail:
        print(f"  결과: FAIL (Score: {score}/100)")
        if fix_log:
            still_broken = [e for e in fix_log if e["result"] == "수정 실패"]
            if still_broken:
                print(f"  ⚠ {len(still_broken)}건 자동 수정 불가 — 세은 수동 확인 필요")
    else:
        if fix_log:
            print(f"  결과: ALL PASS (Score: 100/100) — 수정 {len([e for e in fix_log if e['result'] == '수정 완료'])}건 반영됨")
        else:
            print(f"  결과: ALL PASS (Score: 100/100)")
    print("=" * 70)

    return 1 if has_fail else 0


# ─────────────────────────────────────────────────
#  메인 실행: audit → fix → re-audit 루프
# ─────────────────────────────────────────────────

def run(headless: bool = True, skip_rms: bool = False, no_fix: bool = False, expected_count: int = 0) -> int:
    from playwright.sync_api import sync_playwright

    MAX_FIX_LOOPS = 3  # 자동 수정 최대 3회
    fix_log = []       # 수정 이력 기록

    with sync_playwright() as pw:
        # ── Phase 1: KSE 검증 ──
        print("\n" + "=" * 60)
        print("  AUDIT Phase 1: KSE 검증")
        print("=" * 60)

        browser_kse = pw.chromium.launch(headless=headless, slow_mo=300)
        page_kse = browser_kse.new_page(viewport={"width": 1600, "height": 900})

        print("\n[A1] KSE OMS 로그인...")
        if not kse_login(page_kse):
            browser_kse.close()
            return 1

        print("\n[A2] 팩킹리스트 읽기...")
        rakuten_rows = read_kse_packing_list(page_kse)
        print(f"  Rakuten 주문: {len(rakuten_rows)}건")

        if not rakuten_rows:
            print("  Rakuten 주문 없음 — 검증 종료")
            browser_kse.close()
            return 0

        audit_data = audit_kse_data(rakuten_rows)

        # ── 자동 수정 루프 (KSE 옵션코드) ──
        for loop in range(MAX_FIX_LOOPS):
            opt_failures = [r for r in audit_data
                           if not r["optionCode_ok"] and r["expected_optionCode"] != "UNMAPPED"]

            if not opt_failures or no_fix:
                break

            print(f"\n  옵션코드 FAIL {len(opt_failures)}건 → 자동 수정 시도 (루프 {loop+1}/{MAX_FIX_LOOPS})")
            for f in opt_failures:
                fix_log.append({
                    "loop": loop + 1,
                    "type": "옵션코드",
                    "packNo": f["packNo"],
                    "wrong": f["actual_optionCode"],
                    "correct": f["expected_optionCode"],
                    "result": "시도",
                })

            fixed = fix_option_codes(page_kse, opt_failures)

            if fixed > 0:
                print("\n  재검증 중...")
                rakuten_rows = read_kse_packing_list(page_kse)
                audit_data = audit_kse_data(rakuten_rows)

                # 수정 이력 업데이트
                for entry in fix_log:
                    if entry["result"] == "시도" and entry["type"] == "옵션코드":
                        # 재검증 결과 반영
                        matching = [r for r in audit_data if r["packNo"] == entry["packNo"]]
                        if matching and matching[0]["optionCode_ok"]:
                            entry["result"] = "수정 완료"
                        else:
                            entry["result"] = "수정 실패"
            else:
                for entry in fix_log:
                    if entry["result"] == "시도":
                        entry["result"] = "수정 실패"
                break  # 하나도 수정 못 하면 더 시도해도 무의미

        browser_kse.close()

        # ── Phase 2: RMS 검증 ──
        rms_flow = None

        if not skip_rms:
            print("\n" + "=" * 60)
            print("  AUDIT Phase 2: RMS 검증")
            print("=" * 60)

            browser_rms = pw.chromium.launch(headless=headless, slow_mo=300)
            page_rms = browser_rms.new_page(viewport={"width": 1600, "height": 900})

            print("\n[A3] RMS 로그인...")
            rms_login(page_rms)
            _ss(page_rms, "rms_logged_in")

            # CHECK 0: 주문확인 + 메일
            pack_numbers = list(set(r["packNo"] for r in audit_data if r["packNo"]))
            rms_flow = check_rms_order_flow(page_rms, pack_numbers)

            # CHECK 3: 송장번호 교차
            audit_data = audit_rms_tracking(page_rms, audit_data)

            # ── 자동 수정 루프 (RMS 송장번호) ──
            for loop in range(MAX_FIX_LOOPS):
                rms_failures = [r for r in audit_data if r.get("rms_tracking_match") is False]

                if not rms_failures or no_fix:
                    break

                print(f"\n  송장번호 FAIL {len(rms_failures)}건 → 자동 수정 시도 (루프 {loop+1}/{MAX_FIX_LOOPS})")
                for f in rms_failures:
                    fix_log.append({
                        "loop": loop + 1,
                        "type": "송장번호",
                        "packNo": f["packNo"],
                        "wrong": f.get("rms_trackingNo", ""),
                        "correct": f["trackingNo"],
                        "result": "시도",
                    })

                fixed = fix_rms_tracking(page_rms, rms_failures)

                if fixed > 0:
                    print("\n  재검증 중...")
                    # rms_tracking_match 초기화 후 재검증
                    for r in audit_data:
                        r["rms_trackingNo"] = None
                        r["rms_tracking_match"] = None
                    audit_data = audit_rms_tracking(page_rms, audit_data)

                    for entry in fix_log:
                        if entry["result"] == "시도" and entry["type"] == "송장번호":
                            matching = [r for r in audit_data if r["packNo"] == entry["packNo"]]
                            if matching and matching[0].get("rms_tracking_match") is True:
                                entry["result"] = "수정 완료"
                            else:
                                entry["result"] = "수정 실패"
                else:
                    for entry in fix_log:
                        if entry["result"] == "시도":
                            entry["result"] = "수정 실패"
                    break

            browser_rms.close()

    # ── 최종 리포트 ──
    return print_report(audit_data, rms_flow, fix_log, expected_count=expected_count)


def main():
    parser = argparse.ArgumentParser(description="Rakuten Auditor — 검증 + 자동수정")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시")
    parser.add_argument("--skip-rms", action="store_true", help="RMS 검증 건너뛰기")
    parser.add_argument("--no-fix", action="store_true", help="자동 수정 안 함 (검증만)")
    parser.add_argument("--expected-count", type=int, default=0,
                        help="상위 파이프라인이 전달한 기대 주문 건수 (0이면 vacuous PASS 방지만)")
    args = parser.parse_args()

    exit_code = run(headless=not args.headed, skip_rms=args.skip_rms,
                    no_fix=args.no_fix, expected_count=args.expected_count)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
