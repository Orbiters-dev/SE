"""
調査マン: 競合・参考ブランドのTwitter運用を週次で調査しTeamsに報告する。

Flow:
  Firecrawlで各ブランドの最新ツイートを収集
  → Claudeで投稿傾向・カテゴリ・戦略を分析
  → Teams Webhookに調査レポートを送信
"""

import os
import sys
import json
import time
import logging
import subprocess
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
FIRECRAWL_DIR = PROJECT_ROOT / ".firecrawl"
JST = timezone(timedelta(hours=9))
MODEL = "claude-sonnet-4-20250514"

# ── 調査対象ブランド ──────────────────────────────────────────────────────────

BRANDS = {
    "競合": [
        {"name": "ピジョン",      "handle": "pigeon_official_jp", "query": "ピジョン 育児 site:x.com"},
        {"name": "コンビ",        "handle": "combi_jp",           "query": "コンビ ベビー site:x.com"},
        {"name": "リッチェル",    "handle": "richell_jp",         "query": "リッチェル マグ site:x.com"},
        {"name": "NUKジャパン",   "handle": "nuk_japan",          "query": "NUK 赤ちゃん site:x.com"},
        {"name": "マンチキン",    "handle": "munchkin_japan",     "query": "マンチキン ベビー site:x.com"},
        {"name": "ファルスカ",    "handle": "farska_jp",          "query": "ファルスカ ベビー site:x.com"},
        {"name": "カトージ",      "handle": "katoji_official",    "query": "カトージ 赤ちゃん site:x.com"},
        {"name": "Joie",          "handle": "joie_japan",         "query": "Joie ベビーカー チャイルドシート site:x.com"},
    ],
    "参考（ベビー）": [
        {"name": "アカチャンホンポ", "handle": "akachanhonpo",     "query": "アカチャンホンポ 育児 site:x.com"},
        {"name": "西松屋",          "handle": "nishimatsuya_com", "query": "西松屋 赤ちゃん site:x.com"},
        {"name": "BABYBJORN",       "handle": "babybjorn",        "query": "BabyBjorn baby site:x.com"},
        {"name": "エルゴベビー",    "handle": "ergobaby_jp",      "query": "エルゴベビー 抱っこ紐 site:x.com"},
    ],
    "参考（Kコスメ・韓国ブランド）": [
        {"name": "イニスフリー",  "handle": "innisfree_jp",       "query": "イニスフリー innisfree site:x.com"},
        {"name": "COSRX",         "handle": "cosrx_japan",        "query": "COSRX コスアールエックス site:x.com"},
        {"name": "Anua",          "handle": "anua_japan",         "query": "Anua アヌア スキンケア site:x.com"},
        {"name": "Laneige",       "handle": "laneige_jp",         "query": "Laneige ラネージュ site:x.com"},
    ],
    "参考（人気ブランドSNS運用）": [
        {"name": "無印良品",      "handle": "muji_net",           "query": "無印良品 MUJI 育児 暮らし site:x.com"},
        {"name": "フェリシモ",    "handle": "felissimo",          "query": "フェリシモ ママ 子育て site:x.com"},
        {"name": "北欧、暮らしの道具店", "handle": "hokuoh_kurashi", "query": "北欧暮らしの道具店 ライフスタイル site:x.com"},
    ],
}


# ── Firecrawl検索 ─────────────────────────────────────────────────────────────

def search_brand_tweets(brand: dict, limit: int = 10) -> list[dict]:
    """Firecrawlでブランドの最新ツイートを検索する。"""
    from firecrawl import FirecrawlApp

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        logger.warning("FIRECRAWL_API_KEY not set")
        return []

    try:
        app = FirecrawlApp(api_key=api_key)
        result = app.search(brand["query"], limit=limit)
        # Handle both dict response and SearchData object (newer SDK uses .web)
        if hasattr(result, "web"):
            items = result.web or []
        elif hasattr(result, "data"):
            items = result.data or []
        else:
            items = result.get("web", result.get("data", [])) if isinstance(result, dict) else []

        tweets = []
        for item in items:
            url = item.get("url", "") if isinstance(item, dict) else getattr(item, "url", "")
            if "x.com" in url and "/status/" in url:
                tweets.append({
                    "url": url,
                    "title": item.get("title", "") if isinstance(item, dict) else getattr(item, "title", ""),
                    "description": item.get("description", "") if isinstance(item, dict) else getattr(item, "description", ""),
                })
        return tweets
    except Exception as e:
        logger.warning(f"Search failed for {brand['name']}: {e}")

    return []


# ── Claude分析 ────────────────────────────────────────────────────────────────

def analyze_brand(brand: dict, tweets: list[dict]) -> str:
    """Claudeでブランドのツイート傾向を分析する。"""
    import anthropic

    if not tweets:
        return "ツイートが見つかりませんでした。"

    tweet_texts = "\n".join([
        f"- {t.get('description', t.get('title', ''))[:100]}"
        for t in tweets[:8]
    ])

    prompt = f"""以下は「{brand['name']}」(@{brand['handle']})の最近のツイートです。

{tweet_texts}

★最重要★ まず最初に「グロミミへの示唆」を書いてください。その後に残りを書いてください。

1. **グロミミへの示唆**（最初に必ず書く）: 参考にできる点・差別化できる点（2〜3行）
2. **投稿テーマ**: どんな内容が多いか（1行）
3. **トーン**: 硬い/柔らかい、感情的/情報的など（1行）
4. **ハッシュタグ戦略**: よく使うタグのパターン（1行）
5. **イベント・キャンペーン**: 開催中のイベント・コラボ（1行）

箇条書きで簡潔に。"""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        resp = client.messages.create(
            model=MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Claude analysis failed for {brand['name']}: {e}")
        return "分析できませんでした。"


# ── Excel生成 ─────────────────────────────────────────────────────────────────

def create_research_excel(results: dict, date_str: str) -> Path:
    """調査結果をExcelファイルに出力する。"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "競合調査"

    # ヘッダー
    headers = ["カテゴリ", "ブランド名", "ツイート件数", "分析結果", "サンプルURL①", "サンプルURL②", "サンプルURL③"]
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # データ行
    row = 2
    fill_map = {
        "競合":                     PatternFill(start_color="DEEAF1", end_color="DEEAF1", fill_type="solid"),
        "参考（ベビー）":           PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid"),
        "参考（Kコスメ・韓国ブランド）": PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid"),
        "参考（人気ブランドSNS運用）":  PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid"),
    }
    fill_default = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")

    for category, brand_results in results.items():
        fill = fill_map.get(category, fill_default)
        for brand_name, data in brand_results.items():
            urls = data.get("sample_urls", [])
            ws.cell(row=row, column=1, value=category).fill = fill
            ws.cell(row=row, column=2, value=brand_name).fill = fill
            ws.cell(row=row, column=3, value=data.get("tweet_count", 0)).fill = fill
            analysis_cell = ws.cell(row=row, column=4, value=data.get("analysis", ""))
            analysis_cell.fill = fill
            analysis_cell.alignment = Alignment(wrap_text=True)
            for i, url in enumerate(urls[:3]):
                ws.cell(row=row, column=5 + i, value=url).fill = fill
            row += 1

    # 列幅調整
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 60
    for col in ["E", "F", "G"]:
        ws.column_dimensions[col].width = 40

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    path = TMP_DIR / f"twitter_research_{date_str}.xlsx"
    wb.save(path)
    logger.info(f"Research Excel saved: {path}")
    return path


# ── Teams報告 ─────────────────────────────────────────────────────────────────

def send_report(results: dict) -> None:
    """調査レポートをTeamsに送信する。"""
    import requests

    webhook_url = os.getenv("TEAMS_WEBHOOK_URL") or os.getenv("TEAMS_MASTER_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("TEAMS_WEBHOOK_URL not set")
        return

    today = datetime.now(JST).strftime("%Y-%m-%d（%a）")
    lines = [f"🔍 **調査マン週次レポート** {today}\n"]

    for category, brand_results in results.items():
        lines.append(f"## {category}ブランド")
        for brand_name, data in brand_results.items():
            tweet_count = data.get("tweet_count", 0)
            analysis = data.get("analysis", "")
            lines.append(f"\n### {brand_name}（直近{tweet_count}件）")
            lines.append(analysis)
        lines.append("")

    message = "\n".join(lines)

    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=15)
        resp.raise_for_status()
        logger.info("Research report sent to Teams")
    except Exception as e:
        logger.error(f"Teams send failed: {e}")


# ── メイン ────────────────────────────────────────────────────────────────────

def run_research() -> None:
    """全ブランドを調査してTeamsに報告する。"""
    logger.info("=== 調査マン START ===")
    results = {}

    for category, brands in BRANDS.items():
        results[category] = {}
        for brand in brands:
            logger.info(f"Searching: {brand['name']}")
            tweets = search_brand_tweets(brand, limit=10)
            logger.info(f"  Found {len(tweets)} tweets")

            analysis = analyze_brand(brand, tweets)

            results[category][brand["name"]] = {
                "tweet_count": len(tweets),
                "analysis": analysis,
                "sample_urls": [t["url"] for t in tweets[:3]],
            }

            time.sleep(3)  # Firecrawl rate limit

    # ローカル保存
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(JST).strftime("%Y-%m-%d")
    out_path = TMP_DIR / f"twitter_research_{date_str}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved: {out_path}")

    # ── Save intel for 企画マン ──────────────────────────────────────────────
    try:
        intel_dir = TMP_DIR / "twitter_intel"
        intel_dir.mkdir(parents=True, exist_ok=True)
        intel_path = intel_dir / "competitor_report.json"

        # Extract top_topics and top_formats from analysis texts
        top_topics = []
        top_formats = []
        for _category, brand_results in results.items():
            for brand_name, data in brand_results.items():
                analysis = data.get("analysis", "")
                if analysis and analysis not in ("ツイートが見つかりませんでした。", "分析できませんでした。"):
                    top_topics.append({
                        "brand": brand_name,
                        "analysis": analysis,
                    })
                    # Detect format patterns
                    for fmt_kw in ["質問形", "質問型", "あるある", "キャンペーン", "プレゼント", "UGC", "リポスト", "アンケート", "投票"]:
                        if fmt_kw in analysis:
                            top_formats.append({"brand": brand_name, "format": fmt_kw})

        intel_data = {
            "source": "調査マン",
            "date": date_str,
            "top_topics": top_topics,
            "top_formats": top_formats,
            "raw_file": str(out_path),
        }
        with open(intel_path, "w", encoding="utf-8") as f:
            json.dump(intel_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Intel saved for 企画マン: {intel_path}")
    except Exception as e:
        logger.warning(f"Intel save failed: {e}")

    send_report(results)

    # Excel生成 → Teamsにアップロード
    try:
        excel_path = create_research_excel(results, date_str)
        from teams_upload import upload_file
        upload_file(
            str(excel_path),
            notify=True,
            message=f"📊 {date_str} 競合Twitter調査レポート（Excelで確認できます）",
        )
        logger.info("Research Excel uploaded to Teams")
    except Exception as e:
        logger.warning(f"Excel upload failed: {e}")

    logger.info("=== 調査マン DONE ===")


if __name__ == "__main__":
    run_research()
