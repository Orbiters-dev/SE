"""
WAT Tool: Analyze Japanese parenting trends and generate content plans.
Uses Claude API to analyze scraped trends and produce actionable content plans
with Japanese captions, hashtags, and image generation prompts.
Output: .tmp/content_plan.json

Usage:
    python tools/plan_content.py                         # plan next 1 post
    python tools/plan_content.py --count 7               # plan next 7 days
    python tools/plan_content.py --format carousel        # force format
    python tools/plan_content.py --topic "夜泣き"         # force topic
"""

import os
import json
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

import anthropic

TRENDS_PATH = Path(__file__).parent.parent / ".tmp" / "jp_trends_raw.json"
PLAN_PATH = Path(__file__).parent.parent / ".tmp" / "content_plan.json"
POSTING_LOG_PATH = Path(__file__).parent.parent / ".tmp" / "posting_log.json"
MODEL = "claude-sonnet-4-20250514"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Prompt Construction ──────────────────────────────────────────────────────

SYSTEM_PROMPT = """あなたは日本の育児用品ブランドのSNSマーケティング戦略家です。
日本のSNSトレンドを分析し、Instagram向けのコンテンツ企画を作成してください。

ブランドガイドライン:
- トーン: 温かく共感できる、少しユーモアのある（日本のママインフルエンサースタイル）
- 言語: 自然な日本語、絵文字を適切に活用
- 禁止: 医療的な主張、論争になる育児アドバイス、競合他社の批判
- 推奨フォーマット: カルーセル投稿（保存率が高い）、情報系インフォグラフィック、共感系ミーム

Instagram投稿の最適時間帯（日本時間JST）:
- 平日: 20:00〜22:00（子供を寝かしつけた後）
- 週末: 9:00〜11:00（午前中のゆっくり時間）"""


def build_planning_prompt(
    trends_data: dict,
    count: int,
    forced_format: str | None,
    forced_topic: str | None,
    posting_history: list[dict],
) -> str:
    """Build the prompt for Claude to generate content plans."""

    # Summarize trends for context
    items = trends_data.get("items", [])
    trends_summary = ""
    for i, item in enumerate(items[:50]):  # limit to top 50 for context
        trends_summary += (
            f"{i+1}. [{item.get('source', '?')}] "
            f"{item.get('content_snippet', '')[:200]}\n"
            f"   ハッシュタグ: {', '.join(item.get('hashtags', []))}\n"
            f"   エンゲージメント: {item.get('engagement_signals', 'N/A')}\n\n"
        )

    # Recent posting history to avoid duplicates
    history_text = ""
    if posting_history:
        history_text = "\n最近の投稿履歴（重複を避けること）:\n"
        for post in posting_history[-10:]:
            history_text += f"- {post.get('scheduled_date', '?')}: {post.get('topic', '?')}\n"

    # Format/topic constraints
    constraints = ""
    if forced_format:
        constraints += f"\nフォーマット指定: {forced_format}\n"
    if forced_topic:
        constraints += f"\nトピック指定: {forced_topic}\n"

    # Calculate dates
    start_date = datetime.now()
    dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(count)]
    weekdays = [(start_date + timedelta(days=i)).weekday() for i in range(count)]

    prompt = f"""以下の日本育児トレンドデータを分析し、{count}個のInstagram投稿企画を作成してください。

## トレンドデータ
{trends_summary}
{history_text}
{constraints}

## 投稿日程
{chr(10).join(f"- {d} ({'週末' if wd >= 5 else '平日'})" for d, wd in zip(dates, weekdays))}

## 出力形式（JSON）
以下のJSON形式で出力してください。JSONのみを出力し、他のテキストは含めないでください。

```json
{{
  "posts": [
    {{
      "post_id": "YYYYMMDD_001",
      "scheduled_date": "YYYY-MM-DD",
      "scheduled_time": "20:00",
      "timezone": "Asia/Tokyo",
      "topic": "トピック（日本語）",
      "content_format": "carousel|single_image|reel",
      "slide_count": 5,
      "caption_ja": "完全な日本語キャプション（絵文字、CTA含む）\\n\\n#ハッシュタグ1 #ハッシュタグ2...",
      "hashtags": ["#育児", "#ママ"],
      "image_prompts": [
        {{
          "slide": 1,
          "prompt_en": "English prompt for AI image generation (descriptive, style-specific)",
          "aspect_ratio": "4:5",
          "style_notes": "Warm pastel illustration / clean infographic / etc."
        }}
      ],
      "text_overlays": [
        {{
          "slide": 1,
          "text_ja": "スライド上のテキスト",
          "position": "center|top|bottom",
          "font_size": "large|medium|small"
        }}
      ],
      "marketing_angle": "empathy|information|humor|comparison",
      "status": "planned"
    }}
  ]
}}
```

注意事項:
- image_promptsのprompt_enは英語で、AIイメージ生成に最適化した詳細な説明にすること
- カルーセルの場合、1枚目はアイキャッチ（タイトルスライド）、最後はCTAスライド
- ハッシュタグは日本で人気のある育児関連ハッシュタグを15-25個含める
- キャプションは300-500文字、自然な日本語で
- aspect_ratioは原則 "4:5"（Instagram推奨）"""

    return prompt


# ── Claude API ───────────────────────────────────────────────────────────────

def plan_with_claude(client: anthropic.Anthropic, prompt: str, retries: int = 3) -> dict:
    """Call Claude API and parse JSON response."""
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text

            # Extract JSON from response (handle markdown code blocks)
            json_match = None
            if "```json" in text:
                json_match = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                json_match = text.split("```")[1].split("```")[0].strip()
            else:
                json_match = text.strip()

            result = json.loads(json_match)
            logger.info(f"Claude returned {len(result.get('posts', []))} post plans")
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                logger.info("Retrying with explicit JSON formatting request...")
                prompt += "\n\n重要: 有効なJSONのみを出力してください。マークダウンコードブロックで囲んでください。"
        except Exception as e:
            logger.error(f"Claude API error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                import time
                time.sleep(2 * (attempt + 1))

    raise RuntimeError("Failed to get valid response from Claude after all retries")


# ── Data Loading ─────────────────────────────────────────────────────────────

def load_trends(path: Path) -> dict:
    """Load scraped trends data."""
    if not path.exists():
        raise FileNotFoundError(
            f"Trends file not found: {path}\n"
            f"Run scrape_jp_trends.py first."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Loaded {data.get('total_items', 0)} trend items from {path}")
    return data


def load_posting_history(path: Path) -> list[dict]:
    """Load previous posting log for dedup."""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("posts", [])
    except (json.JSONDecodeError, KeyError):
        return []


def load_existing_plans(path: Path) -> list[dict]:
    """Load existing content plans to avoid duplicates."""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("posts", [])
    except (json.JSONDecodeError, KeyError):
        return []


def save_plan(plan: dict, output_path: Path) -> None:
    """Save content plan to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge with existing plans (keep old ones, add new ones)
    existing = load_existing_plans(output_path)
    existing_ids = {p.get("post_id") for p in existing}
    new_posts = [p for p in plan.get("posts", []) if p.get("post_id") not in existing_ids]

    merged = {
        "planned_at": datetime.now().isoformat(),
        "total_posts": len(existing) + len(new_posts),
        "posts": existing + new_posts,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(new_posts)} new plans (total: {merged['total_posts']}) -> {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Plan Instagram content from JP parenting trends")
    parser.add_argument("--count", type=int, default=1,
                        help="Number of posts to plan (default 1)")
    parser.add_argument("--format", type=str, choices=["carousel", "single_image", "reel"],
                        help="Force a specific content format")
    parser.add_argument("--topic", type=str,
                        help="Force a specific topic (Japanese)")
    parser.add_argument("--trends-file", type=str, default=str(TRENDS_PATH),
                        help="Path to trends JSON file")
    parser.add_argument("--output", type=str, default=str(PLAN_PATH))
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not found. Check .env file.")

    client = anthropic.Anthropic(api_key=api_key)

    # Load data
    trends_data = load_trends(Path(args.trends_file))
    posting_history = load_posting_history(POSTING_LOG_PATH)
    existing_plans = load_existing_plans(Path(args.output))

    # Build prompt
    prompt = build_planning_prompt(
        trends_data=trends_data,
        count=args.count,
        forced_format=args.format,
        forced_topic=args.topic,
        posting_history=existing_plans + posting_history,
    )

    # Generate plan
    logger.info(f"Requesting {args.count} content plan(s) from Claude...")
    plan = plan_with_claude(client, prompt)

    # Save
    save_plan(plan, Path(args.output))

    # Print summary
    print(f"\n{'='*60}")
    print(f"Content Plan Summary")
    print(f"{'='*60}")
    for post in plan.get("posts", []):
        print(f"\n  Post: {post.get('post_id', '?')}")
        print(f"  Date: {post.get('scheduled_date', '?')} {post.get('scheduled_time', '?')} JST")
        print(f"  Topic: {post.get('topic', '?')}")
        print(f"  Format: {post.get('content_format', '?')} ({post.get('slide_count', 1)} slides)")
        print(f"  Angle: {post.get('marketing_angle', '?')}")
        caption_preview = post.get("caption_ja", "")[:100]
        print(f"  Caption: {caption_preview}...")
    print(f"\n{'='*60}")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
