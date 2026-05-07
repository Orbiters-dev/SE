"""
WAT Tool: Generate daily Twitter content plan and post as Teams dashboard.

Generates all slot tweets + Korean translations at once,
posts a comprehensive Adaptive Card to Teams for team review.

Usage:
    python tools/teams_dashboard.py                    # generate & send today's dashboard
    python tools/teams_dashboard.py --dry-run          # generate without posting to Teams
    python tools/teams_dashboard.py --from-file        # send from saved plan (no re-generation)
    python tools/teams_dashboard.py --slot 15          # regenerate specific slot only
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

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

import requests
import anthropic
from twitter_agent import NAKANOHITO_SYSTEM_PROMPT, SLOT_CONFIG, SEASON_MAP
from twitter_utils import (
    validate_tweet_text,
    count_weighted_chars,
    validate_body_length,
    count_body_chars,
)
from teams_notify import WEBHOOK_URL

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
def _plan_path(date_str: str = None) -> Path:
    """Get date-specific plan file path. Prevents overwrite across dates."""
    if not date_str:
        jst = timezone(timedelta(hours=9))
        date_str = datetime.now(jst).strftime("%Y-%m-%d")
    return TMP_DIR / f"daily_tweet_plan_{date_str}.json"

CLAUDE_MODEL = "claude-sonnet-4-20250514"

SLOTS = [10, 13, 17, 19, 21]

SLOT_NAMES_KO = {
    10: "아침 (공감/일상)",
    13: "점심 (팁/질문/K-육아쿼터)",
    17: "저녁 (일상/계절)",
    19: "프라임타임 (공감/제품)",
    21: "밤 (마무리/응원)",
}

SLOT_THEMES_JP = {
    10: "朝の育児あるある",
    13: "Tips・質問・K-育児クォータ",
    17: "日常エピソード",
    19: "共感・製品裏話",
    21: "おやすみ・応援",
}


def get_jst_now() -> datetime:
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst)


def _load_topic_history() -> str:
    """Load past tweet topics to avoid duplication."""
    history_file = TMP_DIR / "tweet_topic_history.json"
    if not history_file.exists():
        return ""
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
        if not history:
            return ""
        # Last 30 entries max
        recent = history[-30:]
        lines = [f"- {h['date']} {h['slot']}:00: [{h.get('topic_id', '?')}] {h['topic_summary']}" for h in recent]
        return "\n".join(lines)
    except Exception:
        return ""


def _load_topic_history_structured() -> dict:
    """Load topic history as structured data for dedup enforcement."""
    history_file = TMP_DIR / "tweet_topic_history.json"
    if not history_file.exists():
        return {"this_week": [], "prev_week": [], "all_topic_ids": []}
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
        if not history:
            return {"this_week": [], "prev_week": [], "all_topic_ids": []}

        from datetime import datetime, timedelta
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        prev_week_start = week_start - timedelta(days=7)

        this_week = []
        prev_week = []
        all_ids = []
        for h in history:
            try:
                d = datetime.strptime(h["date"], "%Y-%m-%d").date()
            except Exception:
                continue
            tid = h.get("topic_id", "")
            if tid:
                all_ids.append(tid)
            if d >= week_start:
                this_week.append(tid)
            elif d >= prev_week_start:
                prev_week.append(tid)

        return {
            "this_week": list(set(this_week)),
            "prev_week": list(set(prev_week)),
            "all_topic_ids": list(set(all_ids)),
            "this_week_babyfood_count": sum(1 for t in this_week if "babyfood" in t or "rinyuushoku" in t),
            "this_week_kparenting_count": sum(
                1 for t in this_week
                if "kparenting" in t or "korean" in t or "k_" in t
            ),
        }
    except Exception:
        return {"this_week": [], "prev_week": [], "all_topic_ids": [], "this_week_kparenting_count": 0}


def _append_topic_history(date: str, slot: str, tweet_jp: str, topic_id: str = ""):
    """Append a new tweet to topic history with topic_id."""
    history_file = TMP_DIR / "tweet_topic_history.json"
    history = []
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
    summary = tweet_jp.split("\n")[0][:80]
    history.append({
        "date": date,
        "slot": slot,
        "topic_id": topic_id,
        "topic_summary": summary,
        "tweet_jp": tweet_jp[:150],
    })
    # Keep last 100
    history = history[-100:]
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def generate_slot_content(slot: int, intel_text: str = "") -> dict:
    """Generate tweet + Korean translation for a single slot.

    Args:
        slot: time slot (e.g. 10, 19)
        intel_text: optional squad intelligence text to inject into prompt
    """
    config = SLOT_CONFIG.get(slot)
    if not config or "post_prompt" not in config:
        return {"slot": slot, "tweet_jp": "", "tweet_ko": "", "error": "no config"}

    month = get_jst_now().month
    season_kw = SEASON_MAP.get(month, "")
    prompt = config["post_prompt"].replace("{season_keywords}", season_kw)

    # ── Topic diversity enforcement ──
    past_topics = _load_topic_history()
    structured = _load_topic_history_structured()
    forbidden_this_week = ", ".join(structured.get("this_week", [])) or "none"
    forbidden_prev_week = ", ".join(structured.get("prev_week", [])) or "none"
    babyfood_count = structured.get("this_week_babyfood_count", 0)
    kparenting_count = structured.get("this_week_kparenting_count", 0)
    kparenting_quota_left = max(0, 2 - kparenting_count)
    kparenting_block = (
        f"\n\n【K-育児クォータ状況】\n"
        f"今週すでに使用したK-育児ネタ: {kparenting_count}/2回\n"
        f"残り使用可: {kparenting_quota_left}回\n"
        f"※ K-育児ネタはslot 13(점심)でのみ可。他スロット(10/17/19/21)では絶対禁止。\n"
        f"※ クォータ0回ならこのスロットでもK-育児禁止。A/B(一般Tips/質問)を書くこと。\n"
    )

    diversity_prompt = f"""

【絶対ルール: トピック多様性】
1. 毎日完全に異なるトピックにしてください。同じトピックの別エピソードはNGです。
   例: NG = 月曜「着替え拒否」→ 火曜「着替えで脱走」(同じトピック)
   例: OK = 月曜「着替え拒否」→ 火曜「幼児食の好き嫌い」→ 水曜「公園でのハプニング」

2. 毎日1ツイートは必ず「食べ物系」トピックにしてください（必須）。
   食べ物系の例: お弁当（保育園弁当・遠足弁当）、おやつ、デザート、幼児食、
   食べこぼし、好き嫌い、作り置き、冷凍ストック等。
   ※K-幼児食レシピは別カテゴリ（K-育児クォータ・週2回まで・slot 13限定）。ここの「食べ物系」は普通の日本の家庭の食事ネタを指します。
   外出先の食事でなくても OK（家ごはん・保育園弁当も立派なネタ）。
   今週の食べ物系トピック数: {babyfood_count}

3. 季節感は週1〜2回だけ。残りは普通の育児日常でOK。
   季節モチーフは「イベント（お花見、海旅行）」ではなく「身近な物・感覚（花びら、蝉の声、落ち葉）」で表現すること。
   毎日季節ネタだと不自然なので、大半は季節に関係ない日常トピックにしてください。

4. 以下のトピックは今週すでに使用済みなので絶対に避けてください:
   今週使用済み: [{forbidden_this_week}]
   先週使用済み: [{forbidden_prev_week}]

5. 出力の最初の行に必ず TOPIC_ID を書いてください。形式:
   TOPIC_ID: (英語の短いID、例: bath_escape, rinyuushoku_rejection, park_adventure, daycare_morning, teething, sleeping_trouble)
   その次の行からツイート本文を書いてください。"""

    if past_topics:
        diversity_prompt += f"\n\n過去のトピック履歴（参考）:\n{past_topics}"

    # Inject K-육 quota awareness ONLY for slot 13 (the K-육 quota slot).
    # Other slots get an explicit "K-育児禁止" reminder via post_prompt itself.
    if slot == 13:
        diversity_prompt += kparenting_block

    prompt += diversity_prompt

    # Inject squad intelligence BEFORE generation — mandatory, not "参考"
    if intel_text:
        intel_injection = (
            f"\n\n{'='*40}\n"
            f"【部隊インテリジェンス — 必須反映】\n"
            f"{intel_text}\n\n"
            f"★ 上記インテリジェンスの活用ルール（厳守）:\n"
            f"1. トレンドハッシュタグが提供されている場合、そこから最低1つをツイートに含めること\n"
            f"2. 競合で反応の良いトピックがあれば、グロミミ視点でそのテーマに触れること\n"
            f"3. 育児ママの最近の話題・悩みがあれば、それに共感する切り口でツイートを作ること\n"
            f"4. ただし宣伝臭は絶対NG。あくまで中の人の自然な投稿として\n"
            f"{'='*40}\n"
        )
        prompt = intel_injection + prompt

    client = anthropic.Anthropic()

    # Generate Japanese tweet
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        system=NAKANOHITO_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_output = response.content[0].text.strip()

    # Extract TOPIC_ID from first line
    topic_id = ""
    tweet_jp = raw_output
    lines = raw_output.split("\n")
    if lines and lines[0].upper().startswith("TOPIC_ID:"):
        topic_id = lines[0].split(":", 1)[1].strip().lower().replace(" ", "_")
        tweet_jp = "\n".join(lines[1:]).strip()

    # Clean up quotes
    if tweet_jp.startswith('"') and tweet_jp.endswith('"'):
        tweet_jp = tweet_jp[1:-1]
    if tweet_jp.startswith("\u300c") and tweet_jp.endswith("\u300d"):
        tweet_jp = tweet_jp[1:-1]

    # Validate weighted length AND body length, retry up to 3 times with progressive feedback.
    MAX_RETRIES = 3
    for attempt in range(1, MAX_RETRIES + 1):
        ok_weighted, msg_weighted = validate_tweet_text(tweet_jp)
        ok_body, msg_body = validate_body_length(tweet_jp)
        body_chars = count_body_chars(tweet_jp)

        if ok_weighted and ok_body:
            break

        if attempt == MAX_RETRIES:
            logger.warning(
                f"Slot {slot} attempt {attempt} still invalid "
                f"(weighted={msg_weighted}, body={msg_body}); shipping anyway"
            )
            break

        # Build progressively stricter feedback for each retry
        feedback_lines = [
            f"\n\n【再生成指示・第{attempt + 1}回試行】前回の出力は以下の理由でルール違反:"
        ]
        if not ok_weighted:
            feedback_lines.append(f"- {msg_weighted}")
        if not ok_body:
            feedback_lines.append(f"- {msg_body} (本文ハッシュタグ抜きで{body_chars}文字)")
        feedback_lines.append(
            "\n【厳守ルール再確認】"
            "\n- 本文（ハッシュタグを除いた部分）は60〜80文字以内（ハッシュタグは別カウント）。"
            "\n- 本文+ハッシュタグ全体で280加重文字以内（日本語1文字=2加重）。"
            "\n- 短く、削れる修飾語は削って書き直してください。"
        )
        retry_prompt = prompt + "\n".join(feedback_lines)

        logger.info(
            f"Slot {slot} attempt {attempt} invalid "
            f"(weighted_ok={ok_weighted}, body_ok={ok_body}, body={body_chars}). Retrying..."
        )
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=NAKANOHITO_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": retry_prompt}],
        )
        raw_output = response.content[0].text.strip()
        if raw_output.split("\n")[0].upper().startswith("TOPIC_ID:"):
            topic_id = raw_output.split("\n")[0].split(":", 1)[1].strip().lower().replace(" ", "_")
            tweet_jp = "\n".join(raw_output.split("\n")[1:]).strip()
        else:
            tweet_jp = raw_output
        if tweet_jp.startswith('"') and tweet_jp.endswith('"'):
            tweet_jp = tweet_jp[1:-1]
        if tweet_jp.startswith("\u300c") and tweet_jp.endswith("\u300d"):
            tweet_jp = tweet_jp[1:-1]

    # Korean translation
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": f"다음 일본어 트윗을 자연스러운 한국어로 번역해주세요. 번역만 출력:\n\n{tweet_jp}",
            }
        ],
    )
    tweet_ko = response.content[0].text.strip()

    wt = count_weighted_chars(tweet_jp)
    ok, _ = validate_tweet_text(tweet_jp)
    body_chars_final = count_body_chars(tweet_jp)
    ok_body_final, _ = validate_body_length(tweet_jp)

    # Save to topic history for dedup (with topic_id)
    _append_topic_history(
        date=get_jst_now().strftime("%Y-%m-%d"),
        slot=str(slot),
        tweet_jp=tweet_jp,
        topic_id=topic_id,
    )

    return {
        "slot": slot,
        "tweet_jp": tweet_jp,
        "tweet_ko": tweet_ko,
        "chars": wt,
        "body_chars": body_chars_final,
        "valid": ok,
        "body_valid": ok_body_final,
        "topic_id": topic_id,
        "theme_jp": SLOT_THEMES_JP.get(slot, ""),
        "theme_ko": SLOT_NAMES_KO.get(slot, ""),
    }


def generate_daily_plan(slots: list[int] = None, target_date: str = None,
                        intel_text: str = "") -> dict:
    """Generate the tweet plan for specific slots and/or date.

    Args:
        slots: which slots to generate (default: all 8)
        target_date: date string "YYYY-MM-DD" (default: today JST)
        intel_text: optional squad intelligence text to inject into prompts
    """
    if slots is None:
        slots = SLOTS

    now = get_jst_now()
    date_str = target_date or now.strftime("%Y-%m-%d")
    plan = {
        "date": date_str,
        "generated_at": now.isoformat(),
        "slots": {},
    }

    # Merge into existing plan if same date (preserves AM when generating PM, etc.)
    plan_file = _plan_path(date_str)
    if plan_file.exists():
        try:
            with open(plan_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("date") == date_str:
                plan["slots"] = existing.get("slots", {})
                logger.info(f"Merging into existing plan for {date_str}")
        except Exception:
            pass

    for slot in slots:
        logger.info(f"Generating slot {slot}:00...")
        content = generate_slot_content(slot, intel_text=intel_text)
        plan["slots"][str(slot)] = content
        logger.info(
            f"  [{slot}:00] {content['tweet_jp'][:40]}... ({content['chars']}/280)"
        )

    # Save to date-specific file
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    logger.info(f"Plan saved to {plan_file}")

    return plan


def load_daily_plan() -> dict:
    """Load previously generated plan from file."""
    plan_file = _plan_path()
    if not plan_file.exists():
        logger.error(f"No plan file at {plan_file}")
        return {}
    with open(plan_file, "r", encoding="utf-8") as f:
        return json.load(f)


def build_dashboard_card(plan: dict) -> dict:
    """Build an Adaptive Card for the daily dashboard."""
    date_str = plan.get("date", "")

    body = [
        {
            "type": "TextBlock",
            "text": f"📋 @grosmimi_japan 오늘의 트윗 플랜",
            "weight": "Bolder",
            "size": "Large",
        },
        {
            "type": "TextBlock",
            "text": f"📅 {date_str} | 생성: {plan.get('generated_at', '')[:16]}",
            "isSubtle": True,
            "spacing": "None",
        },
        {"type": "TextBlock", "text": "━━━━━━━━━━━━━━━━━━━━━━━━", "spacing": "Small"},
    ]

    for slot in SLOTS:
        slot_data = plan.get("slots", {}).get(str(slot), {})
        tweet_jp = slot_data.get("tweet_jp", "(미생성)")
        tweet_ko = slot_data.get("tweet_ko", "")
        chars = slot_data.get("chars", 0)
        valid = slot_data.get("valid", False)
        theme_ko = SLOT_NAMES_KO.get(slot, "")

        status = "✅" if valid else "⚠️"
        if not tweet_jp or tweet_jp == "(미생성)":
            status = "⏳"

        # Slot header
        body.append(
            {
                "type": "TextBlock",
                "text": f"{status} [{slot}:00] {theme_ko}",
                "weight": "Bolder",
                "spacing": "Medium",
                "color": "Good" if valid else "Attention",
            }
        )

        # Japanese tweet
        if tweet_jp and tweet_jp != "(미생성)":
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"🇯🇵 {tweet_jp}",
                    "wrap": True,
                    "spacing": "Small",
                }
            )

            # Korean translation
            if tweet_ko:
                body.append(
                    {
                        "type": "TextBlock",
                        "text": f"🇰🇷 {tweet_ko}",
                        "wrap": True,
                        "spacing": "None",
                        "isSubtle": True,
                    }
                )

            # Char count
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"({chars}/280자)",
                    "isSubtle": True,
                    "spacing": "None",
                    "size": "Small",
                }
            )

        body.append(
            {"type": "TextBlock", "text": "─────────────────────", "spacing": "Small", "isSubtle": True}
        )

    # Footer
    body.append(
        {
            "type": "TextBlock",
            "text": "━━━━━━━━━━━━━━━━━━━━━━━━",
            "spacing": "Medium",
        }
    )
    body.append(
        {
            "type": "TextBlock",
            "text": "⚠️ 수정/취소가 필요하면 Claude에게 직접 전달해주세요.",
            "wrap": True,
            "color": "Attention",
        }
    )
    body.append(
        {
            "type": "TextBlock",
            "text": "각 슬롯 10분 전에 실행 알림이 별도로 갑니다.",
            "isSubtle": True,
            "spacing": "None",
        }
    )

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                },
            }
        ],
    }


def send_dashboard(plan: dict) -> bool:
    """Send the dashboard card to Teams."""
    if not WEBHOOK_URL:
        logger.error("TEAMS_WEBHOOK_URL not set")
        return False

    payload = build_dashboard_card(plan)

    try:
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        if resp.status_code == 202:
            logger.info("Dashboard sent to Teams successfully")
            return True
        else:
            logger.error(f"Teams webhook failed: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Teams webhook error: {e}")
        return False


def print_plan(plan: dict):
    """Print plan to console for review."""
    print(f"\n{'='*60}")
    print(f"  @grosmimi_japan Daily Tweet Plan — {plan.get('date', '')}")
    print(f"{'='*60}\n")

    for slot in SLOTS:
        slot_data = plan.get("slots", {}).get(str(slot), {})
        tweet_jp = slot_data.get("tweet_jp", "(미생성)")
        tweet_ko = slot_data.get("tweet_ko", "")
        chars = slot_data.get("chars", 0)
        valid = slot_data.get("valid", False)
        theme_ko = SLOT_NAMES_KO.get(slot, "")

        status = "OK" if valid else "NG"
        print(f"[{slot}:00] {theme_ko} ({status}, {chars}/280)")
        print(f"  JP: {tweet_jp}")
        if tweet_ko:
            print(f"  KR: {tweet_ko}")
        print()

    print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate daily tweet dashboard")
    parser.add_argument(
        "--dry-run", action="store_true", help="Generate without posting to Teams"
    )
    parser.add_argument(
        "--from-file", action="store_true", help="Send existing plan (no generation)"
    )
    parser.add_argument(
        "--slot", type=int, help="Regenerate specific slot only"
    )
    parser.add_argument(
        "--print", action="store_true", dest="print_only", help="Print plan to console"
    )
    args = parser.parse_args()

    if args.from_file:
        plan = load_daily_plan()
        if not plan:
            sys.exit(1)
    elif args.slot:
        # Regenerate specific slot
        plan = load_daily_plan()
        if not plan:
            plan = {"date": get_jst_now().strftime("%Y-%m-%d"), "slots": {}}
        # Load squad intel for single-slot regeneration
        try:
            from twitter_scheduler import load_twitter_intel
            slot_intel = load_twitter_intel()
        except Exception:
            slot_intel = ""
        content = generate_slot_content(args.slot, intel_text=slot_intel)
        plan["slots"][str(args.slot)] = content
        plan["generated_at"] = get_jst_now().isoformat()
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        with open(_plan_path(), "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
    else:
        plan = generate_daily_plan()

    if args.print_only:
        print_plan(plan)
    elif args.dry_run:
        print_plan(plan)
        logger.info("[DRY RUN] Dashboard not sent to Teams")
    else:
        print_plan(plan)
        send_dashboard(plan)
