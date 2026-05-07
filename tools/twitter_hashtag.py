"""
ハッシュタグ調査マン: 日本のベビー/育児/ママ向けトレンドハッシュタグを週次で調査しTeamsに報告する。

Flow:
  Firecrawlで日本Twitter上のトレンドハッシュタグを収集
  → Claudeで「@grosmimi_jp」運用に活用できるかを分析
  → Teams Webhookに調査レポートを送信
  → 企画マン用にintel保存
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
JST = timezone(timedelta(hours=9))
MODEL = "claude-sonnet-4-20250514"

# ── 調査カテゴリ ──────────────────────────────────────────────────────────────
# @grosmimi_jp = 韓国発ベビーマグブランドの日本公式アカウント

CATEGORIES = [
    {
        "name": "育児・ママライフ",
        "queries": [
            "育児 ハッシュタグ 人気 2026 site:x.com",
            "ママタグ 育児タグ 人気 site:x.com",
            "0歳 1歳 ハッシュタグ 育児 site:x.com",
        ],
    },
    {
        "name": "ベビー用品・離乳食",
        "queries": [
            "ベビー用品 ハッシュタグ 人気 site:x.com",
            "離乳食 ハッシュタグ 人気 site:x.com",
            "ストローマグ 水筒 ハッシュタグ site:x.com",
        ],
    },
    {
        "name": "韓国・K育児・Kベビー",
        "queries": [
            "韓国ベビー ハッシュタグ 人気 site:x.com",
            "韓国育児 ママ ハッシュタグ site:x.com",
            "韓国子供服 韓国ベビー用品 site:x.com",
        ],
    },
    {
        "name": "季節・行事（直近）",
        "queries": [
            "5月 育児 ハッシュタグ 人気 site:x.com",
            "母の日 ベビー ハッシュタグ site:x.com",
            "GW 子育て ハッシュタグ site:x.com",
        ],
    },
]


# ── Firecrawl検索 ─────────────────────────────────────────────────────────────

def search_query(query: str, limit: int = 8) -> list[dict]:
    """Firecrawlで指定クエリのツイート/関連ページを検索する。"""
    from firecrawl import FirecrawlApp

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        logger.warning("FIRECRAWL_API_KEY not set")
        return []

    try:
        app = FirecrawlApp(api_key=api_key)
        result = app.search(query, limit=limit)
        if hasattr(result, "web"):
            items = result.web or []
        elif hasattr(result, "data"):
            items = result.data or []
        else:
            items = result.get("web", result.get("data", [])) if isinstance(result, dict) else []

        hits = []
        for item in items:
            url = item.get("url", "") if isinstance(item, dict) else getattr(item, "url", "")
            title = item.get("title", "") if isinstance(item, dict) else getattr(item, "title", "")
            desc = item.get("description", "") if isinstance(item, dict) else getattr(item, "description", "")
            hits.append({"url": url, "title": title, "description": desc})
        return hits
    except Exception as e:
        logger.warning(f"Search failed for '{query}': {e}")
        return []


# ── Claude分析 ────────────────────────────────────────────────────────────────

def analyze_category(category_name: str, raw_hits: list[dict]) -> dict:
    """Claudeで人気ハッシュタグを抽出 + 活用度を分析。

    Returns:
        {
            "tags": [{"tag": "#育児", "reason": "...", "use_score": 5}, ...],
            "summary": "...",
        }
    """
    import anthropic

    if not raw_hits:
        return {"tags": [], "summary": "検索結果が見つかりませんでした。"}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set")
        return {"tags": [], "summary": "Claude APIキー未設定。"}

    # 検索ヒットを文字列化
    raw_text = "\n".join(
        f"- {h.get('title','')} | {h.get('description','')[:150]} | {h.get('url','')}"
        for h in raw_hits[:20]
    )

    prompt = f"""あなたは日本のSNSハッシュタグ調査の専門家。

下記は「{category_name}」関連でTwitterから収集された生データです:
{raw_text}

このデータから、@grosmimi_jp（韓国発ベビーマグブランドの日本公式アカウント、6-24ヶ月のママがメインターゲット）が
今週活用できそうな**人気ハッシュタグTop 5**を抽出してください。

以下JSON形式のみで返答してください（コードブロックなし、純粋なJSONのみ）:
{{
  "tags": [
    {{"tag": "#育児", "reason": "なぜ@grosmimi_jpに合うか1行", "use_score": 5}},
    ...
  ],
  "summary": "今週このカテゴリで気づいたトレンド傾向を2-3行で"
}}

use_scoreは1-5（5=今すぐ使うべき、1=避けるべき）。tagは「#」付き。tags最大5個。"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        # JSON抽出（コードブロック除去）
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Claude analysis failed for {category_name}: {e}")
        return {"tags": [], "summary": f"分析失敗: {e}"}


# ── Teams報告 ─────────────────────────────────────────────────────────────────

def send_report(results: dict) -> None:
    """調査レポートをTeamsに送信する。"""
    import requests

    webhook_url = os.getenv("TEAMS_WEBHOOK_URL") or os.getenv("TEAMS_MASTER_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("TEAMS_WEBHOOK_URL not set")
        return

    today = datetime.now(JST).strftime("%Y-%m-%d（%a）")
    lines = [f"🏷️ **ハッシュタグ調査マン週次レポート** {today}\n"]
    lines.append("@grosmimi_jp 用に今週活用できる人気ハッシュタグ:\n")

    for cat_name, data in results.items():
        tags = data.get("tags", [])
        summary = data.get("summary", "")
        lines.append(f"## {cat_name}")
        if tags:
            for t in tags:
                lines.append(f"- {t.get('tag','')}（★{t.get('use_score',0)}）{t.get('reason','')}")
        else:
            lines.append("- (該当タグなし)")
        if summary:
            lines.append(f"\n💡 {summary}")
        lines.append("")

    message = "\n".join(lines)

    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=15)
        resp.raise_for_status()
        logger.info("Hashtag report sent to Teams")
    except Exception as e:
        logger.error(f"Teams send failed: {e}")


# ── メイン ────────────────────────────────────────────────────────────────────

def run_hashtag_research() -> None:
    """全カテゴリを調査してTeamsに報告する。"""
    logger.info("=== ハッシュタグ調査マン START ===")
    results = {}

    for category in CATEGORIES:
        cat_name = category["name"]
        logger.info(f"Searching category: {cat_name}")

        raw_hits = []
        for q in category["queries"]:
            hits = search_query(q, limit=8)
            raw_hits.extend(hits)
            time.sleep(2)  # Firecrawl rate limit

        logger.info(f"  Total {len(raw_hits)} hits")

        analysis = analyze_category(cat_name, raw_hits)
        results[cat_name] = {
            "raw_count": len(raw_hits),
            "tags": analysis.get("tags", []),
            "summary": analysis.get("summary", ""),
        }

        time.sleep(3)

    # ローカル保存
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(JST).strftime("%Y-%m-%d")
    out_path = TMP_DIR / f"twitter_hashtag_{date_str}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved: {out_path}")

    # 企画マン用intel
    try:
        intel_dir = TMP_DIR / "twitter_intel"
        intel_dir.mkdir(parents=True, exist_ok=True)
        intel_path = intel_dir / "hashtag_report.json"

        all_tags = []
        for cat_name, data in results.items():
            for t in data.get("tags", []):
                all_tags.append({
                    "category": cat_name,
                    "tag": t.get("tag", ""),
                    "use_score": t.get("use_score", 0),
                    "reason": t.get("reason", ""),
                })
        # use_score降順
        all_tags.sort(key=lambda x: -x.get("use_score", 0))

        intel_data = {
            "source": "ハッシュタグ調査マン",
            "date": date_str,
            "top_tags": all_tags,
            "raw_file": str(out_path),
        }
        with open(intel_path, "w", encoding="utf-8") as f:
            json.dump(intel_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Intel saved for 企画マン: {intel_path}")
    except Exception as e:
        logger.warning(f"Intel save failed: {e}")

    send_report(results)
    logger.info("=== ハッシュタグ調査マン DONE ===")


if __name__ == "__main__":
    run_hashtag_research()
