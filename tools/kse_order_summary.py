"""KSE 팩킹리스트에서 당일 주문 요약 생성 (아마존 + 라쿠텐)"""
import io, sys, os, json, re, urllib.request, urllib.error
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")
from playwright.sync_api import sync_playwright

LOGIN_ID = os.getenv("KSEOMS_LOGIN_ID", "")
LOGIN_PW = os.getenv("KSEOMS_LOGIN_PASSWORD", "")
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
TEAMS_WEBHOOK_SEEUN = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", "")

# ── 옵션코드 → (카테고리, 사이즈, 색상) 역매핑 ─────────────────────
# fill_kseoms_option_code.py 의 OPTION_MAP 을 신뢰 소스로 사용
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
try:
    from fill_kseoms_option_code import OPTION_MAP as _OPTION_MAP
except Exception:
    _OPTION_MAP = {}

_CAT_LABEL = {
    "ppsu": "PPSU",
    "flip": "PPSU Flip Top",
    "stainless": "스테인리스",
}
_ACCESSORY_LABELS = {
    ("replacement", "straw", "2pack"): ("Replacement Straw", ""),
    ("silicone", "nipple", "4pcs"): ("Silicone Nipple 4pcs", ""),
    ("straw", "nipple", "replacement"): ("Replacement Straw", ""),
}

CODE_TO_INFO: dict[str, tuple[str, str, str]] = {}
for _kw, _code in _OPTION_MAP.items():
    if _kw in _ACCESSORY_LABELS:
        _cat, _size = _ACCESSORY_LABELS[_kw]
        CODE_TO_INFO[_code] = (_cat, _size, "")
    elif len(_kw) == 3 and _kw[0] in _CAT_LABEL:
        _cat = _CAT_LABEL[_kw[0]]
        _size = f"{_kw[1]}ml" if _kw[1].isdigit() else _kw[1]
        _color = _kw[2].capitalize()
        CODE_TO_INFO[_code] = (_cat, _size, _color)


# ── 상품 분류 ──────────────────────────────────────────────────────
def classify_product(item_title_kr: str) -> tuple[str, str]:
    """itemTitleKr에서 (카테고리, 사이즈) 추출.

    Returns:
        ("PPSU", "200ml"), ("스테인리스", "300ml"),
        ("PPSU Flip Top", "300ml"),
        ("Replacement Straw", ""), ("Silicone Nipple 4pcs", "") 등
    """
    t = item_title_kr.lower()

    # 사이즈 추출
    size_match = re.search(r"(\d+)\s*ml", t)
    size = f"{size_match.group(1)}ml" if size_match else ""

    # 악세서리
    if "replacement straw" in t:
        return ("replacement straw", "")
    if "silicone" in t and "nipple" in t:
        return ("silicone nipple", "")

    # 원터치 (Flip Top / Dino / Unicorn / ワンタッチ)
    if any(kw in t for kw in ["dino", "unicorn", "flip", "onetouch", "one touch", "ワンタッチ"]):
        return ("원터치", size)

    # 스테인리스
    if "stainless" in t:
        return ("스테인리스", size)

    # 기본 PPSU
    if "ppsu" in t:
        return ("PPSU", size)

    return ("기타", size)


def extract_color(option: str, item_title_kr: str) -> str:
    """option 필드(우선) + itemTitleKr에서 색상 추출. 없으면 ""."""
    src = (option or "") + " " + (item_title_kr or "")
    s = src.lower()

    # 일본어 (option 필드) — 길수록 먼저 매칭 (オリーブピスタチオ before オリーブ 등)
    jp_pairs = [
        ("オリーブピスタチオ", "Olive"),
        ("チェリーピーチ", "Cherry"),
        ("スカイブルー", "Skyblue"),
        ("ホワイト", "White"),
        ("チャコール", "Charcoal"),
        ("ピンク", "Pink"),
        ("ユニコーン", "Unicorn"),
        ("ダイノ", "Dino"),
        ("恐竜", "Dino"),
        ("ベア", "Bear"),
        ("オリーブ", "Olive"),
        ("チェリー", "Cherry"),
    ]
    for jp, en in jp_pairs:
        if jp in src:
            return en

    # 영어 (itemTitleKr) — 복합 키워드 먼저
    en_pairs = [
        ("sweet peach", "Cherry"),
        ("pistachio", "Olive"),
        ("sky blue", "Skyblue"),
        ("skyblue", "Skyblue"),
        ("charcoal", "Charcoal"),
        ("unicorn", "Unicorn"),
        ("white", "White"),
        ("pink", "Pink"),
        ("cherry", "Cherry"),
        ("olive", "Olive"),
        ("bear", "Bear"),
        ("dino", "Dino"),
    ]
    for en, label in en_pairs:
        if en in s:
            return label

    return ""


def build_summary(rows: list[dict]) -> str:
    """팩킹리스트 행 데이터 → 채널별 주문 요약 텍스트."""
    # market 매핑
    channel_map = {
        "amazonjp": "아마존",
        "amazon": "아마존",
        "rakuten": "라쿠텐",
        "rakutenjp": "라쿠텐",
    }

    # {채널: {카테고리: {(색상, 사이즈): 수량}}}
    summary = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # {채널: set(주문번호)} — 주문 건수(주문자 수) 카운트용
    order_ids_by_channel = defaultdict(set)

    for row in rows:
        market = (row.get("market") or "").lower()
        channel = channel_map.get(market, market)
        title_kr = row.get("itemTitleKr") or ""
        option = row.get("option") or ""
        qty = int(row.get("orderQty") or 1)
        order_no = row.get("orderNo") or row.get("receiverName") or ""

        opt_code = (row.get("optionCode") or "").strip()
        info = CODE_TO_INFO.get(opt_code)
        if info:
            cat, size, color = info
        else:
            cat, size = classify_product(title_kr)
            color = extract_color(option, title_kr)
        summary[channel][cat][(color, size)] += qty
        if order_no:
            order_ids_by_channel[channel].add(order_no)

    # 채널 순서: 아마존 → 라쿠텐 → 기타
    channel_order = ["아마존", "라쿠텐"]
    # 카테고리 순서
    cat_order = ["PPSU", "PPSU Flip Top", "원터치", "스테인리스", "Replacement Straw", "Silicone Nipple 4pcs", "replacement straw", "silicone nipple", "기타"]
    # 색상 정렬 우선순위
    color_order = ["White", "Charcoal", "Pink", "Skyblue", "Cherry", "Bear", "Olive", "Unicorn", "Dino", ""]
    color_rank = {c: i for i, c in enumerate(color_order)}

    lines = []
    for ch in channel_order:
        if ch not in summary:
            continue
        cats = summary[ch]
        # 채널 총 건수 = 고유 주문번호 수 (주문자 수 기준)
        order_count = len(order_ids_by_channel.get(ch, set()))
        if order_count == 0:
            # fallback: 주문번호 없으면 제품 라인 수
            order_count = sum(
                qty for variants in cats.values() for qty in variants.values()
            )
        lines.append(f"{ch} ({order_count}건)")
        for cat in cat_order:
            if cat not in cats:
                continue
            variants = cats[cat]
            keys = sorted(
                variants.keys(),
                key=lambda k: (color_rank.get(k[0], 99), k[1]),
            )
            for color, s in keys:
                qty = variants[(color, s)]
                if not s and not color:
                    # 악세서리 (사이즈/색상 없음)
                    lines.append(f"{cat} x{qty}")
                elif not s:
                    lines.append(f"{cat} {color} x{qty}")
                elif not color:
                    lines.append(f"{cat} {s} x{qty}")
                else:
                    lines.append(f"{cat} {color} {s} x{qty}")
        lines.append("")
        lines.append("")

    lines.append("")
    lines.append("")
    lines.append("주문 들어온 것 공유드립니다.")
    return "\n".join(lines)


def fetch_packing_data(headless: bool = True) -> list[dict]:
    """KSE /shipping2 팩킹리스트에서 AG Grid 데이터 읽기."""
    with sync_playwright() as pw:
        # KSE는 headless 차단 → 항상 headed + 최소화로 실행
        browser = pw.chromium.launch(headless=False, slow_mo=300, args=["--window-position=-2400,-2400"])
        page = browser.new_page()
        page.on("dialog", lambda dialog: dialog.accept())

        # 로그인 (재시도 포함)
        for attempt in range(3):
            try:
                page.goto("https://kseoms.com/login", wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(3000)
                page.wait_for_selector("input[type=password]", timeout=15000)
                break
            except Exception:
                if attempt == 2:
                    raise
                print(f"  [RETRY] 로그인 페이지 로드 재시도 ({attempt+2}/3)")
                page.wait_for_timeout(3000)
        id_input = page.query_selector("input[name*=id]") or page.query_selector("input[type=text]")
        pw_input = page.query_selector("input[type=password]")
        id_input.fill(LOGIN_ID)
        pw_input.fill(LOGIN_PW)
        submit = page.query_selector("button[type=submit]")
        if submit:
            submit.click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)

        # 팩킹리스트
        page.goto("https://kseoms.com/shipping2", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # 공지 팝업 닫기 (모달 오버레이 포함)
        try:
            page.evaluate("""() => {
                document.querySelectorAll('figure[id^="noticeModal"]').forEach(el => {
                    el.style.display = 'none';
                });
                document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                document.querySelectorAll('button.btn-notice-hide').forEach(btn => btn.click());
            }""")
            page.wait_for_timeout(1000)
        except Exception:
            pass

        # 검색
        try:
            search_btn = page.wait_for_selector(
                "button:has-text('검 색'), button:has-text('검색')", timeout=5000)
            search_btn.click()
            page.wait_for_timeout(3000)
        except Exception:
            pass

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
                if (node.data) result.push(JSON.parse(JSON.stringify(node.data)));
            });
            return result;
        }""")

        browser.close()
        return rows


def send_to_teams(summary_text: str) -> bool:
    """Teams 웹훅으로 주문 요약 직접 전송 (심플 텍스트)."""
    from datetime import date
    if not TEAMS_WEBHOOK_SEEUN:
        print("  [WARN] TEAMS_WEBHOOK_URL_SEEUN 미설정")
        return False
    today = date.today()
    header = f"• {today.month}/{today.day} 주문 요약"
    # Teams는 \n 연속 무시 → <br> 태그로 줄바꿈
    body_html = summary_text.replace("\n\n", "<br><br>").replace("\n", "<br>")
    full_msg = header + "<br><br>" + body_html
    payload = {"text": full_msg}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(TEAMS_WEBHOOK_SEEUN, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status in (200, 202):
                print("  [OK] Teams 직접 전송 완료")
                return True
            print(f"  [WARN] Teams 응답: {r.status}")
            return False
    except Exception as e:
        print(f"  [WARN] Teams 전송 실패: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="KSE 팩킹리스트 주문 요약")
    parser.add_argument("--headed", action="store_true", help="브라우저 표시")
    parser.add_argument("--from-file", type=str, help="JSON 파일에서 읽기 (디버그용)")
    parser.add_argument("--no-teams", action="store_true", help="Teams 전송 안 함")
    parser.add_argument(
        "--confirm-before-teams",
        action="store_true",
        help="Teams 전송 전에 확인을 묻기 (기본: 확인 없이 즉시 전송)",
    )
    args = parser.parse_args()

    if args.from_file:
        with open(args.from_file, "r", encoding="utf-8") as f:
            rows = json.load(f)
    else:
        print("[1a] KSE 팩킹리스트 (아마존)...")
        kse_rows = fetch_packing_data(headless=not args.headed)
        # 라쿠텐은 KSE에서 더 이상 처리하지 않음 — 행 제외
        amazon_rows = [
            r for r in kse_rows
            if (r.get("market") or "").lower() not in ("rakuten", "rakutenjp")
        ]
        skipped = len(kse_rows) - len(amazon_rows)
        print(f"  KSE {len(kse_rows)}건 → 아마존 {len(amazon_rows)}건 (라쿠텐 {skipped}건 제외)")

        print("[1b] RMS 발송대기 (라쿠텐)...")
        try:
            from rakuten_pending_orders import fetch_pending_orders
            rakuten_rows = fetch_pending_orders(headless=not args.headed)
            print(f"  라쿠텐 {len(rakuten_rows)}건 로드")
        except Exception as e:
            print(f"  [WARN] 라쿠텐 수집 실패: {e}")
            rakuten_rows = []

        rows = amazon_rows + rakuten_rows

    print()
    text = build_summary(rows)
    print(text)

    # .tmp에도 저장
    out = PROJECT_ROOT / ".tmp" / "order_summary.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)

    # Teams 직접 전송 (기본: 자동 전송)
    if not args.no_teams and rows:
        if args.confirm_before_teams:
            ans = input("Teams로 전송할까요? [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                print("[SKIP] 사용자 확인으로 Teams 전송 건너뜀")
                return
        print("\n[2] Teams 전송...")
        send_to_teams(text)


if __name__ == "__main__":
    main()
