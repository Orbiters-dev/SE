"""
WAT Tool: Generate weekly content plan (20 ideas) as Excel file.
Pipeline: Firecrawl trend scraping + competitor insights -> Claude analysis -> Excel output.

Sources: bbox IG, Pigeon IG, JP parenting IG hashtags, Twitter, MamaStar, Ameblo
         + competitor_insights.json (from weekly_ig_competitor_analysis.py)
Output: .tmp/weekly_content_plan_YYYYMMDD.xlsx

Usage:
    python tools/plan_weekly_content.py                              # 20 ideas (meme:10, brand:10)
    python tools/plan_weekly_content.py --distribution "meme:5,brand:5"  # custom
    python tools/plan_weekly_content.py --dry-run                    # scrape trends only, no Excel
"""

import os
import sys
import re
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for Korean/Japanese output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

import anthropic
from firecrawl import FirecrawlApp
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

TMP_DIR = Path(__file__).parent.parent / ".tmp"
TRENDS_CACHE = TMP_DIR / "weekly_trends_raw.json"
INSIGHTS_PATH = TMP_DIR / "competitor_insights.json"
MODEL = "claude-sonnet-4-20250514"
RATE_LIMIT_DELAY = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Color palette ────────────────────────────────────────────────────────────

NAVY = "1F3864"
SLATE_BLUE = "2E5090"
LIGHT_BLUE = "D6E4F0"
WHITE = "FFFFFF"
OFF_WHITE = "F5F7FA"
DARK_GRAY = "343A40"
MID_GRAY = "6C757D"

CATEGORY_COLORS = {
    "meme": "FFE0B2",       # orange light
    "brand": "BBDEFB",      # blue light
    "tips": "C8E6C9",       # green light
    "k_babyfood": "F8BBD0", # pink light
}
CATEGORY_LABELS = {
    "meme": "밈/바이럴",
    "brand": "브랜드 제품",
    "tips": "육아 상식/팁",
    "k_babyfood": "K-이유식",
}

# ── Trend Sources ────────────────────────────────────────────────────────────

INSTAGRAM_ACCOUNTS = [
    # bbox (picnob.com — picuki.com is dead since 2026-03)
    "https://www.picnob.com/profile/bboxforkidsjapan/",
    # Pigeon
    "https://www.picnob.com/profile/pigeon_official.jp/",
]

INSTAGRAM_HASHTAGS = [
    "https://inflact.com/profiles/tag/%E8%82%B2%E5%85%90/",           # 育児
    "https://inflact.com/profiles/tag/%E3%83%9E%E3%83%9E/",           # ママ
    "https://inflact.com/profiles/tag/%E5%AD%90%E8%82%B2%E3%81%A6/",  # 子育て
    "https://inflact.com/profiles/tag/%E9%9B%A2%E4%B9%B3%E9%A3%9F/",  # 離乳食
    "https://inflact.com/profiles/tag/%E8%82%B2%E5%85%90%E3%81%82%E3%82%8B%E3%81%82%E3%82%8B/",  # 育児あるある
]

TWITTER_URLS = [
    "https://nitter.poast.org/search?f=tweets&q=%23%E8%82%B2%E5%85%90%E3%81%82%E3%82%8B%E3%81%82%E3%82%8B",
    "https://nitter.poast.org/search?f=tweets&q=%23%E8%82%B2%E5%85%90%E6%BC%AB%E7%94%BB",
    "https://nitter.poast.org/search?f=tweets&q=%23%E3%83%AF%E3%83%B3%E3%82%AA%E3%83%9A%E8%82%B2%E5%85%90",
]

COMMUNITY_URLS = [
    "https://mamastar.jp/bbs/ranking",
    "https://blogger.ameba.jp/genres/baby",
]


# ── Scraping ─────────────────────────────────────────────────────────────────

def scrape_page(app: FirecrawlApp, url: str, retries: int = 2) -> str:
    """Scrape a single page via Firecrawl, return markdown."""
    for attempt in range(retries):
        try:
            result = app.scrape(
                url,
                formats=["markdown"],
                wait_for=3000,
                only_main_content=True,
                timeout=60000,
            )
            md = ""
            if hasattr(result, "markdown"):
                md = result.markdown or ""
            elif isinstance(result, dict):
                md = result.get("markdown", "")
            logger.info(f"  -> {len(md)} chars from {url[:70]}")
            return md
        except Exception as e:
            logger.warning(f"  Attempt {attempt+1}/{retries} failed for {url[:70]}: {e}")
            if attempt < retries - 1:
                time.sleep(RATE_LIMIT_DELAY * (attempt + 1))
    return ""


def scrape_all_trends(app: FirecrawlApp, max_pages: int) -> list[dict]:
    """Scrape trends from all sources, return list of trend items."""
    all_items = []

    # Instagram accounts (bbox, Pigeon)
    logger.info("Scraping Instagram accounts (bbox, Pigeon)...")
    for url in INSTAGRAM_ACCOUNTS[:max_pages]:
        md = scrape_page(app, url)
        if md:
            items = _parse_instagram(md, url)
            all_items.extend(items)
        time.sleep(RATE_LIMIT_DELAY)

    # Instagram hashtags
    logger.info("Scraping Instagram hashtags...")
    for url in INSTAGRAM_HASHTAGS[:max_pages]:
        md = scrape_page(app, url)
        if md:
            items = _parse_instagram(md, url)
            all_items.extend(items)
        time.sleep(RATE_LIMIT_DELAY)

    # Twitter
    logger.info("Scraping Twitter/X...")
    for url in TWITTER_URLS[:max_pages]:
        md = scrape_page(app, url)
        if md:
            items = _parse_twitter(md, url)
            all_items.extend(items)
        time.sleep(RATE_LIMIT_DELAY)

    # Communities
    logger.info("Scraping communities (MamaStar, Ameblo)...")
    for url in COMMUNITY_URLS[:max_pages]:
        md = scrape_page(app, url)
        if md:
            items = _parse_community(md, url)
            all_items.extend(items)
        time.sleep(RATE_LIMIT_DELAY)

    # Deduplicate
    seen = set()
    unique = []
    for item in all_items:
        key = item.get("snippet", "")[:80]
        if key and key not in seen:
            seen.add(key)
            unique.append(item)

    logger.info(f"Total trends: {len(all_items)} -> Unique: {len(unique)}")
    return unique


def _is_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", text))


def _parse_instagram(md: str, url: str) -> list[dict]:
    items = []
    desc_pattern = re.compile(r"([^\n]{20,}(?:#\w+[^\n]*))", re.MULTILINE)
    for desc in desc_pattern.findall(md):
        hashtags = [f"#{h}" for h in re.findall(r"#(\w+)", desc) if _is_japanese(h)]
        if not hashtags and not _is_japanese(desc):
            continue
        items.append({
            "source": "instagram",
            "url": url,
            "snippet": re.sub(r"\s+", " ", desc).strip()[:400],
            "hashtags": hashtags[:10],
        })
    # Fallback: image alt texts
    if not items:
        for alt, _ in re.findall(r"\!\[([^\]]{10,})\]\((https?://[^\)]+)\)", md):
            if _is_japanese(alt):
                items.append({
                    "source": "instagram",
                    "url": url,
                    "snippet": alt.strip()[:400],
                    "hashtags": [],
                })
    return items[:20]


def _parse_twitter(md: str, url: str) -> list[dict]:
    items = []
    for block in re.split(r"\n(?=[@\[])", md):
        content = re.sub(r"\[([^\]]*)\]\([^\)]+\)", r"\1", block)
        content = re.sub(r"\!\[[^\]]*\]\([^\)]+\)", "", content)
        content = re.sub(r"[#*_`>]+", "", content)
        content = re.sub(r"\s+", " ", content).strip()
        if len(content) < 30:
            continue
        hashtags = [f"#{h}" for h in re.findall(r"#(\w+)", block) if _is_japanese(h)]
        items.append({
            "source": "twitter",
            "url": url,
            "snippet": content[:400],
            "hashtags": hashtags,
        })
    return items[:20]


def _parse_community(md: str, url: str) -> list[dict]:
    items = []
    for title, link in re.findall(r"\[([^\]]{10,})\]\((https?://[^\)]+)\)", md):
        if _is_japanese(title) and len(title) > 5:
            items.append({
                "source": "community",
                "url": link,
                "snippet": title.strip()[:400],
                "hashtags": [],
            })
    return items[:20]


# ── Claude Planning ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """あなたは日本の育児用品ブランド「Grosmimi」のSNSコンテンツストラテジストです。
トレンドデータを分析し、Instagramコンテンツ企画案を作成してください。

## カテゴリ（4種類から選択）
1. meme — ミーム/バイラル: 育児あるあるネタ、共感型バイラルコンテンツ
2. brand — ブランド製品: Grosmimi製品の紹介・説明コンテンツ
3. tips — 育児Tips: 実用的な育児情報・アドバイス
4. k_babyfood — K-離乳食: 韓国式離乳食コンテンツ

## ブランドガイドライン
- トーン: 温かく共感できる、少しユーモア（日本のママインフルエンサースタイル）
- 言語: 自然な日本語、絵文字を適切に活用
- 禁止: 医療的主張、論争になる育児アドバイス、競合批判
- ミーム/バイラルカテゴリでは製品露出禁止（プロフィールリンクのみ）

## 自社アカウント参考スタイル
- grosmimi_japan: ママ友のような温かい日本語トーン、インフルエンサーPRリールが高反応、PPSUストローマグの安全性訴求、教育カルーセル
- onzenna.official: UGCリポスト中心、1人称視点ミーム（例：「私はPPSUストローカップです」）、リアルな使用シーンの生活密着型コンテンツ
- 共通の学び: インフルエンサー/UGC風のリアルな使用感コンテンツが10〜100倍の反応を獲得する

## 出力要件
各企画案には以下を含めること:
- category: meme / brand / tips / k_babyfood
- topic: トピック（日本語）
- topic_ko: トピックの韓国語翻訳
- image_text: クリエイターがデザインに直接使える日本語テキスト（スライド別、改行区切り）
- image_concept: 各スライドにどんな写真/イラストを入れるかの具体的なイメージ構想（スライド別、改行区切り、例：「〜している赤ちゃんの写真」「〜のイラスト」）
- emphasis: デザイン時に強調すべき核心メッセージ
- caption: インスタキャプション（日本語+絵文字+CTA）
- caption_ko: キャプションの韓国語翻訳（意訳OK、自然な韓国語で）
- hashtags: カテゴリに合ったハッシュタグ15〜25個
- trend_ref: インスピレーション元（ソース+キーワード）"""


def _load_competitor_insights() -> str:
    """Load competitor insights JSON and format as text for Claude prompt."""
    if not INSIGHTS_PATH.exists():
        logger.info("No competitor insights found — skipping")
        return ""

    try:
        with open(INSIGHTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load competitor insights: {e}")
        return ""

    parts = []
    parts.append("## 競合ブランド分析（直近の人気コンテンツ）\n")

    # Content type performance
    type_perf = data.get("content_type_performance", {})
    if type_perf:
        parts.append("### コンテンツタイプ別パフォーマンス")
        for ct, stats in sorted(type_perf.items(), key=lambda x: x[1].get("avg_likes", 0), reverse=True):
            parts.append(f"- {ct}: 平均いいね {stats.get('avg_likes', 0)}, "
                         f"平均コメント {stats.get('avg_comments', 0)}, "
                         f"投稿数 {stats.get('count', 0)}")
        parts.append("")

    # Top posts
    top_posts = data.get("top_posts", [])[:10]
    if top_posts:
        parts.append("### 人気投稿TOP10")
        for i, p in enumerate(top_posts, 1):
            parts.append(f"{i}. [{p.get('brand', '')}] いいね{p.get('likes', 0)} / "
                         f"コメント{p.get('comments', 0)} / タイプ: {p.get('content_type', '')}")
            parts.append(f"   内容: {p.get('caption_snippet', '')[:120]}")
        parts.append("")

    return "\n".join(parts)


def _call_claude_for_plans(client: anthropic.Anthropic, prompt: str, batch_size: int) -> list[dict]:
    """Call Claude once and parse JSON plans. Returns list of plan dicts."""
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text

            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                json_str = text.split("```")[1].split("```")[0].strip()
            else:
                json_str = text.strip()

            result = json.loads(json_str)
            plans = result.get("plans", [])
            logger.info(f"Claude returned {len(plans)} plan(s)")
            return plans

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                prompt += "\n\n重要: 有効なJSONのみを出力してください。captionは200文字以内に短縮してください。"
                time.sleep(RATE_LIMIT_DELAY)
        except Exception as e:
            logger.error(f"Claude API error (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(2 * (attempt + 1))

    raise RuntimeError("Failed to get valid plans from Claude after all retries")


def generate_plans(client: anthropic.Anthropic, trends: list[dict], count: int,
                   distribution: dict | None = None) -> list[dict]:
    """Use Claude to generate content plan ideas from trends + competitor insights.
    Splits into batches of 5 to avoid token overflow."""
    # Summarize trends
    trends_text = ""
    for i, t in enumerate(trends[:60]):
        trends_text += (
            f"{i+1}. [{t['source']}] {t['snippet'][:200]}\n"
            f"   Tags: {', '.join(t.get('hashtags', []))}\n\n"
        )

    # Load competitor insights
    competitor_text = _load_competitor_insights()

    # Split distribution into batches of 5
    BATCH_SIZE = 5
    batches = []  # list of (batch_count, batch_dist_instruction)

    if distribution:
        for cat, cat_count in distribution.items():
            label = CATEGORY_LABELS.get(cat, cat)
            remaining = cat_count
            while remaining > 0:
                batch_n = min(remaining, BATCH_SIZE)
                batch_dist = f"以下のカテゴリ配分を厳守してください:\n- {label} ({cat}): {batch_n}個"
                batches.append((batch_n, batch_dist))
                remaining -= batch_n
    else:
        for start in range(0, count, BATCH_SIZE):
            batch_n = min(BATCH_SIZE, count - start)
            batch_dist = "4つのカテゴリ（meme, brand, tips, k_babyfood）をバランスよく配分"
            batches.append((batch_n, batch_dist))

    all_plans = []
    for batch_idx, (batch_count, dist_instruction) in enumerate(batches):
        logger.info(f"Generating batch {batch_idx+1}/{len(batches)} ({batch_count} plans)...")

        prompt = f"""以下のトレンドデータと競合分析を元に、{batch_count}個のInstagramコンテンツ企画案を作成してください。

## トレンドデータ
{trends_text}

{competitor_text}

## 重要: 競合分析の活用
- 上記の競合ブランドで反応が良いコンテンツタイプを参考にしてください
- 人気投稿のテーマや表現方法からインスピレーションを得てください
- ただしGrosmimi独自の差別化ポイントを必ず含めてください

## 注意事項
- {dist_instruction}
- image_textはクリエイターがすぐデザインに使える具体的な日本語テキスト（スライド1〜4の内容を改行区切りで）
- image_conceptは各スライドにどんな写真/イラストを配置するかの具体的な構想（例：「ストローマグを持って笑っている赤ちゃんの写真」「ママが離乳食を準備している手元のイラスト」）。スライド別に改行区切りで記述
- emphasisはデザイン時の核心ポイント（1〜2文）
- captionは実際のInstagramに投稿する完全なテキスト（200〜400文字、CTA含む）
- hashtagsは文字列の配列で15個まで
- topic_koはtopicの韓国語翻訳（自然な韓国語で）
- caption_koはcaptionの韓国語翻訳（意訳OK、自然な韓国語で。ハッシュタグは日本語のまま）
- trend_refはどのトレンドからインスピレーションを得たか（1文）

## 出力形式（JSONのみ出力、余計なテキスト禁止）
```json
{{
  "plans": [
    {{
      "category": "meme",
      "topic": "トピック",
      "topic_ko": "주제 한국어 번역",
      "image_text": "スライド1: テキスト\\nスライド2: テキスト\\nスライド3: テキスト\\nスライド4: テキスト",
      "image_concept": "スライド1: 〜している赤ちゃんの写真\\nスライド2: 〜のイラスト\\nスライド3: 製品のフラットレイ写真\\nスライド4: ママと赤ちゃんが〜している写真",
      "emphasis": "核心メッセージ",
      "caption": "完全なキャプション",
      "caption_ko": "캡션 한국어 번역",
      "hashtags": ["#育児", "#ママ"],
      "trend_ref": "ソース名"
    }}
  ]
}}
```"""

        batch_plans = _call_claude_for_plans(client, prompt, batch_count)
        all_plans.extend(batch_plans)

        if batch_idx < len(batches) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    logger.info(f"Total plans generated: {len(all_plans)}")
    return all_plans


# ── Excel Output ─────────────────────────────────────────────────────────────

def thin_border():
    s = Side(style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)


COLUMNS = [
    ("#",           5,  False),
    ("카테고리",    14, False),
    ("주제",        28, False),
    ("주제(한국어)", 28, False),
    ("이미지 문구", 45, True),
    ("이미지 구상", 50, True),
    ("강조 포인트", 30, True),
    ("캡션",        55, True),
    ("캡션(한국어)", 55, True),
    ("해시태그",    40, True),
    ("참고 트렌드", 30, True),
]


def build_excel(plans: list[dict], output_path: Path) -> None:
    """Write plans to a styled Excel file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "주간 기획안"
    ws.sheet_view.showGridLines = False

    # ── Header row ───────────────────────────────────────────────────────
    for ci, (header, width, _) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=ci, value=header)
        cell.font = Font(name="Calibri", bold=True, color=WHITE, size=11)
        cell.fill = PatternFill(fill_type="solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border()
        ws.column_dimensions[get_column_letter(ci)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"

    # ── Data rows ────────────────────────────────────────────────────────
    for ri, plan in enumerate(plans):
        row_idx = ri + 2
        cat_key = plan.get("category", "meme")
        cat_label = CATEGORY_LABELS.get(cat_key, cat_key)
        cat_bg = CATEGORY_COLORS.get(cat_key, OFF_WHITE)
        row_bg = OFF_WHITE if ri % 2 == 0 else WHITE

        values = [
            ri + 1,
            cat_label,
            plan.get("topic", ""),
            plan.get("topic_ko", ""),
            plan.get("image_text", ""),
            plan.get("image_concept", ""),
            plan.get("emphasis", ""),
            plan.get("caption", ""),
            plan.get("caption_ko", ""),
            " ".join(plan.get("hashtags", [])),
            plan.get("trend_ref", ""),
        ]

        for ci, val in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=ci, value=val)
            _, _, wrap = COLUMNS[ci - 1]

            # Category column gets special coloring
            bg = cat_bg if ci == 2 else row_bg

            cell.font = Font(name="Calibri", size=10, color=DARK_GRAY)
            cell.fill = PatternFill(fill_type="solid", fgColor=bg)
            cell.alignment = Alignment(
                horizontal="center" if ci <= 2 else "left",
                vertical="top",
                wrap_text=wrap,
            )
            cell.border = thin_border()

        ws.row_dimensions[row_idx].height = 120

    # ── Summary row ──────────────────────────────────────────────────────
    summary_row = len(plans) + 3
    ws.cell(row=summary_row, column=1, value="Summary").font = Font(
        name="Calibri", bold=True, size=10, color=NAVY
    )

    # Category counts
    from collections import Counter
    cat_counts = Counter(p.get("category", "?") for p in plans)
    summary_parts = []
    for key, label in CATEGORY_LABELS.items():
        cnt = cat_counts.get(key, 0)
        if cnt > 0:
            summary_parts.append(f"{label}: {cnt}")
    ws.cell(row=summary_row, column=2, value=" / ".join(summary_parts)).font = Font(
        name="Calibri", size=10, color=MID_GRAY
    )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.cell(row=summary_row + 1, column=2, value=f"Generated: {generated_at}").font = Font(
        name="Calibri", size=9, color=MID_GRAY, italic=True
    )

    wb.save(output_path)
    logger.info(f"Excel saved: {output_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate weekly content plan as Excel")
    parser.add_argument("--count", type=int, default=10,
                        help="Number of content ideas (default 10)")
    parser.add_argument("--max-pages", type=int, default=3,
                        help="Max pages per source for scraping (default 3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape trends only, skip Claude + Excel")
    parser.add_argument("--output", type=str, default=None,
                        help="Custom output path for Excel file")
    parser.add_argument("--distribution", type=str, default=None,
                        help="Category distribution e.g. 'meme:5,brand:5'")
    args = parser.parse_args()

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Scrape trends ────────────────────────────────────────────
    fc_key = os.getenv("FIRECRAWL_API_KEY")
    if not fc_key:
        raise EnvironmentError("FIRECRAWL_API_KEY not found. Check .env file.")

    app = FirecrawlApp(api_key=fc_key)
    logger.info("Starting trend collection...")
    trends = scrape_all_trends(app, max_pages=args.max_pages)

    # Cache trends
    with open(TRENDS_CACHE, "w", encoding="utf-8") as f:
        json.dump({
            "scraped_at": datetime.now().isoformat(),
            "total_items": len(trends),
            "items": trends,
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"Trends cached: {TRENDS_CACHE}")

    if args.dry_run:
        print(f"\n{'='*55}")
        print(f"  Dry run complete. {len(trends)} trends collected.")
        print(f"  Cached: {TRENDS_CACHE}")
        print(f"{'='*55}\n")
        return

    # ── Step 2: Generate plans with Claude ───────────────────────────────
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not found. Check .env file.")

    client = anthropic.Anthropic(api_key=api_key)
    logger.info(f"Generating {args.count} content plans with Claude...")
    # Parse distribution if provided
    distribution = None
    if args.distribution:
        distribution = {}
        for part in args.distribution.split(","):
            k, v = part.strip().split(":")
            distribution[k.strip()] = int(v.strip())
        # Override count to match distribution total
        args.count = sum(distribution.values())

    plans = generate_plans(client, trends, args.count, distribution=distribution)

    # ── Step 3: Write Excel ──────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d")
    output_path = Path(args.output) if args.output else TMP_DIR / f"weekly_content_plan_{ts}.xlsx"
    build_excel(plans, output_path)

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  Weekly Content Plan Generated")
    print(f"{'='*55}")
    print(f"  Ideas:  {len(plans)}")
    from collections import Counter
    cat_counts = Counter(p.get("category", "?") for p in plans)
    for key, label in CATEGORY_LABELS.items():
        cnt = cat_counts.get(key, 0)
        if cnt > 0:
            print(f"    {label}: {cnt}")
    print(f"  Output: {output_path}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
