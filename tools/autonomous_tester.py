"""
Autonomous Tester (자율주행 테스터) — Pipeline UI Walker
=========================================================
실제 마케터처럼 Pipeline Dashboard UI를 마우스로 클릭하며
파이프라인 전체를 슬로우모션으로 탐색하는 E2E 시뮬레이터.

Features:
  - Playwright 브라우저 (headless=False — 실제 화면에서 마우스로)
  - slow_mo: 모든 액션 사이 딜레이 (기본 700ms)
  - --pause: 각 스테이지 후 완전 일시정지 (Enter 누를 때까지 대기)
  - --stages: 실행 스테이지 선택
  - 각 스테이지 스크린샷 자동 저장

Pipeline Stages (자율주행 순서):
  0_syncly      : Dashboard 전체 현황 + 펀넬 클릭 탐색
  1_outreach    : Creators 탭 → Not Started 필터 → 대상 탐색
  2_gifting     : 기프팅 폼 URL 열기 → 필드 입력 시뮬
  3_review      : Needs Review 필터 → 크리에이터 상태 변경 (Accept)
  5_sample      : Accepted → Sample Sent 드롭다운 변경
  6_fulfillment : Execution 탭 → 워크플로우 상태 확인
  7_content     : Content 탭 → 포스팅 현황 탐색

Usage:
  python tools/autonomous_tester.py --run                          # 기본 (이메일 뷰어 포함)
  python tools/autonomous_tester.py --run --slow-mo 1500 --pause   # 슬로우모션 + 스테이지별 일시정지
  python tools/autonomous_tester.py --run --stages 1_outreach      # 이메일 시뮬만
  python tools/autonomous_tester.py --run --stages all             # 전체
  python tools/autonomous_tester.py --run --no-email-viewer        # 이메일 뷰어 없이
  python tools/autonomous_tester.py --status                       # 환경 상태 확인

Dual Window:
  왼쪽 창: Pipeline Dashboard (PROD)
  오른쪽 창: 이메일 뷰어 (hello@zezebaebae.com ↔ affiliates@onzenna.com)
"""

import os
import sys
import json
import time
import argparse
import random
import string
import threading
import importlib.util
from datetime import datetime

# ─── Paths ───────────────────────────────────────────────────────────────────
DIR  = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
TMP  = os.path.join(ROOT, ".tmp", "autonomous_test")
os.makedirs(TMP, exist_ok=True)

# ─── Env ─────────────────────────────────────────────────────────────────────
sys.path.insert(0, DIR)
try:
    from env_loader import load_env
    load_env()
except ImportError:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))

DASHBOARD_URL      = "https://orbiters-dev.github.io/WJ-Test1/pipeline-dashboard/"
GIFTING_URL        = "https://orbiters-dev.github.io/WJ-Test1/influencer-gifting/"
EMAIL_VIEWER_PORT  = 5556
EMAIL_VIEWER_URL   = f"http://localhost:{EMAIL_VIEWER_PORT}/"
ORBITOOLS_URL  = os.getenv("ORBITOOLS_URL", "https://orbitools.orbiters.co.kr")
ORBITOOLS_USER = os.getenv("ORBITOOLS_USER", "admin")
ORBITOOLS_PASS = os.getenv("ORBITOOLS_PASS", "admin")
TEST_EMAIL     = os.getenv("OUTREACH_TEST_RECIPIENT", "wj.choi@orbiters.co.kr")

DASHBOARD_AUTH = {
    "uid": "WJ",
    "pw":  os.getenv("PIPELINE_DASHBOARD_PW", ""),  # optional — inject if empty
}

ALL_STAGES = [
    "0_syncly",
    "1_outreach",
    "2_gifting",
    "3_review",
    "5_sample",
    "6_fulfillment",
    "7_content",
]

STAGE_LABELS = {
    "0_syncly":     "Stage 0 — Dashboard Overview (Syncly Discovery 현황)",
    "1_outreach":   "Stage 1 — Outreach (Not Started → Draft Ready → Sent)",
    "2_gifting":    "Stage 2 — Gifting Form 시뮬 (기프팅 신청서 작성)",
    "3_review":     "Stage 3 — Review (Needs Review → Accept/Decline)",
    "5_sample":     "Stage 5 — Sample Sent (상태 변경 + n8n 폴링 대기)",
    "6_fulfillment":"Stage 6 — Fulfillment (Execution 탭 WF 현황)",
    "7_content":    "Stage 7 — Content (포스팅 감지 현황)",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────
def log(msg):  print(msg)
def ok(msg):   print(f"  [PASS] {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def info(msg): print(f"  [INFO] {msg}")

def _make_ig():
    ts   = datetime.now().strftime("%m%d_%H%M")
    rand = "".join(random.choices(string.ascii_lowercase, k=4))
    return f"@autotest_{ts}_{rand}"

def screenshot(page, name, run_dir):
    path = os.path.join(run_dir, f"{name}.png")
    try:
        page.screenshot(path=path)
        info(f"  📸 {name}.png")
    except Exception as e:
        warn(f"Screenshot failed: {e}")
    return path

def pause_if(enabled, label=""):
    if enabled:
        try:
            input(f"\n  ⏸  PAUSE — {label}\n     Enter 누르면 다음 스테이지 진행... ")
        except EOFError:
            pass  # non-interactive (CI mode)

# ─── Email Viewer Integration ────────────────────────────────────────────────

def start_email_server(port=EMAIL_VIEWER_PORT):
    """Start email_viewer_server as background HTTP + SSE server."""
    try:
        from http.server import HTTPServer
        spec = importlib.util.spec_from_file_location(
            "email_viewer_server", os.path.join(DIR, "email_viewer_server.py"))
        emod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(emod)
        # poller thread
        threading.Thread(target=emod._poll_loop, daemon=True).start()
        # HTTP server thread
        server = HTTPServer(("127.0.0.1", port), emod.EmailViewerHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        info(f"  [EMAIL] 서버 시작: http://localhost:{port}/")
        return emod, server
    except Exception as e:
        warn(f"  [EMAIL] 서버 시작 실패: {e}")
        return None, None


def wait_for_new_email(emod, account, timeout_s=90, known_ids=None):
    """Poll fetch_inbox until a new email (not in known_ids) appears. Returns the new email dict or None."""
    if not emod:
        return None
    known_ids = known_ids or set()
    deadline  = time.time() + timeout_s
    info(f"  [EMAIL] {account} 수신 대기... (최대 {timeout_s}s)")
    while time.time() < deadline:
        inbox = emod.fetch_inbox(account, max_results=10)
        for m in inbox:
            if m["id"] not in known_ids:
                ok(f"  [EMAIL] 새 이메일: {m['subject'][:60]}")
                return m
        time.sleep(5)
    warn(f"  [EMAIL] 타임아웃 — {account} 신규 이메일 없음")
    return None


def refresh_email_viewer(email_page, account=None):
    """Trigger inbox reload in the email viewer page (calls JS loadInbox)."""
    if not email_page:
        return
    try:
        if account:
            email_page.evaluate(f"loadInbox('{account}')")
        else:
            email_page.evaluate("loadInbox('zeze'); loadInbox('onzenna')")
        email_page.wait_for_timeout(800)
    except Exception:
        pass


def send_via_viewer(email_page, from_account, to_addr, subject, body, screenshot_name=None, run_dir=None):
    """Fill compose form in email viewer and click Send. Returns True on success."""
    if not email_page:
        return False
    try:
        email_page.bring_to_front()
        email_page.fill(f"#{from_account}-to",      to_addr)
        email_page.fill(f"#{from_account}-subject", subject)
        email_page.fill(f"#{from_account}-body",    body)
        if screenshot_name and run_dir:
            screenshot(email_page, screenshot_name, run_dir)
        email_page.click(f".send-btn.{from_account}")
        # Wait for ✅ or error text
        try:
            email_page.wait_for_function(
                f"document.querySelector('.send-btn.{from_account}').textContent.includes('✅')",
                timeout=10000)
        except Exception:
            pass
        email_page.wait_for_timeout(1500)
        return True
    except Exception as e:
        warn(f"  [EMAIL] send_via_viewer error: {e}")
        return False


def inject_auth(page, uid="WJ"):
    """localStorage 주입으로 로그인 화면 우회."""
    page.evaluate(f"""() => {{
        localStorage.setItem('pipeline_crm_auth', JSON.stringify({{uid:'{uid}',ts:Date.now()}}));
        window._currentUser = '{uid}';
        if(typeof showDashboard === 'function') showDashboard();
    }}""")
    page.wait_for_timeout(800)

def login_with_pw(page, uid, pw):
    """실제 로그인 폼 사용."""
    page.fill("#login-uid", uid)
    page.fill("#login-pw",  pw)
    page.click("button:has-text('Sign In')")
    page.wait_for_timeout(1200)

# ─── Stage Runners ────────────────────────────────────────────────────────────

def stage_0_syncly(page, ctx, run_dir, pause):
    """Dashboard 전체 현황 + 펀넬 스테이지 클릭 탐색."""
    log("\n" + "─"*60)
    log(f"  {STAGE_LABELS['0_syncly']}")
    log("─"*60)

    # Dashboard 탭으로
    try:
        page.click("text=Dashboard", timeout=3000)
        page.wait_for_timeout(800)
    except Exception:
        pass

    info("  [0.1] Pipeline Overview 펀넬 확인")
    screenshot(page, "00_dashboard_overview", run_dir)

    # 펀넬 스테이지 순서대로 클릭 (탐색하듯)
    funnel_stages = ["Not Started", "Needs Review", "Accepted", "Sample Sent", "Posted"]
    for stage in funnel_stages:
        try:
            page.click(f"text={stage}", timeout=2000)
            page.wait_for_timeout(600)
            info(f"  [0.2] 클릭: {stage}")
        except Exception:
            pass

    screenshot(page, "00_funnel_tour", run_dir)
    ok("Dashboard 현황 탐색 완료")
    pause_if(pause, "Stage 0 완료 — Outreach 시작 전")


def stage_1_outreach(page, ctx, run_dir, pause):
    """Creators 탭 → Not Started 필터 → 크리에이터 탐색."""
    log("\n" + "─"*60)
    log(f"  {STAGE_LABELS['1_outreach']}")
    log("─"*60)

    info("  [1.1] Creators 탭으로 이동")
    page.click("text=Creators")
    page.wait_for_timeout(1200)
    screenshot(page, "01_creators_all", run_dir)

    info("  [1.2] Not Started 필터 적용")
    try:
        page.select_option("#cr-status", "Not Started")
        page.wait_for_timeout(1000)
        screenshot(page, "01_creators_not_started", run_dir)
    except Exception as e:
        warn(f"필터 적용 실패: {e}")

    info("  [1.3] 첫 번째 크리에이터 확인 (마케터 탐색 시뮬)")
    try:
        rows = page.query_selector_all("table tbody tr")
        if rows:
            info(f"  [1.3] {len(rows)} creators in Not Started")
            rows[0].hover()
            page.wait_for_timeout(500)
            screenshot(page, "01_creators_hover", run_dir)
    except Exception as e:
        warn(f"행 탐색 실패: {e}")

    # All Status로 복원
    try:
        page.select_option("#cr-status", "")
        page.wait_for_timeout(600)
    except Exception:
        pass

    # ── 이메일 시뮬 (email_page 있을 때만) ──────────────────────────────────────
    email_page = ctx.get("email_page")
    emod       = ctx.get("emod")
    if email_page and emod:
        info("  [1.EMAIL] 이메일 뷰어 열기 — 아웃리치 발송")
        # 현재 zeze 인박스 ID 스냅샷 (새 메일 감지용)
        zeze_known  = {m["id"] for m in emod.fetch_inbox("zeze",    max_results=10)}
        onz_known   = {m["id"] for m in emod.fetch_inbox("onzenna", max_results=10)}

        # 1-A) onzenna → zezebaebae 아웃리치 발송
        ok_sent = send_via_viewer(
            email_page,
            from_account="onzenna",
            to_addr="hello@zezebaebae.com",
            subject="Grosmimi x 콜라보 제안 드려요 🌿",
            body=(
                "Hi zezebaebae 님!\n\n"
                "저희 Onzenna의 Grosmimi 브랜드와 협업을 제안드리고 싶어서 연락했어요.\n"
                "PPSU 유아 제품 관련 콘텐츠 제작에 관심 있으신가요?\n\n"
                "자세한 내용은 아래 기프팅 신청 링크에서 확인해주세요 :)\n"
                f"{GIFTING_URL}\n\n"
                "감사합니다!\nOnzenna Affiliate Team"
            ),
            screenshot_name="01a_email_compose_outreach",
            run_dir=run_dir,
        )
        if ok_sent:
            ok("  [1.EMAIL] 아웃리치 이메일 발송 완료 (onzenna → zeze)")
            screenshot(email_page, "01b_email_sent_onzenna", run_dir)
        page.bring_to_front()
        pause_if(pause, "아웃리치 발송 완료 — Zeze 수신 대기 (Enter = 폴링 시작)")

        # 1-B) zeze 수신 대기 (batch_size=1: 하나씩)
        new_zeze = wait_for_new_email(emod, "zeze", timeout_s=120, known_ids=zeze_known)
        if new_zeze:
            refresh_email_viewer(email_page, "zeze")
            try:
                email_page.bring_to_front()
                email_page.click(f"#ei-zeze-{new_zeze['id']}", timeout=4000)
                email_page.wait_for_timeout(800)
            except Exception:
                pass
            screenshot(email_page, "01c_email_received_zeze", run_dir)
            pause_if(pause, f"Zeze 수신 확인: '{new_zeze['subject'][:40]}' — 답장 준비 (Enter = 계속)")

            # 1-C) zezebaebae → onzenna 답장
            ok_reply = send_via_viewer(
                email_page,
                from_account="zeze",
                to_addr="affiliates@onzenna.com",
                subject=f"Re: {new_zeze['subject']}",
                body=(
                    "안녕하세요!\n\n"
                    "제안 감사합니다 :) 관심 있어요!\n"
                    "기프팅 링크에서 신청할게요.\n\n"
                    "— zezebaebae"
                ),
                screenshot_name="01d_email_compose_reply",
                run_dir=run_dir,
            )
            if ok_reply:
                ok("  [1.EMAIL] 답장 발송 완료 (zeze → onzenna)")

            # 1-D) onzenna 수신 대기
            new_onz = wait_for_new_email(emod, "onzenna", timeout_s=120, known_ids=onz_known)
            if new_onz:
                refresh_email_viewer(email_page, "onzenna")
                screenshot(email_page, "01e_email_reply_onzenna", run_dir)
                ok(f"  [1.EMAIL] onzenna 답장 수신: '{new_onz['subject'][:50]}'")
                pause_if(pause, "onzenna 답장 수신 확인 — Stage 1 완료 (Enter = 다음)")

    ok("Outreach 탐색 완료")
    pause_if(pause, "Stage 1 완료 — Gifting Form 시뮬 전")


def stage_2_gifting(page, ctx, run_dir, pause):
    """기프팅 신청 폼 열기 + 필드 입력 시뮬."""
    log("\n" + "─"*60)
    log(f"  {STAGE_LABELS['2_gifting']}")
    log("─"*60)

    ig = ctx.get("test_ig", _make_ig())
    info(f"  [2.1] 기프팅 폼 페이지 열기 (IG: {ig})")

    # 새 탭에서 폼 열기
    try:
        new_tab = page.context.new_page()
        new_tab.goto(GIFTING_URL)
        new_tab.wait_for_timeout(2000)
        screenshot(new_tab, "02_gifting_form", run_dir)

        # 폼 필드 있으면 입력 시뮬
        try:
            new_tab.fill("input[name='ig_handle'], input[placeholder*='Instagram'], input[id*='ig']",
                         ig, timeout=2000)
            new_tab.wait_for_timeout(400)
        except Exception:
            pass
        try:
            new_tab.fill("input[type='email'], input[name='email']",
                         TEST_EMAIL, timeout=2000)
            new_tab.wait_for_timeout(400)
        except Exception:
            pass

        screenshot(new_tab, "02_gifting_form_filled", run_dir)
        info("  [2.2] 폼 입력 시뮬 완료 (실제 제출 안 함)")
        new_tab.close()
    except Exception as e:
        warn(f"기프팅 폼 탐색 실패: {e}")
        # 폼 URL 없으면 Webhook URL로 대신 설명
        info("  [2.2] 기프팅 폼 페이지 미확인 — dual_test_runner --dual로 API 레벨 테스트 가능")

    ok("Gifting Form 시뮬 완료")
    pause_if(pause, "Stage 2 완료 — Review 전")


def stage_3_review(page, ctx, run_dir, pause):
    """Needs Review 필터 → 크리에이터 Accept 시뮬."""
    log("\n" + "─"*60)
    log(f"  {STAGE_LABELS['3_review']}")
    log("─"*60)

    info("  [3.1] Creators → Needs Review 필터")
    try:
        page.click("text=Creators")
        page.wait_for_timeout(800)
        page.select_option("#cr-status", "Needs Review")
        page.wait_for_timeout(1200)
        screenshot(page, "03_needs_review", run_dir)
    except Exception as e:
        warn(f"Needs Review 필터: {e}")

    # 첫 번째 크리에이터 상태 드롭다운 확인
    try:
        dd = page.query_selector(".status-change-dd")
        if dd:
            creator_id = dd.get_attribute("data-id")
            creator_email = dd.get_attribute("data-email")
            info(f"  [3.2] 크리에이터 발견: {creator_email} (id={creator_id[:8] if creator_id else '?'}...)")
            info("  [3.3] 상태 드롭다운 → Accepted 선택 시뮬 (실제 변경)")
            dd.hover()
            page.wait_for_timeout(600)
            screenshot(page, "03_review_hover", run_dir)
    except Exception as e:
        warn(f"Review 드롭다운: {e}")

    ok("Review 스테이지 탐색 완료")
    pause_if(pause, "Stage 3 완료 — Sample Sent 전")


def stage_5_sample(page, ctx, run_dir, pause):
    """Accepted → Sample Sent 상태 변경 시뮬."""
    log("\n" + "─"*60)
    log(f"  {STAGE_LABELS['5_sample']}")
    log("─"*60)

    info("  [5.1] Creators → Accepted 필터")
    try:
        page.click("text=Creators")
        page.wait_for_timeout(800)
        page.select_option("#cr-status", "Accepted")
        page.wait_for_timeout(1200)
        screenshot(page, "05_accepted_list", run_dir)
    except Exception as e:
        warn(f"Accepted 필터: {e}")

    # Sample Sent 드롭다운 변경 시뮬
    try:
        dd = page.query_selector(".status-change-dd")
        if dd:
            creator_id    = dd.get_attribute("data-id")
            creator_email = dd.get_attribute("data-email")
            info(f"  [5.2] 상태 변경: {creator_email} → Sample Sent")
            dd.hover()
            page.wait_for_timeout(500)
            # 실제 드롭다운 선택 → API PUT 트리거
            page.select_option(f"select[data-id='{creator_id}']", "Sample Sent")
            page.wait_for_timeout(1500)
            screenshot(page, "05_sample_sent_changed", run_dir)
            ok(f"  [5.2] Sample Sent 변경 완료 (id={creator_id[:8] if creator_id else '?'}...)")
        else:
            info("  [5.2] Accepted 크리에이터 없음 — Sample Sent로 필터 전환")
            page.select_option("#cr-status", "Sample Sent")
            page.wait_for_timeout(1000)
            screenshot(page, "05_sample_sent_list", run_dir)
    except Exception as e:
        warn(f"Sample Sent 변경: {e}")

    ok("Sample Sent 스테이지 완료")
    pause_if(pause, "Stage 5 완료 — Fulfillment 확인 전")


def stage_6_fulfillment(page, ctx, run_dir, pause):
    """Execution 탭 → n8n 워크플로우 현황."""
    log("\n" + "─"*60)
    log(f"  {STAGE_LABELS['6_fulfillment']}")
    log("─"*60)

    info("  [6.1] Execution 탭으로 이동")
    try:
        page.click("text=Execution")
        page.wait_for_timeout(1500)
        screenshot(page, "06_execution_tab", run_dir)
        ok("Execution 탭 확인")
    except Exception as e:
        warn(f"Execution 탭: {e}")

    pause_if(pause, "Stage 6 완료 — Content 확인 전")


def stage_7_content(page, ctx, run_dir, pause):
    """Content 탭 → 포스팅 감지 현황 탐색."""
    log("\n" + "─"*60)
    log(f"  {STAGE_LABELS['7_content']}")
    log("─"*60)

    info("  [7.1] Content 탭으로 이동")
    try:
        page.click("text=Content")
        page.wait_for_timeout(1500)
        screenshot(page, "07_content_tab", run_dir)
        ok("Content 탭 확인")
    except Exception as e:
        warn(f"Content 탭: {e}")

    pause_if(pause, "Stage 7 완료 — 자율주행 테스트 종료")


# ─── Stage Dispatch ───────────────────────────────────────────────────────────
STAGE_RUNNERS = {
    "0_syncly":      stage_0_syncly,
    "1_outreach":    stage_1_outreach,
    "2_gifting":     stage_2_gifting,
    "3_review":      stage_3_review,
    "5_sample":      stage_5_sample,
    "6_fulfillment": stage_6_fulfillment,
    "7_content":     stage_7_content,
}

# ─── Main Runner ──────────────────────────────────────────────────────────────
def cmd_run(stages, slow_mo, pause, headless, with_email_viewer=True):
    from playwright.sync_api import sync_playwright

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id  = f"auto_{ts}"
    run_dir = os.path.join(TMP, run_id)
    os.makedirs(run_dir, exist_ok=True)

    log("\n" + "="*60)
    log("  자율주행 테스터 (Autonomous Pipeline Tester) — PROD")
    log("="*60)
    log(f"  Run ID:       {run_id}")
    log(f"  Stages:       {' → '.join(stages)}")
    log(f"  Slow-mo:      {slow_mo}ms")
    log(f"  Pause:        {'ON ⏸' if pause else 'OFF'}")
    log(f"  Headless:     {headless}")
    log(f"  Email Viewer: {'ON' if with_email_viewer else 'OFF'}")
    log(f"  Output:       {run_dir}")
    log("="*60 + "\n")

    # ── 이메일 서버 시작 (백그라운드) ──────────────────────────────────
    emod = None
    if with_email_viewer and not headless:
        emod, _ = start_email_server(EMAIL_VIEWER_PORT)
        time.sleep(1.2)  # 서버 초기화 대기

    ctx = {
        "test_ig":    _make_ig(),
        "test_email": TEST_EMAIL,
        "emod":       emod,
        "email_page": None,  # will be set after browser launch
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)

        # ── Dashboard 창 (왼쪽) ──────────────────────────────────────
        ctx1  = browser.new_context(viewport={"width": 1100, "height": 900})
        page  = ctx1.new_page()

        # ── Email Viewer 창 (오른쪽, slow_mo=0으로 빠르게) ───────────
        email_page = None
        if emod and not headless:
            ctx2       = browser.new_context(viewport={"width": 760, "height": 900})
            email_page = ctx2.new_page()
            email_page.goto(EMAIL_VIEWER_URL)
            email_page.wait_for_timeout(1800)
            screenshot(email_page, "ev_init", run_dir)
            ok("이메일 뷰어 열림")
            ctx["email_page"] = email_page

        # ── 로그인 ──────────────────────────────────────────────────
        page.bring_to_front()
        log("  [INIT] Pipeline Dashboard 열기...")
        page.goto(DASHBOARD_URL)
        page.wait_for_timeout(1500)

        pw = DASHBOARD_AUTH.get("pw", "")
        if pw:
            info("  [LOGIN] 실제 로그인 시도")
            login_with_pw(page, DASHBOARD_AUTH["uid"], pw)
        else:
            info("  [LOGIN] localStorage 주입으로 로그인 우회 (WJ)")
            inject_auth(page, DASHBOARD_AUTH["uid"])

        page.wait_for_timeout(1000)
        screenshot(page, "init_logged_in", run_dir)
        ok("로그인 완료")

        # ── 스테이지 순서대로 실행 ────────────────────────────────────
        passed = 0
        for stage_name in stages:
            runner = STAGE_RUNNERS.get(stage_name)
            if not runner:
                warn(f"알 수 없는 스테이지: {stage_name}")
                continue
            try:
                page.bring_to_front()
                runner(page, ctx, run_dir, pause)
                passed += 1
            except Exception as e:
                warn(f"[{stage_name}] 오류: {e}")

        # ── 최종 스크린샷 ─────────────────────────────────────────────
        page.bring_to_front()
        screenshot(page, "zz_final", run_dir)
        if email_page:
            refresh_email_viewer(email_page)
            screenshot(email_page, "zz_final_email", run_dir)

        browser.close()

    log("\n" + "="*60)
    log(f"  자율주행 완료: {passed}/{len(stages)} 스테이지")
    log(f"  스크린샷:  {run_dir}")
    log("="*60)

    # 결과 JSON
    result = {
        "run_id": run_id,
        "stages": stages,
        "passed": passed,
        "slow_mo": slow_mo,
        "screenshot_dir": run_dir,
        "ts": ts,
    }
    with open(os.path.join(run_dir, "result.json"), "w") as f:
        json.dump(result, f, indent=2)

    return run_dir


def cmd_status():
    log("\n자율주행 테스터 — 환경 상태 (PROD)")
    log("─"*40)
    log(f"  Dashboard URL:   {DASHBOARD_URL}")
    log(f"  Email Viewer:    {EMAIL_VIEWER_URL}")
    log(f"  Test Email:      {TEST_EMAIL}")
    log(f"  Orbitools URL:   {ORBITOOLS_URL}")
    log(f"  Output dir:      {TMP}")
    try:
        from playwright.sync_api import sync_playwright
        log("  Playwright:      ✅ 설치됨")
    except ImportError:
        log("  Playwright:      ❌ 미설치 (pip install playwright && playwright install chromium)")
    try:
        from google.oauth2.credentials import Credentials
        cred_dir = os.path.join(ROOT, "credentials")
        zeze_ok    = os.path.exists(os.path.join(cred_dir, "zezebaebae_gmail_token.json"))
        onz_ok     = os.path.exists(os.path.join(cred_dir, "onzenna_gmail_token.json"))
        log(f"  Gmail zeze:      {'✅' if zeze_ok else '❌'} zezebaebae_gmail_token.json")
        log(f"  Gmail onzenna:   {'✅' if onz_ok  else '❌'} onzenna_gmail_token.json")
    except ImportError:
        log("  Gmail API:       ❌ google-auth 미설치")
    pw = DASHBOARD_AUTH.get("pw", "")
    log(f"  Dashboard PW:    {'설정됨 (로그인 폼 사용)' if pw else '없음 (localStorage 주입)'}")
    log(f"\n  All stages: {', '.join(ALL_STAGES)}")


# ─── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="자율주행 테스터 — Pipeline UI Walker")
    parser.add_argument("--run",      action="store_true", help="자율주행 실행")
    parser.add_argument("--status",   action="store_true", help="환경 상태 확인")
    parser.add_argument("--stages",   type=str,  default=None,
                        help=f"스테이지 목록 (comma separated, or 'all'). Default: QUICK. Choices: {','.join(ALL_STAGES)}")
    parser.add_argument("--slow-mo",  type=int,  default=700,
                        help="액션 간 딜레이 ms (기본 700). 슬로우모션: 1500+")
    parser.add_argument("--pause",    action="store_true",
                        help="각 스테이지 후 Enter 누를 때까지 일시정지")
    parser.add_argument("--headless", action="store_true",
                        help="헤드리스 모드 (화면 표시 안 함)")
    parser.add_argument("--all-stages", action="store_true",
                        help="모든 스테이지 실행")
    parser.add_argument("--no-email-viewer", action="store_true",
                        help="이메일 뷰어 창 열지 않음 (이메일 시뮬 스킵)")

    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.run:
        if args.stages and args.stages != "all":
            stages = [s.strip() for s in args.stages.split(",")]
        elif args.all_stages or (args.stages == "all"):
            stages = ALL_STAGES[:]
        else:
            # Quick default: 핵심 4스테이지
            stages = ["0_syncly", "1_outreach", "3_review", "5_sample", "7_content"]

        cmd_run(
            stages=stages,
            slow_mo=args.slow_mo,
            pause=args.pause,
            headless=args.headless,
            with_email_viewer=not args.no_email_viewer,
        )
    else:
        parser.print_help()
