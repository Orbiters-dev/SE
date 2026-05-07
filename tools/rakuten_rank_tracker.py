"""
rakuten_rank_tracker.py — 라쿠텐 키워드별 검색 순위 트래커

키워드별로 라쿠텐 검색 결과를 Playwright로 직접 크롤링하고,
GROSMIMI(LITTLEFINGERUSA) 제품의 오가닉 순위를 추적한다.
PR(광고) 결과 제외 순위를 기준으로 보고한다.

사용법:
  python tools/rakuten_rank_tracker.py                # 전체 키워드 추적 + Teams 발송
  python tools/rakuten_rank_tracker.py --dry-run       # 추적만 (Teams 발송 안 함)
  python tools/rakuten_rank_tracker.py --keywords "グロミミ,PPSU"  # 특정 키워드만
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- path setup ---
TOOLS_DIR = Path(__file__).resolve().parent
ROOT = TOOLS_DIR.parent

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
TMP_DIR = ROOT / ".tmp"
TMP_DIR.mkdir(exist_ok=True)

# --- encoding ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# --- timezone ---
JST = timezone(timedelta(hours=9))
KST = timezone(timedelta(hours=9))  # same offset

# ============================================================
# 설정
# ============================================================

SHOP_IDENTIFIERS = ["littlefingerusa", "435776"]
OUR_BRAND = "GROSMIMI"

DEFAULT_KEYWORDS = [
    # ── 브랜드 (3) ──
    "グロミミ",
    "grosmimi",
    "グロミミ マグ",
    # ── 대표 제너릭 (2) ──
    "ストローマグ",
    "マグマグ",
    # ── 소재 (3) ──
    "ppsu",
    "ストローマグ ステンレス",
    "ステンレスストローマグ",
    # ── 기능 (5) ──
    "漏れない ストローマグ",
    "ストローマグ 食洗機対応",
    "軽量 ストローマグ",
    "ワンタッチ ストローマグ",
    "両手",
    # ── 제품 타입 (3) ──
    "ベビーマグ",
    "ベビー ストローマグ",
    "トレーニングマグ",
]
# ── 제외 키워드 (세은 지시 2026-04-21) ──
# 아래는 순위 조사에서 제외. 장기간 45위 내 미노출 또는 트래킹 가치 낮음.
#   - ベビー 水筒                 (45位内にない)
#   - ストローマグ 出産祝い       (45位内にない)
#   - ストローマグ 保育園         (4위 PPSU — 세은 지시로 제외)
#   - 赤ちゃん ストローマグ       (45位内にない)
#   - 水筒 ストロー               (45位内にない)
#   - サーモス ストローマグ       (45位内にない)

# 과거 데이터 파일
HISTORY_FILE = TMP_DIR / "rakuten_rank_history.json"

# Teams webhook (세은 전용)
TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL_SEEUN", os.getenv("TEAMS_WEBHOOK_URL", ""))

# 한 페이지에 약 45개 결과, 첫 페이지만 확인
MAX_PAGES = 1


# ============================================================
# Playwright 스크래핑
# ============================================================

def scrape_keyword(keyword: str, max_pages: int = MAX_PAGES, pw_page=None) -> list[dict]:
    """Playwright로 라쿠텐 검색 후 결과 파싱. 각 아이템을 dict로 반환."""
    all_items = []

    for page_num in range(1, max_pages + 1):
        encoded_kw = urllib.parse.quote(keyword)
        if page_num == 1:
            url = f"https://search.rakuten.co.jp/search/mall/{encoded_kw}/"
        else:
            url = f"https://search.rakuten.co.jp/search/mall/{encoded_kw}/?p={page_num}"

        try:
            pw_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            pw_page.wait_for_timeout(2000)
        except Exception as e:
            print(f"  [ERROR] {keyword} p{page_num}: {e}")
            continue

        # .searchresultitem 으로 모든 검색결과 아이템 선택
        item_els = pw_page.query_selector_all(".searchresultitem")
        if not item_els:
            print(f"  [SKIP] {keyword} p{page_num} — 아이템 없음")
            break

        for item_el in item_els:
            parsed = parse_item_element(item_el)
            if parsed:
                parsed["page"] = page_num
                all_items.append(parsed)

        # 결과가 적으면 다음 페이지 불필요
        if len(item_els) < 30:
            break

        # rate limit 방지
        if page_num < max_pages:
            time.sleep(1.5)

    return all_items


def parse_item_element(item_el) -> dict | None:
    """개별 .searchresultitem 요소에서 제품 정보 파싱."""
    import re
    try:
        # 제목 + 링크: [class*=title-link-wrapper] a
        title_el = item_el.query_selector("[class*=title-link-wrapper] a")
        if not title_el:
            return None

        title = title_el.inner_text().strip()
        if not title or len(title) < 3:
            return None

        link = title_el.get_attribute("href") or ""

        # PR 판별: 제목에 [PR] 포함 또는 링크가 redirect_rpp/ias.rakuten 경로
        is_pr = title.startswith("[PR]") or "redirect_rpp" in link or "ias.rakuten.co.jp" in link

        # [PR] 접두사 제거 (분석용)
        clean_title = title
        if clean_title.startswith("[PR] "):
            clean_title = clean_title[5:]
        elif clean_title.startswith("[PR]"):
            clean_title = clean_title[4:]

        # 판매자명: .content.merchant a
        shop_el = item_el.query_selector(".content.merchant a")
        shop = shop_el.inner_text().strip() if shop_el else ""

        # 가격: [class*="price--"] div
        price = ""
        price_el = item_el.query_selector("[class*='price--']")
        if price_el:
            price_text = price_el.inner_text().strip()
            m = re.search(r"([\d,]+)", price_text)
            if m:
                price = m.group(1)

        # 우리 제품 여부: 링크 또는 판매자명에 식별자 포함
        is_ours = any(sid in link.lower() for sid in SHOP_IDENTIFIERS)
        if not is_ours and shop:
            is_ours = any(sid in shop.lower() for sid in SHOP_IDENTIFIERS)

        return {
            "title": clean_title,
            "is_pr": is_pr,
            "is_ours": is_ours,
            "price": price,
            "shop": shop,
            "url": link,
        }
    except Exception:
        return None


def analyze_keyword(keyword: str, items: list[dict]) -> dict:
    """키워드별 분석 결과 생성."""
    # PR 제외 순위 계산
    organic_rank = 0
    our_positions = []
    top_competitors = []

    for item in items:
        if item["is_pr"]:
            continue
        organic_rank += 1

        if item["is_ours"] and organic_rank <= 90:
            product_type = identify_product(item["title"])
            if product_type is None:
                continue
            our_positions.append({
                "rank": organic_rank,
                "title_short": product_type,
                "price": item["price"],
            })
        elif organic_rank <= 5 and not item["is_ours"]:
            brand = identify_brand(item["title"])
            if brand:
                top_competitors.append({
                    "rank": organic_rank,
                    "brand": brand,
                })

    # PR 포함 우리 제품 위치
    pr_positions = []
    for i, item in enumerate(items, 1):
        if item["is_ours"] and item["is_pr"]:
            pr_positions.append(i)

    return {
        "keyword": keyword,
        "total_results": len(items),
        "pr_count": sum(1 for i in items if i["is_pr"]),
        "our_positions": our_positions,
        "our_pr_positions": pr_positions,
        "top_competitors": top_competitors,
    }


# 경쟁사 브랜드 목록 (제품 제목에서 매칭)
KNOWN_BRANDS = [
    "bbox", "b.box", "Bbox",
    "Richell", "richell", "リッチェル",
    "Pigeon", "pigeon", "ピジョン",
    "Combi", "combi", "コンビ",
    "サーモス", "THERMOS", "thermos",
    "ピーコック", "Peacock",
    "Bunnytoo", "bunnytoo",
    "リッタグリッタ", "Litta Glitta",
    "OXO", "oxo",
    "Munchkin", "munchkin", "マンチキン",
    "NUK", "nuk", "ヌーク",
    "Betta", "betta", "ベッタ",
    "EDISON", "edison", "エジソン",
    "SkipHop", "SKIP HOP",
]


def identify_brand(title: str) -> str | None:
    """제품 제목에서 알려진 경쟁 브랜드명 추출."""
    title_lower = title.lower()
    brand_map = {
        "bbox": "b.box", "b.box": "b.box",
        "richell": "Richell", "リッチェル": "Richell",
        "pigeon": "Pigeon", "ピジョン": "Pigeon",
        "combi": "Combi", "コンビ": "Combi",
        "サーモス": "THERMOS", "thermos": "THERMOS",
        "ピーコック": "Peacock", "peacock": "Peacock",
        "bunnytoo": "Bunnytoo",
        "リッタグリッタ": "Litta Glitta", "litta glitta": "Litta Glitta",
        "oxo": "OXO",
        "munchkin": "Munchkin", "マンチキン": "Munchkin",
        "nuk": "NUK", "ヌーク": "NUK",
        "betta": "Betta", "ベッタ": "Betta",
        "edison": "EDISON", "エジソン": "EDISON",
        "skiphop": "SkipHop", "skip hop": "SkipHop",
    }
    for key, brand in brand_map.items():
        if key in title_lower or key in title:
            return brand
    return None


def identify_product(title: str) -> str:
    """제품 제목에서 종류 판별."""
    if "ワンタッチ" in title:
        return "ワンタッチ"
    elif "ステンレス" in title:
        return "ステンレス"
    elif "PPSU" in title or "ppsu" in title.lower():
        return "PPSU"
    elif ("ニップル" in title or "ストロー" in title) and "マグ" not in title:
        if "4個入" in title:
            return "Replacement Nipple"
        if "2セット" in title or "２セット" in title:
            return "Replacement Straw"
        return None
    elif "グロミミ" in title or "grosmimi" in title.lower():
        return "GROSMIMI"
    return title[:15]


# ============================================================
# 다수결 투표 (순위 흔들림 방지)
# ============================================================

def _majority_vote(analyses: list[dict]) -> dict:
    """여러 번 검색 결과 중 다수결로 순위 확정.
    각 제품(title_short)별로 가장 많이 나온 순위를 선택."""
    from collections import Counter

    if len(analyses) == 1:
        return analyses[0]

    # 제품별 순위 수집
    product_ranks: dict[str, list[int]] = {}
    product_prices: dict[str, str] = {}
    for a in analyses:
        for pos in a["our_positions"]:
            prod = pos["title_short"]
            product_ranks.setdefault(prod, []).append(pos["rank"])
            product_prices[prod] = pos["price"]

    # 다수결: 가장 빈번한 순위, 동률이면 최빈값 중 최소
    voted_positions = []
    for prod, ranks in product_ranks.items():
        counter = Counter(ranks)
        most_common_rank = min(counter.most_common(), key=lambda x: (-x[1], x[0]))[0]
        voted_positions.append({
            "rank": most_common_rank,
            "title_short": prod,
            "price": product_prices.get(prod, ""),
        })

    voted_positions.sort(key=lambda x: x["rank"])

    # 나머지 필드는 마지막 분석 기준
    base = analyses[-1].copy()
    base["our_positions"] = voted_positions
    return base


# ============================================================
# 히스토리 관리
# ============================================================

def load_history() -> dict:
    """과거 순위 데이터 로드."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_history(history: dict):
    """순위 히스토리 저장."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_previous_ranks(history: dict, keyword: str) -> list[dict]:
    """전일 순위 데이터 가져오기."""
    kw_history = history.get(keyword, [])
    if len(kw_history) >= 2:
        return kw_history[-2].get("positions", [])
    return []


def calc_rank_change(current_rank: int, current_product: str, prev_positions: list[dict]) -> str:
    """전일 대비 순위 변동 표시 (제품 타입 기준 매칭)."""
    if not prev_positions:
        return ""
    for p in prev_positions:
        if p.get("title_short") == current_product:
            diff = p["rank"] - current_rank
            if diff > 0:
                return f"↑{diff}"
            elif diff < 0:
                return f"↓{abs(diff)}"
            return "→"
    return ""


# ============================================================
# 리포트 생성
# ============================================================

def format_teams_report(results: list[dict], history: dict, timestamp: str) -> str:
    """Teams 메시지용 리포트 포맷."""
    lines = [f"{timestamp} 기준 라쿠텐 키워드별 제품 순위\n"]

    summary_up = []
    summary_down = []
    summary_notfound = []

    for r in results:
        keyword = r["keyword"]
        positions = r["our_positions"]
        prev = get_previous_ranks(history, keyword)

        lines.append(f"■ {keyword}")

        if not positions:
            lines.append("  → PR 제외 45位内にない")
            summary_notfound.append(keyword)
            lines.append("")
            continue

        if len(positions) == 1:
            pos = positions[0]
            change = calc_rank_change(pos["rank"], pos["title_short"], prev)
            change_str = f" ({change})" if change else ""
            lines.append(f"  → PR 제외 {pos['rank']}위{change_str} — {pos['title_short']}")
        else:
            ranks = [str(p["rank"]) for p in positions]
            lines.append(f"  → PR 제외 {', '.join(ranks)}위")
            for pos in positions:
                change = calc_rank_change(pos["rank"], pos["title_short"], prev)
                change_str = f" ({change})" if change else ""
                lines.append(f"    {pos['rank']}위: {pos['title_short']}{change_str}")

        # 상위 경쟁 브랜드
        if r.get("top_competitors") and positions and positions[0]["rank"] > 5:
            seen = set()
            brand_lines = []
            for c in r["top_competitors"]:
                b = c["brand"]
                if b not in seen:
                    seen.add(b)
                    brand_lines.append(f"    {c['rank']}위-{b}")
            if brand_lines:
                lines.append(f"  ※ 상위: {brand_lines[0].strip()},")
                for bl in brand_lines[1:-1]:
                    lines.append(f"{bl},")
                if len(brand_lines) > 1:
                    lines.append(f"{brand_lines[-1]}")

        lines.append("")

        # 요약용 집계
        if positions and prev:
            best_rank = positions[0]["rank"]
            prev_best = min(p["rank"] for p in prev) if prev else best_rank
            diff = prev_best - best_rank
            if diff > 0:
                summary_up.append(f"{keyword}({prev_best}→{best_rank} ↑{diff})")
            elif diff < 0:
                summary_down.append(f"{keyword}({prev_best}→{best_rank} ↓{abs(diff)})")

    # ── 변동 분석 ──
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    # 상승/하락 상세 (키워드 + 제품명)
    detail_up = []
    detail_down = []
    for r in results:
        if not r["our_positions"] or not get_previous_ranks(history, r["keyword"]):
            continue
        prev = get_previous_ranks(history, r["keyword"])
        prev_best = min(p["rank"] for p in prev) if prev else None
        if prev_best is None:
            continue
        cur = r["our_positions"][0]
        diff = prev_best - cur["rank"]
        if diff > 0:
            detail_up.append(f"  {r['keyword']}: {prev_best}→{cur['rank']}위 (↑{diff}) — {cur['title_short']}")
        elif diff < 0:
            detail_down.append(f"  {r['keyword']}: {prev_best}→{cur['rank']}위 (↓{abs(diff)}) — {cur['title_short']}")

    if detail_up:
        lines.append("📈 상승")
        lines.extend(detail_up)
        lines.append("")
    if detail_down:
        lines.append("📉 하락")
        lines.extend(detail_down)
        lines.append("")
    if not detail_up and not detail_down:
        lines.append("변동 없음")
        lines.append("")

    # 경쟁사 — 키워드별 상위 브랜드
    brand_count = {}
    brand_keywords = {}
    for r in results:
        for c in r.get("top_competitors", []):
            b = c["brand"]
            brand_count[b] = brand_count.get(b, 0) + 1
            if b not in brand_keywords:
                brand_keywords[b] = []
            brand_keywords[b].append(r["keyword"])
    if brand_count:
        lines.append("🏷 경쟁사 (상위 5위 내 자주 등장)")
        sorted_brands = sorted(brand_count.items(), key=lambda x: -x[1])
        for brand, cnt in sorted_brands[:5]:
            kws = brand_keywords[brand][:3]
            lines.append(f"  {brand} ({cnt}개 키워드) — {', '.join(kws)}")

    lines.append("\n전달드립니다")

    # 경쟁사 키워드 제안은 별도 메시지로 (discover_competitor_keywords에서 처리)

    return "\n".join(lines)


# ============================================================
# 경쟁사 키워드 발견
# ============================================================

# 경쟁사 키워드 후보 파일 (세은 승인 대기)
COMPETITOR_KW_FILE = TMP_DIR / "competitor_keyword_candidates.json"

def discover_competitor_keywords(results: list[dict]) -> list[dict]:
    """경쟁사 상품 타이틀에서 우리가 추적하지 않는 키워드 후보 추출."""
    import re

    # 경쟁사 상품 타이틀 수집
    competitor_titles = []
    for r in results:
        for item in r.get("_raw_items", []):
            if not item.get("is_ours") and not item.get("is_pr"):
                brand = identify_brand(item.get("title", ""))
                if brand:
                    competitor_titles.append({
                        "brand": brand,
                        "title": item["title"],
                        "keyword": r["keyword"],
                        "rank": item.get("organic_rank", 0),
                    })

    # 타이틀에서 자주 나오는 일본어 키워드 패턴 추출
    kw_patterns = [
        r"(保冷\s*保温)", r"(食洗機\s*対応)", r"(漏れない)", r"(こぼれない)",
        r"(ワンタッチ)", r"(哺乳瓶)", r"(離乳食)", r"(出産祝い)",
        r"(保育園)", r"(お出かけ)", r"(軽量)", r"(BPAフリー)",
        r"(トライタン)", r"(シリコン)", r"(両手)", r"(コップ飲み)",
        r"(スパウト)", r"(マグセット)", r"(水筒\s*キッズ)", r"(ベビー\s*水筒)",
        r"(ストロー\s*水筒)", r"(保温\s*マグ)", r"(ストロー\s*練習)",
    ]

    kw_counts = {}
    for ct in competitor_titles:
        title = ct["title"]
        for pat in kw_patterns:
            m = re.search(pat, title)
            if m:
                kw = m.group(1).strip()
                if kw not in kw_counts:
                    kw_counts[kw] = {"count": 0, "brands": set(), "example_titles": []}
                kw_counts[kw]["count"] += 1
                kw_counts[kw]["brands"].add(ct["brand"])
                if len(kw_counts[kw]["example_titles"]) < 2:
                    kw_counts[kw]["example_titles"].append(ct["title"][:40])

    # 현재 추적 키워드와 비교해서 우리가 안 쓰는 것만 필터
    current_kws_lower = {k.lower().replace(" ", "") for k in DEFAULT_KEYWORDS}
    candidates = []
    for kw, info in sorted(kw_counts.items(), key=lambda x: -x[1]["count"]):
        kw_clean = kw.lower().replace(" ", "")
        # 현재 추적 중인 키워드에 포함되어 있으면 스킵
        if any(kw_clean in ck or ck in kw_clean for ck in current_kws_lower):
            continue
        if info["count"] >= 2:  # 최소 2번 이상 등장
            candidates.append({
                "keyword": kw,
                "count": info["count"],
                "brands": list(info["brands"]),
                "examples": info["example_titles"],
            })

    # 파일에 저장
    if candidates:
        COMPETITOR_KW_FILE.write_text(
            json.dumps(candidates, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    return candidates


def format_competitor_kw_suggestion(candidates: list[dict]) -> str:
    """경쟁사 키워드 제안 메시지 포맷."""
    if not candidates:
        return ""

    lines = ["🔍 경쟁사가 쓰는데 우리가 안 추적하는 키워드", ""]
    for c in candidates[:5]:
        brands_str = ", ".join(c["brands"][:3])
        lines.append(f"  「{c['keyword']}」 — {brands_str} ({c['count']}건)")
    lines.append("")
    lines.append("추가할 키워드 있으면 말해줘!")
    return "\n".join(lines)


# ============================================================
# Teams 발송
# ============================================================

def send_teams_message(message: str) -> bool:
    """Teams webhook으로 메시지 발송."""
    if not TEAMS_WEBHOOK_URL:
        print("[WARN] TEAMS_WEBHOOK_URL 미설정 — 발송 건너뜀")
        return False

    import urllib.request

    payload = {"text": message.replace("\n", "<br>")}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TEAMS_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 202):
                print("[OK] Teams 발송 완료")
                return True
            print(f"[WARN] Teams 응답: {resp.status}")
            return False
    except Exception as e:
        print(f"[ERROR] Teams 발송 실패: {e}")
        return False


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="라쿠텐 키워드별 검색 순위 트래커")
    parser.add_argument("--dry-run", action="store_true", help="Teams 발송 없이 콘솔 출력만")
    parser.add_argument("--keywords", help="추적할 키워드 (쉼표 구분)")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help="검색 페이지 수 (기본 2)")
    args = parser.parse_args()

    keywords = args.keywords.split(",") if args.keywords else DEFAULT_KEYWORDS
    now = datetime.now(KST)
    timestamp = now.strftime("%y.%m.%d %H:%M")
    date_key = now.strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"라쿠텐 키워드 순위 트래커 (Playwright) — {timestamp}")
    print(f"키워드 {len(keywords)}개 추적 시작")
    print(f"{'='*60}\n")

    # 히스토리 로드
    history = load_history()

    # Playwright 브라우저 한 번만 열기
    from playwright.sync_api import sync_playwright

    # 실제 Chrome UA로 크롤링 (Playwright 기본 UA는 라쿠텐 검색 랭킹이 달라짐)
    CHROME_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pw_page = browser.new_page(
            user_agent=CHROME_UA,
            locale="ja-JP",
            viewport={"width": 1920, "height": 1080},
        )

        for i, kw in enumerate(keywords, 1):
            print(f"[{i}/{len(keywords)}] '{kw}' 검색 중...")

            # 3회 검색 → 다수결로 순위 확정 (동점 근처 흔들림 방지)
            SAMPLE_COUNT = 3
            all_analyses = []
            for trial in range(SAMPLE_COUNT):
                items = scrape_keyword(kw, args.max_pages, pw_page)
                analysis = analyze_keyword(kw, items)
                all_analyses.append(analysis)
                if trial < SAMPLE_COUNT - 1:
                    time.sleep(1)

            # 다수결: 각 제품별로 가장 많이 나온 순위 선택
            analysis = _majority_vote(all_analyses)

            pr_count = analysis["pr_count"]
            total = analysis["total_results"]
            organic_count = total - pr_count
            print(f"  → {total}개 수집 (오가닉: {organic_count}, PR: {pr_count}) [x{SAMPLE_COUNT} 다수결]")

            if analysis["our_positions"]:
                ranks = ", ".join(f"{p_['rank']}위({p_['title_short']})" for p_ in analysis["our_positions"])
                print(f"  → 우리 제품: {ranks}")
            else:
                print(f"  → 45位内にない")

            # raw items 보존 (경쟁사 키워드 분석용)
            analysis["_raw_items"] = items
            results.append(analysis)

            # rate limit
            if i < len(keywords):
                time.sleep(1.5)

        browser.close()

    # 리포트 생성
    report = format_teams_report(results, history, timestamp)

    print(f"\n{'='*60}")
    print("리포트 미리보기:")
    print(f"{'='*60}")
    print(report)
    print(f"{'='*60}\n")

    # 히스토리 업데이트
    for r in results:
        kw = r["keyword"]
        if kw not in history:
            history[kw] = []
        entry = {
            "date": date_key,
            "timestamp": now.isoformat(),
            "positions": r["our_positions"],
        }
        existing_idx = next(
            (i for i, h in enumerate(history[kw]) if h["date"] == date_key),
            None,
        )
        if existing_idx is not None:
            history[kw][existing_idx] = entry
        else:
            history[kw].append(entry)
        history[kw] = history[kw][-30:]
    save_history(history)
    print(f"[OK] 히스토리 저장: {HISTORY_FILE}")

    # 결과 JSON 저장
    result_file = TMP_DIR / f"rakuten_rank_{date_key}.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": now.isoformat(),
            "keywords": len(keywords),
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"[OK] 결과 저장: {result_file}")

    # 경쟁사 키워드 발견
    comp_candidates = discover_competitor_keywords(results)
    if comp_candidates:
        comp_msg = format_competitor_kw_suggestion(comp_candidates)
        print(f"\n{comp_msg}")
        report = report + "\n\n" + comp_msg

    # Teams 발송
    if not args.dry_run:
        send_teams_message(report)
    else:
        print("[DRY-RUN] Teams 발송 건너뜀")


if __name__ == "__main__":
    main()
