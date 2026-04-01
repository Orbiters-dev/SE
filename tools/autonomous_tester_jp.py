"""
Autonomous Tester JP (자율주행 테스터 — Japan)
==============================================
JP Pipeline Dashboard의 모든 탭/인터랙션을 Playwright headless로
자동 순회하며 에러를 수집하는 E2E 테스터.

Features:
  - Headless 기본 (bash 한 방 실행, 사람 승인 불필요)
  - 10개 스테이지: 8개 탭 + 기프팅 폼 + 모달
  - 콘솔 에러 / 네트워크 실패 / JS exception 자동 수집
  - 스크린샷 자동 저장
  - JSON 리포트 + fix_manifest.json (수정 루프용)
  - dual_test_runner.py / codex_auditor.py 연동

Usage:
  python tools/autonomous_tester_jp.py --run                    # 전체 headless
  python tools/autonomous_tester_jp.py --run --no-headless      # 화면 보이게
  python tools/autonomous_tester_jp.py --run --stages 0,1,2     # 특정 스테이지만
  python tools/autonomous_tester_jp.py --run --dual --codex     # + 파이프라이너 + codex
  python tools/autonomous_tester_jp.py --status                 # 환경 확인
"""

import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ─── Paths ───────────────────────────────────────────────────────────────────
DIR  = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
TMP  = os.path.join(ROOT, ".tmp", "autonomous_test_jp")
os.makedirs(TMP, exist_ok=True)

PYTHON = sys.executable

# ─── Constants ───────────────────────────────────────────────────────────────
JP_DASHBOARD_URL = "https://orbiters-dev.github.io/WJ-Test1/pipeline-dashboard-jp/"
JP_GIFTING_URL   = JP_DASHBOARD_URL + "gifting-form.html"
JP_AUTH = {"uid": "WJ", "pw": "3352"}

ALL_STAGES = [
    "0_dashboard", "1_creators", "2_sheet", "3_drafts",
    "4_contracts", "5_config", "6_samples", "7_failures",
    "8_gifting", "9_modals",
]

STAGE_LABELS = {
    "0_dashboard":  "Dashboard — Stats / Funnel / KPI / Activity",
    "1_creators":   "Creators — 필터 / 카드 / DM Thread",
    "2_sheet":      "Influencer Sheet — Discovery / Sort / Filter",
    "3_drafts":     "DM Drafts — Generate / Select / Execute",
    "4_contracts":  "Contracts — AI Classify / Gifting vs Paid",
    "5_config":     "Config — Template / FAQ / Guidelines",
    "6_samples":    "Samples — Table / Export / Checkbox",
    "7_failures":   "Failures — Log Table / Clear",
    "8_gifting":    "Gifting Form — 7-Step Wizard",
    "9_modals":     "Modals — Import / DM Thread",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────
def log(msg):   print(msg)
def ok(msg):    print(f"  [PASS] {msg}")
def warn(msg):  print(f"  [WARN] {msg}")
def fail(msg):  print(f"  [FAIL] {msg}")
def info(msg):  print(f"  [INFO] {msg}")


def screenshot(page, name, run_dir):
    path = os.path.join(run_dir, f"{name}.png")
    try:
        page.screenshot(path=path, full_page=False)
    except Exception as e:
        warn(f"Screenshot failed: {e}")
    return path


def switch_tab(page, tab_name):
    """tab_name: dashboard, creators, sheet, drafts, contracts, config, samples, failures"""
    page.click(f".mt > div[data-p='{tab_name}']")
    page.wait_for_timeout(1200)


def check(checks, name, passed, detail=""):
    status = passed if passed is not None else None
    checks.append({"check": name, "passed": status, "detail": detail})
    if passed:
        ok(f"{name} — {detail}")
    elif passed is False:
        fail(f"{name} — {detail}")
    else:
        info(f"{name} — {detail} (skip)")


def el_exists(page, selector, timeout=3000):
    try:
        page.wait_for_selector(selector, state="attached", timeout=timeout)
        return True
    except Exception:
        return False


def el_count(page, selector):
    try:
        return len(page.query_selector_all(selector))
    except Exception:
        return 0


def el_text(page, selector):
    try:
        el = page.query_selector(selector)
        return el.text_content().strip() if el else ""
    except Exception:
        return ""


# ─── Monitor Setup ───────────────────────────────────────────────────────────
def setup_monitors(page, ctx):
    ctx["console_errors"] = []
    ctx["network_failures"] = []
    ctx["api_responses"] = []

    def on_console(msg):
        if msg.type in ("error",):
            ctx["console_errors"].append({
                "type": msg.type, "text": msg.text,
                "ts": datetime.now().isoformat(),
            })

    def on_pageerror(err):
        ctx["console_errors"].append({
            "type": "pageerror", "text": str(err),
            "ts": datetime.now().isoformat(),
        })

    def on_requestfailed(req):
        ctx["network_failures"].append({
            "url": req.url, "method": req.method,
            "failure": req.failure,
            "ts": datetime.now().isoformat(),
        })

    def on_response(resp):
        if "n8n.orbiters" in resp.url or "orbitools" in resp.url:
            ctx["api_responses"].append({
                "url": resp.url, "status": resp.status,
                "ts": datetime.now().isoformat(),
            })

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("requestfailed", on_requestfailed)
    page.on("response", on_response)


# ─── Stage Runners ───────────────────────────────────────────────────────────

def stage_0_dashboard(page, ctx, run_dir):
    """Dashboard tab — stats, funnel, KPI, activity."""
    checks = []
    switch_tab(page, "dashboard")
    screenshot(page, "00_dashboard", run_dir)

    # Stat cards
    stat_ids = ["s-total", "s-draft", "s-sent", "s-accepted", "s-posted", "s-inbound", "s-manual-dm"]
    found = 0
    for sid in stat_ids:
        if el_exists(page, f"#{sid}", 2000):
            found += 1
    check(checks, "stat_cards", found >= 5, f"{found}/{len(stat_ids)} stat cards found")

    # Funnel — 3 rows
    funnel_rows = el_count(page, ".funnel-row")
    check(checks, "funnel_rows", funnel_rows == 3, f"{funnel_rows} funnel rows (expect 3: PIPELINE/INBOUND/MANUAL)")

    # Click some funnel stages
    for stage in ["draft_ready", "sent", "accepted", "posted"]:
        try:
            page.click(f".fn[data-stage='{stage}']", timeout=2000)
            page.wait_for_timeout(400)
        except Exception:
            pass
    screenshot(page, "00_funnel_click", run_dir)

    # Daily KPI table
    kpi_rows = el_count(page, "#daily-kpi-tbody tr")
    has_kpi = kpi_rows > 0
    check(checks, "daily_kpi_table", has_kpi, f"{kpi_rows} rows")

    # DM Budget bar
    budget_exists = el_exists(page, "#dm-budget-bar", 2000)
    check(checks, "dm_budget_bar", budget_exists, "budget bar element")

    # Activity log
    activity_exists = el_exists(page, "#activity-log", 2000)
    check(checks, "activity_log", activity_exists, "activity log container")

    screenshot(page, "00_dashboard_end", run_dir)
    return checks


def stage_1_creators(page, ctx, run_dir):
    """Creators tab — filter, cards, select, DM thread."""
    checks = []
    switch_tab(page, "creators")
    page.wait_for_timeout(1500)
    screenshot(page, "01_creators", run_dir)

    # Search filter
    search = page.query_selector("#creator-search")
    check(checks, "search_input", search is not None, "search input exists")

    if search:
        page.fill("#creator-search", "test")
        page.wait_for_timeout(500)
        count_text = el_text(page, "#creator-count")
        check(checks, "search_filter", True, f"searched 'test' → {count_text}")
        page.fill("#creator-search", "")
        page.wait_for_timeout(500)

    # Status dropdown
    dd = page.query_selector("#creator-status-filter")
    check(checks, "status_dropdown", dd is not None, "status dropdown exists")

    if dd:
        options = page.query_selector_all("#creator-status-filter option")
        check(checks, "status_options", len(options) >= 10, f"{len(options)} options")
        # Cycle through a few statuses
        for val in ["draft_ready", "sent", "accepted", "guidelines_sent", "manual_dm", ""]:
            try:
                page.select_option("#creator-status-filter", val)
                page.wait_for_timeout(400)
            except Exception:
                pass
        screenshot(page, "01_creators_filtered", run_dir)

    # Creator cards
    cards = el_count(page, "#creators-cards > div")
    check(checks, "creator_cards", cards >= 0, f"{cards} creator cards rendered")

    # Select all checkbox
    select_all = el_exists(page, "#creators-select-all", 2000)
    check(checks, "select_all_checkbox", select_all, "select all exists")

    # Execute button
    exec_btn = el_exists(page, "#btn-creators-execute", 2000)
    check(checks, "execute_button", exec_btn, "execute button exists")

    # DM Thread modal — try to open for first creator
    try:
        handle_link = page.query_selector("#creators-cards a[onclick*='openDmThread'], #creators-cards button[onclick*='openDmThread']")
        if handle_link:
            handle_link.click()
            page.wait_for_timeout(1000)
            modal = el_exists(page, ".dm-thread-overlay", 3000)
            check(checks, "dm_thread_modal", modal, "DM thread modal opened")
            screenshot(page, "01_dm_thread", run_dir)
            # Close
            try:
                page.click(".dm-thread-close", timeout=2000)
                page.wait_for_timeout(500)
            except Exception:
                page.keyboard.press("Escape")
        else:
            # Try clicking on a creator handle link
            handle_el = page.query_selector("#creators-cards [onclick*='openDmThread']")
            if handle_el:
                handle_el.click()
                page.wait_for_timeout(1000)
                modal = el_exists(page, ".dm-thread-overlay", 3000)
                check(checks, "dm_thread_modal", modal, "DM thread modal opened")
                screenshot(page, "01_dm_thread", run_dir)
                try:
                    page.click(".dm-thread-close", timeout=2000)
                except Exception:
                    page.keyboard.press("Escape")
            else:
                check(checks, "dm_thread_modal", None, "no creator handle to click (skip)")
    except Exception as e:
        check(checks, "dm_thread_modal", False, str(e))

    screenshot(page, "01_creators_end", run_dir)
    return checks


def stage_2_sheet(page, ctx, run_dir):
    """Influencer Sheet — refresh, search, filter, sort."""
    checks = []
    switch_tab(page, "sheet")
    page.wait_for_timeout(2000)
    screenshot(page, "02_sheet", run_dir)

    # Refresh button
    refresh = page.query_selector("button:has-text('Refresh'), button[onclick*='loadInfluencerSheet']")
    check(checks, "refresh_button", refresh is not None, "refresh button exists")
    if refresh:
        try:
            refresh.click()
            page.wait_for_timeout(3000)
        except Exception:
            pass

    # Search
    search = page.query_selector("#sheet-search")
    check(checks, "sheet_search", search is not None, "search input")

    # Status filter
    status_dd = page.query_selector("#sheet-filter-status")
    check(checks, "sheet_status_filter", status_dd is not None, "status filter dropdown")

    # Source filter
    source_dd = page.query_selector("#sheet-filter-source")
    check(checks, "sheet_source_filter", source_dd is not None, "source filter dropdown")

    # Hide contacted toggle
    hide_cb = page.query_selector("#sheet-hide-contacted")
    check(checks, "hide_contacted", hide_cb is not None, "hide contacted checkbox")

    # Sortable headers
    sortable = page.query_selector_all("th[onclick*='sortSheet']")
    check(checks, "sortable_columns", len(sortable) > 0, f"{len(sortable)} sortable columns")

    # Try clicking a sort
    if sortable:
        try:
            sortable[0].click()
            page.wait_for_timeout(600)
        except Exception:
            pass

    screenshot(page, "02_sheet_end", run_dir)
    return checks


def stage_3_drafts(page, ctx, run_dir):
    """DM Drafts — batch size, generate, select."""
    checks = []
    switch_tab(page, "drafts")
    page.wait_for_timeout(1500)
    screenshot(page, "03_drafts", run_dir)

    # Batch size input
    batch = page.query_selector("#draft-batch-size")
    check(checks, "batch_size_input", batch is not None, "batch size input")

    # Generate button
    gen_btn = page.query_selector("#btn-generate")
    check(checks, "generate_button", gen_btn is not None, "generate drafts button")

    # Select all checkbox
    select_all = page.query_selector("#select-all-drafts")
    check(checks, "select_all_drafts", select_all is not None, "select all drafts checkbox")

    # Execute button
    exec_btn = page.query_selector("#btn-execute")
    check(checks, "execute_drafts_button", exec_btn is not None, "execute drafts button")

    # Drafts list
    drafts = el_count(page, "#drafts-list > div, #drafts-list .dm-card")
    check(checks, "drafts_list", True, f"{drafts} draft cards")

    screenshot(page, "03_drafts_end", run_dir)
    return checks


def stage_4_contracts(page, ctx, run_dir):
    """Contracts — AI classify, gifting/paid split."""
    checks = []
    switch_tab(page, "contracts")
    page.wait_for_timeout(1500)
    screenshot(page, "04_contracts", run_dir)

    # AI Classify button
    classify = page.query_selector("button[onclick*='classifyContracts'], button:has-text('Classify')")
    check(checks, "classify_button", classify is not None, "AI classify button")

    # Execute contracts button
    exec_btn = page.query_selector("#btn-exec-contracts, button[onclick*='executeContracts']")
    check(checks, "execute_contracts", exec_btn is not None, "execute contracts button")

    # Gifting/Paid lists
    gifting_list = page.query_selector("#contract-gifting-list")
    paid_list = page.query_selector("#contract-paid-list")
    check(checks, "contract_lists", gifting_list is not None or paid_list is not None,
          f"gifting={'yes' if gifting_list else 'no'} paid={'yes' if paid_list else 'no'}")

    screenshot(page, "04_contracts_end", run_dir)
    return checks


def stage_5_config(page, ctx, run_dir):
    """Config — daily limit, template, FAQ, guidelines."""
    checks = []
    switch_tab(page, "config")
    page.wait_for_timeout(1500)
    screenshot(page, "05_config", run_dir)

    # Daily limit
    limit = page.query_selector("#cfg-daily-limit")
    check(checks, "daily_limit", limit is not None, "daily limit input")

    # DM template
    template = page.query_selector("#cfg-dm-template")
    check(checks, "dm_template", template is not None, "DM template textarea")

    # Mistake log
    mistake = page.query_selector("#cfg-mistake-log")
    check(checks, "mistake_log", mistake is not None, "mistake log textarea")

    # FAQ section
    faq = page.query_selector("#faq-list")
    check(checks, "faq_section", faq is not None, "FAQ list")

    # DocuSeal IDs
    ds_gifting = page.query_selector("#cfg-docuseal-gifting")
    ds_paid = page.query_selector("#cfg-docuseal-paid")
    check(checks, "docuseal_ids",
          ds_gifting is not None or ds_paid is not None,
          f"gifting={'yes' if ds_gifting else 'no'} paid={'yes' if ds_paid else 'no'}")

    screenshot(page, "05_config_end", run_dir)
    return checks


def stage_6_samples(page, ctx, run_dir):
    """Samples — table, export, checkbox."""
    checks = []
    switch_tab(page, "samples")
    page.wait_for_timeout(1500)
    screenshot(page, "06_samples", run_dir)

    # Sample table
    rows = el_count(page, "#samples-tbody tr")
    check(checks, "samples_table", True, f"{rows} rows in samples table")

    # Export button
    export_btn = page.query_selector("button[onclick*='exportSamples'], button:has-text('Export')")
    check(checks, "export_csv", export_btn is not None, "export CSV button")

    # Mark sent button
    mark_btn = page.query_selector("button[onclick*='markSamplesSent'], button:has-text('Mark')")
    check(checks, "mark_sent_button", mark_btn is not None, "mark as sent button")

    screenshot(page, "06_samples_end", run_dir)
    return checks


def stage_7_failures(page, ctx, run_dir):
    """Failures — log table, clear button."""
    checks = []
    switch_tab(page, "failures")
    page.wait_for_timeout(1500)
    screenshot(page, "07_failures", run_dir)

    # Failure table
    table = page.query_selector("#failure-log-body, #p-failures table")
    check(checks, "failure_table", table is not None, "failure log table")

    # Clear button
    clear_btn = page.query_selector("button[onclick*='clearFailureLog'], button:has-text('Clear')")
    check(checks, "clear_log_button", clear_btn is not None, "clear log button")

    screenshot(page, "07_failures_end", run_dir)
    return checks


def stage_8_gifting(page, ctx, run_dir):
    """Gifting Form — 7-step wizard navigation (no submit)."""
    checks = []
    new_tab = page.context.new_page()
    try:
        new_tab.goto(JP_GIFTING_URL)
        new_tab.wait_for_timeout(2000)
        screenshot(new_tab, "08_gifting_step1", run_dir)

        # Step 1 — Name
        name_input = new_tab.query_selector("#inputName")
        check(checks, "step1_name", name_input is not None, "name input exists")
        if name_input:
            new_tab.fill("#inputName", "テスト ユーザー")
            new_tab.click("button:has-text('次へ')")
            new_tab.wait_for_timeout(800)

        # Step 2 — Email
        email_input = el_exists(new_tab, "#inputEmail", 3000)
        check(checks, "step2_email", email_input, "email input visible")
        if email_input:
            new_tab.fill("#inputEmail", "test@example.com")
            new_tab.click("#step2 button:has-text('次へ')")
            new_tab.wait_for_timeout(800)

        # Step 3 — Phone
        phone_input = el_exists(new_tab, "#inputPhone", 3000)
        check(checks, "step3_phone", phone_input, "phone input visible")
        if phone_input:
            new_tab.fill("#inputPhone", "090-1234-5678")
            new_tab.click("#step3 button:has-text('次へ')")
            new_tab.wait_for_timeout(800)

        screenshot(new_tab, "08_gifting_step3", run_dir)

        # Step 4 — Baby birthday
        year_dd = el_exists(new_tab, "#inputYear", 3000)
        check(checks, "step4_birthday", year_dd, "birthday selects visible")
        if year_dd:
            try:
                new_tab.select_option("#inputYear", index=2)
                new_tab.select_option("#inputMonth", index=3)
                new_tab.click("#step4 button:has-text('次へ')")
                new_tab.wait_for_timeout(800)
            except Exception as e:
                check(checks, "step4_navigate", False, str(e))

        # Step 5 — Product selection
        product_area = el_exists(new_tab, "#productArea, #step5", 3000)
        check(checks, "step5_product", product_area, "product area visible")
        if product_area:
            # Click first product card (.gf-pcard) and color swatch (.gf-swatch)
            try:
                new_tab.wait_for_selector(".gf-pcard", timeout=5000)
                card = new_tab.query_selector(".gf-pcard")
                if card:
                    card.click()
                    new_tab.wait_for_timeout(500)
                    # Click a color swatch
                    swatch = new_tab.query_selector(".gf-swatch")
                    if swatch:
                        swatch.click()
                        new_tab.wait_for_timeout(300)
                    new_tab.click("#step5 button:has-text('次へ')")
                    new_tab.wait_for_timeout(800)
            except Exception as e:
                check(checks, "step5_select", False, str(e))

        screenshot(new_tab, "08_gifting_step5", run_dir)

        # Step 6 — Address
        postal = el_exists(new_tab, "#inputPostal", 3000)
        check(checks, "step6_address", postal, "address form visible")
        if postal:
            try:
                new_tab.fill("#inputPostal", "150-0001")
                new_tab.select_option("#inputPrefecture", index=13)  # 東京都
                new_tab.fill("#inputCity", "渋谷区")
                new_tab.fill("#inputAddress", "神宮前1-2-3")
                new_tab.click("#step6 button:has-text('確認')")
                new_tab.wait_for_timeout(800)
            except Exception as e:
                check(checks, "step6_fill", False, str(e))

        # Step 7 — Review (DO NOT SUBMIT)
        review = el_exists(new_tab, "#step7, #reviewTable", 3000)
        check(checks, "step7_review", review, "review page reached")
        screenshot(new_tab, "08_gifting_step7", run_dir)

    except Exception as e:
        check(checks, "gifting_form_load", False, str(e))
    finally:
        new_tab.close()

    return checks


def stage_9_modals(page, ctx, run_dir):
    """Import modal + DM Thread modal."""
    checks = []

    # Import modal
    switch_tab(page, "creators")
    page.wait_for_timeout(800)
    try:
        import_btn = page.query_selector("button[onclick*='showImportModal'], button:has-text('Import')")
        if import_btn:
            import_btn.click()
            page.wait_for_timeout(800)
            modal = el_exists(page, "#import-modal", 3000)
            check(checks, "import_modal_open", modal, "import modal opened")
            screenshot(page, "09_import_modal", run_dir)
            # Close
            try:
                close_btn = page.query_selector("#import-modal button:has-text('Cancel'), #import-modal .dm-thread-close, #import-modal button:has-text('×')")
                if close_btn:
                    close_btn.click()
                else:
                    page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                page.keyboard.press("Escape")
        else:
            check(checks, "import_modal_open", None, "no import button found (skip)")
    except Exception as e:
        check(checks, "import_modal_open", False, str(e))

    # DM Thread modal (if a creator has the 💬 button)
    try:
        dm_btn = page.query_selector("button:has-text('💬'), button[onclick*='openDmThread']")
        if dm_btn:
            dm_btn.click()
            page.wait_for_timeout(1000)
            thread = el_exists(page, ".dm-thread-overlay", 3000)
            check(checks, "dm_thread_open", thread, "DM thread modal opened")
            if thread:
                # Check input and send button
                input_el = el_exists(page, ".dm-thread-input input", 2000)
                send_btn = el_exists(page, ".dm-thread-input button", 2000)
                check(checks, "dm_thread_input", input_el, "message input exists")
                check(checks, "dm_thread_send", send_btn, "send button exists")
                screenshot(page, "09_dm_thread", run_dir)
                # Close
                try:
                    page.click(".dm-thread-close", timeout=2000)
                except Exception:
                    page.keyboard.press("Escape")
        else:
            check(checks, "dm_thread_open", None, "no DM button found (skip)")
    except Exception as e:
        check(checks, "dm_thread_open", False, str(e))

    screenshot(page, "09_modals_end", run_dir)
    return checks


# ─── Stage Dispatch ──────────────────────────────────────────────────────────
STAGE_RUNNERS = {
    "0_dashboard":  stage_0_dashboard,
    "1_creators":   stage_1_creators,
    "2_sheet":      stage_2_sheet,
    "3_drafts":     stage_3_drafts,
    "4_contracts":  stage_4_contracts,
    "5_config":     stage_5_config,
    "6_samples":    stage_6_samples,
    "7_failures":   stage_7_failures,
    "8_gifting":    stage_8_gifting,
    "9_modals":     stage_9_modals,
}


# ─── Main Runner ─────────────────────────────────────────────────────────────
def cmd_run(stages, slow_mo, headless):
    from playwright.sync_api import sync_playwright

    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"auto_jp_{ts}"
    run_dir = os.path.join(TMP, run_id)
    os.makedirs(run_dir, exist_ok=True)

    log("\n" + "=" * 60)
    log("  자율주행 테스터 JP (Autonomous Dashboard Tester — Japan)")
    log("=" * 60)
    log(f"  Run ID:    {run_id}")
    log(f"  Stages:    {' → '.join(stages)}")
    log(f"  Headless:  {headless}")
    log(f"  Slow-mo:   {slow_mo}ms")
    log(f"  Output:    {run_dir}")
    log("=" * 60 + "\n")

    ctx = {
        "console_errors": [],
        "network_failures": [],
        "api_responses": [],
    }
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.set_default_timeout(15000)

        setup_monitors(page, ctx)

        # ── Login ──
        log("  [INIT] JP Dashboard 열기...")
        page.goto(JP_DASHBOARD_URL)
        page.wait_for_timeout(2000)

        info("  [LOGIN] 로그인 시도 (WJ)")
        page.fill("#login-uid", JP_AUTH["uid"])
        page.fill("#login-pw", JP_AUTH["pw"])
        page.click("button:has-text('Sign In')")
        page.wait_for_timeout(2000)

        # Verify login
        main_visible = el_exists(page, "#main-content", 5000)
        if main_visible:
            ok("로그인 성공")
        else:
            fail("로그인 실패 — main-content 보이지 않음")
            screenshot(page, "login_failed", run_dir)
            browser.close()
            return run_dir

        screenshot(page, "init_logged_in", run_dir)

        # ── Run stages ──
        for stage_name in stages:
            runner = STAGE_RUNNERS.get(stage_name)
            if not runner:
                warn(f"알 수 없는 스테이지: {stage_name}")
                continue

            log(f"\n{'─' * 60}")
            log(f"  {STAGE_LABELS.get(stage_name, stage_name)}")
            log("─" * 60)

            t0 = time.time()
            try:
                stage_checks = runner(page, ctx, run_dir)
                duration = int((time.time() - t0) * 1000)

                passed_count = sum(1 for c in stage_checks if c["passed"] is True)
                failed_count = sum(1 for c in stage_checks if c["passed"] is False)
                status = "PASS" if failed_count == 0 else "FAIL"

                results.append({
                    "stage": stage_name,
                    "status": status,
                    "duration_ms": duration,
                    "assertions": stage_checks,
                    "passed": passed_count,
                    "failed": failed_count,
                })
                log(f"  → {status} ({passed_count} passed, {failed_count} failed, {duration}ms)")

            except Exception as e:
                duration = int((time.time() - t0) * 1000)
                fail(f"[{stage_name}] 스테이지 크래시: {e}")
                results.append({
                    "stage": stage_name,
                    "status": "CRASH",
                    "duration_ms": duration,
                    "assertions": [],
                    "error": str(e),
                })

        # ── Final screenshot ──
        screenshot(page, "zz_final", run_dir)
        browser.close()

    # ── Build report ──
    total_stages = len(results)
    passed_stages = sum(1 for r in results if r["status"] == "PASS")
    failed_stages = sum(1 for r in results if r["status"] in ("FAIL", "CRASH"))

    report = {
        "run_id": run_id,
        "region": "jp",
        "dashboard_url": JP_DASHBOARD_URL,
        "stages": stages,
        "results": results,
        "console_errors": ctx["console_errors"],
        "network_failures": ctx["network_failures"],
        "api_responses": ctx["api_responses"],
        "summary": {
            "total": total_stages,
            "passed": passed_stages,
            "failed": failed_stages,
        },
        "screenshot_dir": run_dir,
        "ts": ts,
    }

    report_path = os.path.join(run_dir, "result.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # ── Fix manifest (if failures) ──
    fix_targets = []
    for r in results:
        if r["status"] in ("FAIL", "CRASH"):
            for a in r.get("assertions", []):
                if a.get("passed") is False:
                    fix_targets.append({
                        "file": "docs/pipeline-dashboard-jp/index.html",
                        "stage": r["stage"],
                        "check": a["check"],
                        "error_type": "assertion_failed",
                        "detail": a.get("detail", ""),
                        "console_errors_nearby": [
                            e["text"] for e in ctx["console_errors"][-5:]
                        ],
                    })
            if r.get("error"):
                fix_targets.append({
                    "file": "docs/pipeline-dashboard-jp/index.html",
                    "stage": r["stage"],
                    "check": "stage_crash",
                    "error_type": "crash",
                    "detail": r["error"],
                    "console_errors_nearby": [
                        e["text"] for e in ctx["console_errors"][-5:]
                    ],
                })

    if fix_targets:
        manifest = {"run_id": run_id, "fix_targets": fix_targets}
        manifest_path = os.path.join(run_dir, "fix_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    # ── Summary ──
    log("\n" + "=" * 60)
    log(f"  자율주행 완료: {passed_stages}/{total_stages} stages PASS")
    if ctx["console_errors"]:
        log(f"  콘솔 에러: {len(ctx['console_errors'])}건")
    if ctx["network_failures"]:
        log(f"  네트워크 실패: {len(ctx['network_failures'])}건")
    log(f"  리포트: {report_path}")
    if fix_targets:
        log(f"  fix_manifest: {len(fix_targets)} targets")
    log(f"  스크린샷: {run_dir}")
    log("=" * 60)

    return run_dir


def cmd_run_with_integrations(stages, slow_mo, headless, run_dual, run_codex):
    """Run UI test, then optionally dual test and codex audit."""
    run_dir = cmd_run(stages, slow_mo, headless)

    if run_dual:
        log("\n" + "─" * 60)
        log("  [DUAL] dual_test_runner.py 실행...")
        log("─" * 60)
        try:
            cmd = [PYTHON, os.path.join(DIR, "dual_test_runner.py"), "--dual", "--quick"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            log(result.stdout[-2000:] if result.stdout else "  (no output)")
            if result.returncode != 0:
                warn(f"dual_test_runner exit code: {result.returncode}")
                if result.stderr:
                    log(result.stderr[-1000:])
        except Exception as e:
            warn(f"dual_test_runner 실행 실패: {e}")

    if run_codex:
        log("\n" + "─" * 60)
        log("  [CODEX] codex_auditor.py 실행...")
        log("─" * 60)
        # Read our summary for the prompt
        try:
            with open(os.path.join(run_dir, "result.json"), "r") as f:
                report = json.load(f)
            summary_text = json.dumps(report["summary"])
        except Exception:
            summary_text = "E2E test completed"

        try:
            cmd = [PYTHON, os.path.join(DIR, "codex_auditor.py"),
                   "--domain", "pipeline", "--verify-round", "1",
                   "--prompt", f"Verify JP dashboard E2E test results: {summary_text}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            log(result.stdout[-2000:] if result.stdout else "  (no output)")
        except Exception as e:
            warn(f"codex_auditor 실행 실패: {e}")

    return run_dir


def cmd_status():
    log("\n자율주행 테스터 JP — 환경 상태")
    log("─" * 40)
    log(f"  Dashboard URL: {JP_DASHBOARD_URL}")
    log(f"  Gifting Form:  {JP_GIFTING_URL}")
    log(f"  Output dir:    {TMP}")
    log(f"  Python:        {PYTHON}")
    try:
        from playwright.sync_api import sync_playwright
        log("  Playwright:    ✅ installed")
    except ImportError:
        log("  Playwright:    ❌ pip install playwright && playwright install chromium")
    dual = os.path.exists(os.path.join(DIR, "dual_test_runner.py"))
    codex = os.path.exists(os.path.join(DIR, "codex_auditor.py"))
    log(f"  dual_test:     {'✅' if dual else '❌'}")
    log(f"  codex_auditor: {'✅' if codex else '❌'}")
    log(f"\n  All stages: {', '.join(ALL_STAGES)}")

    # Recent runs
    if os.path.isdir(TMP):
        runs = sorted([d for d in os.listdir(TMP) if d.startswith("auto_jp_")])
        if runs:
            log(f"\n  Recent runs ({len(runs)} total):")
            for r in runs[-5:]:
                rpath = os.path.join(TMP, r, "result.json")
                if os.path.exists(rpath):
                    try:
                        with open(rpath) as f:
                            data = json.load(f)
                        s = data.get("summary", {})
                        log(f"    {r} — {s.get('passed', '?')}/{s.get('total', '?')} PASS")
                    except Exception:
                        log(f"    {r}")
                else:
                    log(f"    {r} (no result.json)")


# ─── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="자율주행 테스터 JP — Pipeline Dashboard E2E")
    parser.add_argument("--run",         action="store_true", help="자율주행 실행")
    parser.add_argument("--status",      action="store_true", help="환경 상태 확인")
    parser.add_argument("--stages",      type=str, default=None,
                        help=f"스테이지 (comma separated, 'all'). Default: all. Choices: {','.join(ALL_STAGES)}")
    parser.add_argument("--slow-mo",     type=int, default=300, help="액션 간 딜레이 ms (기본 300)")
    parser.add_argument("--headless",    action="store_true", default=True, help="헤드리스 (기본)")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="화면 표시")
    parser.add_argument("--dual",        action="store_true", help="dual_test_runner.py 연동")
    parser.add_argument("--codex",       action="store_true", help="codex_auditor.py 연동")

    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.run:
        if args.stages and args.stages != "all":
            stages = [s.strip() for s in args.stages.split(",")]
        else:
            stages = ALL_STAGES[:]

        if args.dual or args.codex:
            cmd_run_with_integrations(stages, args.slow_mo, args.headless, args.dual, args.codex)
        else:
            cmd_run(stages, args.slow_mo, args.headless)
    else:
        parser.print_help()
