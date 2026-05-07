"""
WAT Tool: Twitter auto-scheduler with Excel-based team approval.

Flow:
1. AM/PM split: generate tweets + reply plans → Excel → upload to Teams
2. Team reviews Excel (Confirmed/Declined dropdown):
   - Confirmed            →  post at scheduled time
   - Declined + alt text  →  use alt text instead
   - Declined (no text)   →  skip
   - (empty)              →  NOT confirmed, do NOT post
3. Each slot time: check Excel → post tweet + replies if confirmed

Schedule (JST):
    08:00  Search reply targets (AM slots)
    08:30  AM Excel (9,11,13,15 tweets+replies) → Teams upload
    09:00  Slot 9 (tweet + replies)
    11:00  Slot 11
    13:00  Slot 13
    15:00  Slot 15
    15:30  Search reply targets (PM slots)
    16:00  PM Excel (17,19,21,23 tweets+replies) → Teams upload
           Friday: also generate Sat/Sun tweets (no replies)
    17:00  Slot 17
    19:00  Slot 19
    21:00  Slot 21
    23:00  Slot 23

Usage:
    python tools/twitter_scheduler.py                  # run next upcoming slot
    python tools/twitter_scheduler.py --slot 13        # run specific slot
    python tools/twitter_scheduler.py --daemon         # run all day (background)
    python tools/twitter_scheduler.py --dry-run        # preview without posting
    python tools/twitter_scheduler.py --generate-am    # generate AM plan + upload
    python tools/twitter_scheduler.py --generate-pm    # generate PM plan + upload
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    # pythonw.exe has no stdout/stderr — redirect to devnull
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    else:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOG_FILE = Path(__file__).parent.parent / ".tmp" / "scheduler.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from twitter_utils import (
    create_twitter_clients,
    validate_tweet_text,
    count_weighted_chars,
    validate_body_length,
    count_body_chars,
)
from teams_notify import send_action_plan, send_result
from teams_actions import check_pending_actions, mark_action_handled
from excel_feedback import download_plan_excel, read_feedback

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"
CANCEL_FILE = TMP_DIR / "cancel_next_tweet"
PENDING_FILE = TMP_DIR / "pending_tweet.json"

# ── Config ───────────────────────────────────────────────────────────────
SLOTS = [10, 13, 17, 19, 21]
AM_SLOTS = [10, 13]
PM_SLOTS = [17, 19, 21]
APPROVAL_WAIT_MINUTES = 10
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# ── Import agent prompts ────────────────────────────────────────────────
from twitter_agent import NAKANOHITO_SYSTEM_PROMPT, SLOT_CONFIG, SEASON_MAP


def get_jst_now() -> datetime:
    """Get current time in JST (UTC+9)."""
    from datetime import timezone
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst)


def load_twitter_intel() -> str:
    """Load intelligence from other squad members for plan generation.

    Returns a structured summary string that gets injected into the
    企画マン's Claude prompt. Now provides richer context:
    - Competitor insights: top 5 brands with full 'グロミミへの示唆' section
    - Hashtags: filtered to 育児/ベビー relevant only (skip unrelated trends)
    - Engagement: recent mama topics from commenter interactions
    """
    intel_dir = os.path.join(str(PROJECT_ROOT), ".tmp", "twitter_intel")
    intel_summary = []

    # ── 조사맨: 경쟁사 인텔 (richer extraction) ──
    comp_path = os.path.join(intel_dir, "competitor_report.json")
    if os.path.exists(comp_path):
        try:
            with open(comp_path, "r", encoding="utf-8") as f:
                comp = json.load(f)
            if comp.get("top_topics"):
                # Extract 'グロミミへの示唆' section from each analysis
                insights = []
                for t in comp["top_topics"][:8]:
                    if not isinstance(t, dict):
                        continue
                    brand = t.get("brand", "")
                    analysis = t.get("analysis", "")
                    # Find the actionable insight section
                    hint_text = ""
                    for marker in ["グロミミへの示唆", "参考点", "差別化点"]:
                        idx = analysis.find(marker)
                        if idx >= 0:
                            hint_text = analysis[idx:idx + 250].strip()
                            break
                    if hint_text:
                        insights.append(f"・{brand}: {hint_text}")
                    else:
                        insights.append(f"・{brand}: {analysis[:150]}")
                if insights:
                    intel_summary.append(
                        "【競合ブランドの動向とグロミミへの示唆】\n" + "\n".join(insights)
                    )
            if comp.get("top_formats"):
                fmt_counts = {}
                for t in comp["top_formats"]:
                    fmt = t.get("format", "") if isinstance(t, dict) else str(t)
                    fmt_counts[fmt] = fmt_counts.get(fmt, 0) + 1
                fmt_ranked = sorted(fmt_counts.items(), key=lambda x: -x[1])
                fmt_strs = [f"{fmt}({cnt}社)" for fmt, cnt in fmt_ranked[:5]]
                intel_summary.append(f"【競合で多いフォーマット】{', '.join(fmt_strs)}")
        except Exception as e:
            logger.warning(f"Failed to load competitor intel: {e}")

    # ── 해시태그맨: 육아/베이비 관련만 필터링 ──
    hash_path = os.path.join(intel_dir, "hashtag_trends.json")
    if os.path.exists(hash_path):
        try:
            with open(hash_path, "r", encoding="utf-8") as f:
                ht = json.load(f)
            # Filter hashtags to 育児/ベビー related
            # Only pass hashtags in our brand territory
            parenting_keywords = [
                "育児あるある", "育児疲れ", "育児グッズ", "育児垢",
                "子育て", "ママさん", "ママ友", "ワンオペ",
                "幼児食", "離乳", "お弁当", "イヤイヤ期",
                "寝かしつけ", "ストローマグ", "ベビーマグ", "ベビー用品",
                "赤ちゃん", "保育園", "入園", "キッズ",
                "K育児", "K幼児食",
            ]
            # No blocking — all parenting tags including manga/illustration
            all_tags = ht.get("trending_hashtags", [])
            relevant_tags = [
                tag for tag in all_tags
                if any(kw in tag for kw in parenting_keywords)
            ]
            other_tags = [tag for tag in all_tags if tag not in relevant_tags]

            if relevant_tags:
                intel_summary.append(
                    f"【今週の育児系トレンドハッシュタグ（50個プールからランダムに5〜10個選んで使用）】\n"
                    f"{', '.join(relevant_tags)}"
                )
            if other_tags:
                intel_summary.append(
                    f"【一般トレンド（参考）】{', '.join(other_tags[:10])}"
                )

            # Suggested keywords
            suggested = ht.get("suggested_keywords", [])
            if suggested:
                intel_summary.append(
                    f"【提案キーワード】{', '.join(suggested[:15])}"
                )

            # Trend analysis + brand fit from ハッシュタグ調査マン
            analysis = ht.get("trend_analysis", "")
            if analysis:
                header = (
                    "【ハッシュタグ調査マンのトレンド分析・ブランドFit判断】" + chr(10)
                    + "以下は今週の育児トレンドとグロミミとの相性分析です。" + chr(10)
                    + "これを参考にツイートの話題・切り口を決めてください。" + chr(10) + chr(10)
                )
                intel_summary.append(header + analysis)
        except Exception as e:
            logger.warning(f"Failed to load hashtag intel: {e}")

    # ── 코멘터: 현장 인사이트 ──
    engage_path = os.path.join(intel_dir, "engagement_insights.json")
    if os.path.exists(engage_path):
        try:
            with open(engage_path, "r", encoding="utf-8") as f:
                eng = json.load(f)
                topics = eng.get("recent_topics", [])[:10]
                if topics:
                    topic_texts = [t.get("target_text", "")[:120] for t in topics if t.get("target_text")]
                    if topic_texts:
                        intel_summary.append(
                            "【育児ママの最近の話題・悩み】\n"
                            + "\n".join(f"・{t}" for t in topic_texts[:7])
                        )
        except Exception as e:
            logger.warning(f"Failed to load engagement intel: {e}")

    return "\n\n".join(intel_summary) if intel_summary else ""


def _plan_path(date_str: str = None) -> Path:
    """Get date-specific plan file path. Downloads from SharePoint if not local."""
    if not date_str:
        date_str = get_jst_now().strftime("%Y-%m-%d")
    local = TMP_DIR / f"daily_tweet_plan_{date_str}.json"
    if not local.exists():
        try:
            from teams_upload import download_plan_json
            download_plan_json(date_str, str(local))
        except Exception as e:
            logger.warning(f"SharePoint plan download failed: {e}")
    return local


def generate_tweet(slot: int) -> tuple[str, str]:
    """Generate tweet text and Korean translation using Claude API.

    Returns:
        tuple: (japanese_tweet, korean_translation)
    """
    import anthropic

    config = SLOT_CONFIG.get(slot)
    if not config or "post_prompt" not in config:
        logger.warning(f"Slot {slot} has no post_prompt, skipping generation")
        return "", ""

    month = get_jst_now().month
    season_kw = SEASON_MAP.get(month, "")
    prompt = config["post_prompt"].replace("{season_keywords}", season_kw)

    # Inject squad intelligence into prompt
    intel = load_twitter_intel()
    if intel:
        intel_section = (
            f"\n\n--- 部隊インテリジェンス（他メンバーの調査結果）---\n{intel}\n"
            f"上記のトレンドやトピックを参考にしつつ、グロミミらしい切り口でツイートを企画してください。\n---\n"
        )
        prompt += intel_section

    client = anthropic.Anthropic()

    # Generate Japanese tweet
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        system=NAKANOHITO_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    tweet_jp = response.content[0].text.strip()

    # Clean up: remove quotes if wrapped
    if tweet_jp.startswith('"') and tweet_jp.endswith('"'):
        tweet_jp = tweet_jp[1:-1]
    if tweet_jp.startswith("「") and tweet_jp.endswith("」"):
        tweet_jp = tweet_jp[1:-1]

    # Validate weighted length AND body length, retry up to 3 times.
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

        feedback = [f"\n\n【再生成・第{attempt + 1}回試行】前回出力ルール違反:"]
        if not ok_weighted:
            feedback.append(f"- {msg_weighted}")
        if not ok_body:
            feedback.append(f"- {msg_body} (本文ハッシュタグ抜きで{body_chars}文字)")
        feedback.append(
            "\n【厳守】本文（ハッシュタグ除く）60〜80文字以内、"
            "本文+ハッシュタグ全体で280加重以内。短く書き直してください。"
        )
        retry_prompt = prompt + "\n".join(feedback)
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
        tweet_jp = response.content[0].text.strip()
        if tweet_jp.startswith('"') and tweet_jp.endswith('"'):
            tweet_jp = tweet_jp[1:-1]
        if tweet_jp.startswith("\u300c") and tweet_jp.endswith("\u300d"):
            tweet_jp = tweet_jp[1:-1]

    # Generate Korean translation
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

    return tweet_jp, tweet_ko


def _check_excel_for_slot(slot: int) -> dict:
    """Download Excel from Teams and check approval column for this slot.

    Returns:
        {"action": "approve"|"replace"|"cancel"|"pending", "alt_text": "..."}
    """
    try:
        excel_path = download_plan_excel()
        if not excel_path:
            return {"action": "pending", "alt_text": ""}

        feedbacks = read_feedback(excel_path)
        logger.info(f"Excel feedbacks found: {[(fb['slot'], fb['action'], fb['sheet']) for fb in feedbacks]}")
        for fb in feedbacks:
            if fb["slot"] == slot and fb["sheet"] == "내 트윗":
                logger.info(f"Slot {slot} approval: {fb['action']}")
                return {
                    "action": fb["action"],
                    "alt_text": fb.get("alt_text", ""),
                }

        logger.info(f"No approval row found for slot {slot} in Excel")
        return {"action": "pending", "alt_text": ""}
    except Exception as e:
        logger.warning(f"Excel check failed: {e}", exc_info=True)
        return {"action": "pending", "alt_text": ""}


def _check_excel_for_replies(slot: int) -> list[dict]:
    """Download Excel and check reply approvals for this slot.

    Returns:
        list of {"action": "approve"|"replace"|"cancel"|"pending",
                 "alt_text": "...", "reply_index": int, "target_username": "..."}
    """
    try:
        excel_path = download_plan_excel()
        if not excel_path:
            return []

        feedbacks = read_feedback(excel_path)
        return [
            fb for fb in feedbacks
            if fb["slot"] == slot and fb["sheet"] == "리플 계획"
        ]
    except Exception as e:
        logger.warning(f"Excel reply check failed: {e}")
        return []


def _regenerate_with_feedback(slot: int, instruction: str) -> tuple[str, str]:
    """Regenerate a slot's tweet with team's modification instruction.

    Returns:
        tuple: (new_japanese_tweet, new_korean_translation)
    """
    import anthropic

    config = SLOT_CONFIG.get(slot)
    if not config or "post_prompt" not in config:
        return "", ""

    month = get_jst_now().month
    season_kw = SEASON_MAP.get(month, "")
    base_prompt = config["post_prompt"].replace("{season_keywords}", season_kw)

    prompt = f"""{base_prompt}

追加指示（チームからのフィードバック）:
{instruction}

このフィードバックを反映して、ツイートを作成してください。"""

    client = anthropic.Anthropic()

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        system=NAKANOHITO_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    tweet_jp = response.content[0].text.strip()
    if tweet_jp.startswith('"') and tweet_jp.endswith('"'):
        tweet_jp = tweet_jp[1:-1]
    if tweet_jp.startswith("「") and tweet_jp.endswith("」"):
        tweet_jp = tweet_jp[1:-1]

    # Korean translation
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": f"다음 일본어 트윗을 자연스러운 한국어로 번역해주세요. 번역만 출력:\n\n{tweet_jp}",
        }],
    )
    tweet_ko = response.content[0].text.strip()

    logger.info(f"Regenerated tweet ({count_weighted_chars(tweet_jp)}/280): {tweet_jp[:60]}...")
    return tweet_jp, tweet_ko


def _notify_skip(slot: int, reason: str, tweet_jp: str = ""):
    """Send a Teams notification when a tweet slot is skipped."""
    try:
        import requests as _req
        _webhook = os.getenv("TEAMS_WEBHOOK_URL") or os.getenv("TEAMS_MASTER_WEBHOOK_URL")
        if not _webhook:
            return
        _label = "朝の投稿" if slot == 10 else "夜の投稿"
        _preview = f"\n> {tweet_jp[:80]}{'...' if len(tweet_jp) > 80 else ''}" if tweet_jp else ""
        _msg = (
            f"⚠️ **監督報告** — {slot}:00 {_label} スキップ\n\n"
            f"**理由**: {reason}{_preview}\n\n"
            f"Excelの{slot}:00行でConfirmedを選択してください。"
        )
        _req.post(_webhook, json={"text": _msg}, timeout=10)
        logger.info(f"Skip notification sent for slot {slot}")
    except Exception as _e:
        logger.warning(f"Skip notify failed: {_e}")


def run_slot(slot: int, dry_run: bool = False) -> dict:
    """Execute a slot: check Excel → post tweet + replies if confirmed.

    Approval logic (Confirmed/Declined dropdown):
    - Confirmed           → post as-is
    - Declined + alt text → use alt text
    - Declined (no text)  → skip
    - (empty)             → wait up to APPROVAL_WAIT_MINUTES, then skip
    """

    logger.info(f"=== Slot {slot}:00 START ===")
    config = SLOT_CONFIG.get(slot)
    if not config:
        logger.error(f"No config for slot {slot}")
        return {"status": "error", "reason": "no config"}

    result = {"slot": slot, "actions": []}

    # ── Step 1: Load tweet + replies from daily plan ──────────────────────
    tweet_jp, tweet_ko = "", ""
    replies = []
    plan_file = _plan_path()  # date-specific: daily_tweet_plan_YYYY-MM-DD.json

    if plan_file.exists():
        with open(plan_file, "r", encoding="utf-8") as f:
            plan = json.load(f)
        slot_data = plan.get("slots", {}).get(str(slot), {})
        tweet_jp = slot_data.get("tweet_jp", "")
        tweet_ko = slot_data.get("tweet_ko", "")
        replies = slot_data.get("replies", [])

    # If no pre-generated tweet, generate now
    if not tweet_jp and "post_prompt" in config:
        logger.info("No pre-generated tweet. Generating via Claude API...")
        tweet_jp, tweet_ko = generate_tweet(slot)

    if tweet_jp:
        ok, msg = validate_tweet_text(tweet_jp)
        wt = count_weighted_chars(tweet_jp)
        logger.info(f"Tweet ({wt}/280): {tweet_jp[:60]}...")
        if not ok:
            logger.error(f"Tweet validation failed: {msg}")
            return {"status": "error", "reason": msg}

    if dry_run:
        logger.info(f"[DRY RUN] Tweet: {tweet_jp[:80]}...")
        for i, r in enumerate(replies):
            logger.info(f"[DRY RUN] Reply #{i} to @{r.get('target_username','?')}: {r.get('reply_jp','')[:60]}...")
        return {"status": "dry_run", "tweet": tweet_jp, "replies": len(replies)}

    # ── Step 2: Check Excel approval (once) ───────────────────────────────────
    logger.info(f"Checking Excel approval for slot {slot}...")
    confirmed = False
    skip_reason = ""
    try:
        excel_result = _check_excel_for_slot(slot)
        action = excel_result["action"]
        alt_text = excel_result.get("alt_text", "")

        if action == "approve":
            logger.info("Tweet CONFIRMED — posting")
            confirmed = True
        elif action == "replace":
            logger.info(f"Using alt text: {alt_text[:60]}...")
            tweet_jp = alt_text
            tweet_ko = ""
            confirmed = True
        elif action == "cancel":
            logger.info("Tweet DECLINED — skipping")
            _notify_skip(slot, "❌ Declined（却下）", tweet_jp)
            return {"status": "cancelled", "reason": "declined"}
        else:
            logger.info("No approval found — skipping")
            skip_reason = "Excelの承認列が空欄（Confirmedが見つかりません）"
    except Exception as e:
        logger.warning(f"Excel check failed: {e} — skipping")
        skip_reason = f"Excelの読み込みエラー: {e}"

    # ── Step 2b: Fallback — check plan JSON's approved flag ───────────────────
    if not confirmed and plan_file.exists():
        try:
            with open(plan_file, "r", encoding="utf-8") as f:
                _plan = json.load(f)
            _slot_data = _plan.get("slots", {}).get(str(slot), {})
            if _slot_data.get("approved"):
                logger.info(f"Slot {slot}: approved flag found in plan JSON — posting")
                confirmed = True
                # Use alt text from plan JSON if replaced
                if _slot_data.get("replaced") and _slot_data.get("tweet_jp"):
                    tweet_jp = _slot_data["tweet_jp"]
        except Exception as _e:
            logger.warning(f"Plan JSON fallback check failed: {_e}")

    if not confirmed:
        _notify_skip(slot, skip_reason or "承認なし", tweet_jp)
        return {"status": "skipped", "reason": "no confirmation"}

    # ── Step 3: Post tweet ─────────────────────────────────────────────────
    tweet_url = ""
    if tweet_jp:
        logger.info("Posting tweet...")
        try:
            client, api = create_twitter_clients()
        except EnvironmentError as e:
            logger.error(f"Twitter credentials missing: {e}")
            _notify_skip(slot, f"Twitter認証情報が不足: {e}", tweet_jp)
            raise

        ok, msg = validate_tweet_text(tweet_jp)
        if ok:
            try:
                response = client.create_tweet(text=tweet_jp)
                tweet_id = response.data["id"]
                tweet_url = f"https://x.com/grosmimi_jp/status/{tweet_id}"
                logger.info(f"Posted: {tweet_url}")
                result["actions"].append({"type": "tweet", "url": tweet_url})
            except Exception as e:
                logger.error(f"Tweet posting failed: {type(e).__name__}: {e}")
                _notify_skip(slot, f"ツイート投稿エラー: {type(e).__name__}: {str(e)[:100]}", tweet_jp)
                raise
        else:
            logger.error(f"Tweet blocked at post time: {msg}")

    # ── Step 4: Execute confirmed replies ──────────────────────────────────
    if replies:
        logger.info(f"Checking {len(replies)} reply approvals...")
        reply_feedbacks = _check_excel_for_replies(slot)

        # Build lookup: reply_index → feedback
        fb_map = {fb["reply_index"]: fb for fb in reply_feedbacks}

        from twitter_engage import post_reply

        for idx, reply_plan in enumerate(replies):
            fb = fb_map.get(idx)
            target_user = reply_plan.get("target_username", "?")
            target_tweet_id = reply_plan.get("target_tweet_id", "")

            if not fb:
                logger.info(f"  Reply #{idx} @{target_user}: no approval — skipping")
                continue

            if fb["action"] == "cancel":
                logger.info(f"  Reply #{idx} @{target_user}: DECLINED — skipping")
                continue

            # Use alt_text if replaced
            reply_text = fb["alt_text"] if fb["action"] == "replace" else reply_plan.get("reply_jp", "")

            if not reply_text or not target_tweet_id:
                logger.warning(f"  Reply #{idx} @{target_user}: missing text or tweet_id")
                continue

            logger.info(f"  Posting reply #{idx} to @{target_user}: {reply_text[:50]}...")
            reply_url = post_reply(
                tweet_id=target_tweet_id,
                reply_text=reply_text,
                username=target_user,
            )
            if reply_url:
                result["actions"].append({
                    "type": "reply",
                    "target": f"@{target_user}",
                    "url": reply_url,
                })

    # ── Step 5: Send result to Teams ───────────────────────────────────────
    send_result(slot=slot, tweet_url=tweet_url,
                tweet_text=tweet_jp, tweet_ko=tweet_ko)

    # 監督: 日本語で投稿完了を報告
    try:
        import requests as _req
        _webhook = os.getenv("TEAMS_WEBHOOK_URL") or os.getenv("TEAMS_MASTER_WEBHOOK_URL")
        if _webhook and tweet_url:
            _label = "朝の投稿" if slot == 10 else "夜の投稿"
            _now = get_jst_now().strftime("%H:%M")
            _msg = (
                f"📢 **監督報告** {_now} JST\n\n"
                f"✅ **{slot}:00 {_label}** 投稿完了\n"
                f"> {tweet_jp[:100]}{'...' if len(tweet_jp) > 100 else ''}\n\n"
                f"[投稿を確認]({tweet_url})"
            )
            _req.post(_webhook, json={"text": _msg}, timeout=10)
            logger.info(f"Supervisor notified: slot {slot} posted")
    except Exception as _e:
        logger.warning(f"Supervisor notify failed: {_e}")

    result["status"] = "completed"
    logger.info(f"=== Slot {slot}:00 DONE ({len(result['actions'])} actions) ===")

    # Notify master status
    try:
        from master_status import log_action, update_domain
        log_action("twitter", "slot_completed", {
            "slot": slot,
            "tweet_url": tweet_url,
            "actions": len(result.get("actions", [])),
        }, source="twitter_scheduler")
        update_domain("twitter", {
            "last_tweet_slot": slot,
            "last_tweet_at": get_jst_now().isoformat(),
        })
    except Exception:
        pass

    return result


def generate_and_upload(slots: list[int] = None, label: str = "",
                        include_replies: bool = True,
                        target_date: str = None) -> dict:
    """Generate tweet plan + reply plan → Excel → upload to Teams.

    Args:
        slots: which slots to generate (default: all 8)
        label: filename label ("AM", "PM", "weekend_sat", etc.)
        include_replies: False for weekend mode (tweets only)
        target_date: date string for the plan (default: today)
    """
    from teams_dashboard import generate_daily_plan
    from plan_replies import plan_daily_replies, merge_replies_into_plan
    from generate_daily_excel import create_daily_excel
    from teams_upload import upload_file

    period = label or "ALL"
    logger.info(f"=== GENERATE {period} PLAN ===")

    # Load squad intelligence for prompt injection
    intel = load_twitter_intel()
    if intel:
        logger.info(f"Squad intelligence loaded ({len(intel)} chars)")

    # Step 1: Generate tweets via Claude API (with squad intel)
    plan = generate_daily_plan(slots=slots, target_date=target_date,
                               intel_text=intel)
    if not plan or not plan.get("slots"):
        logger.error("Plan generation failed")
        return None

    logger.info(f"Generated {len(plan['slots'])} slots")

    # Step 2: Search reply targets + generate drafts
    if include_replies and slots:
        logger.info("Searching reply targets...")
        reply_plans = plan_daily_replies(slots)
        plan = merge_replies_into_plan(reply_plans)
        total_replies = sum(len(r) for r in reply_plans.values())
        logger.info(f"Planned {total_replies} replies")

    # Step 3: Create Excel
    excel_path = create_daily_excel(
        plan,
        slots=slots,
        include_replies=include_replies,
        label=label,
    )
    logger.info(f"Excel: {excel_path}")

    # Step 4: Upload to Teams
    try:
        msg = f"{period} 트윗 플랜입니다. Confirmed/Declined로 승인해주세요."
        result = upload_file(excel_path, notify=True, message=msg)
        logger.info(f"Uploaded to Teams: {result.get('web_url', '')}")
    except Exception as e:
        logger.warning(f"Teams upload failed: {e}")

    return plan


def _is_male_account(tweet: dict) -> bool:
    """Return True if the tweet appears to be from a male (skip these)."""
    text = " ".join([
        tweet.get("username", ""),
        tweet.get("title", ""),
        tweet.get("description", ""),
    ])
    male_keywords = [
        "パパです", "パパやってます", "パパをやってます", "児のパパ", "人のパパ",
        "お父さん", "父親", "父です", "父ちゃん", "パパ目線", "父目線",
        "夫目線", "育メン", "イクメン",
        "僕は", "俺は", "ぼくは",
    ]
    return any(kw in text for kw in male_keywords)


def _is_corporate_account(tweet: dict) -> bool:
    """Return True if the tweet appears to be from a corporate/brand account (skip these)."""
    text = " ".join([
        tweet.get("username", ""),
        tweet.get("title", ""),
        tweet.get("description", ""),
    ])
    corporate_keywords = [
        # 企業・法人
        "株式会社", "有限会社", "合同会社", "一般社団法人", "公益財団法人",
        "Inc.", "Co.,Ltd", "Corp.", "LLC",
        # PR・公式
        "公式", "official", "Official", "PR", "広報",
        # 企業系サービス・メディア
        "編集部", "メディア", "ニュース", "news", "News",
        "サービス", "サポート", "support", "Support",
        "ショップ", "shop", "Shop", "store", "Store",
        "通販", "EC", "販売",
        # 医療・専門機関
        "病院", "クリニック", "医院", "薬局",
        # ブランド系
        "ブランド", "brand", "Brand",
    ]
    return any(kw in text for kw in corporate_keywords)


def _get_daily_engage_schedule() -> list[tuple[int, int, int]]:
    """Get today's engagement schedule: [(hour, minute, count), ...].

    3 batches seeded by date so times vary each day:
      Batch 1 (朝): 10〜11時台  → 2件
      Batch 2 (昼): 13〜16時台  → 2件
      Batch 3 (夜): 19〜21時台  → 1件
    """
    import random
    now = get_jst_now()
    seed = int(now.strftime("%Y%m%d"))
    rng = random.Random(seed)

    h1 = rng.randint(10, 11); m1 = rng.choice([0, 15, 30, 45])
    h2 = rng.randint(13, 16); m2 = rng.choice([0, 15, 30, 45])
    h3 = rng.randint(19, 21); m3 = rng.choice([0, 15, 30, 45])
    return [(h1, m1, 2), (h2, m2, 2), (h3, m3, 1)]


def run_engagement_replies(count: int = 5):
    """Search general parenting tweets and post empathy replies (no approval needed).

    - Targets: 育児全般のハッシュタグ
    - Skips male accounts
    - No approval needed, auto-posts
    """
    from twitter_engage import (
        search_tweets, generate_reply, post_reply,
        get_replied_tweet_ids, load_engage_log, save_engage_log,
    )
    from twitter_utils import validate_tweet_text

    logger.info(f"=== Engagement START (target: {count} replies) ===")

    hashtags = [
        "#育児垢さんと繋がりたい",
        "#ママさんと繋がりたい",
        "#育児あるある",
        "#1歳児のいる生活",
        "#子育て日記",
        "#ワンオペ育児",
        "#育児ママと繋がりたい",
        "#幼児食",
        "#イヤイヤ期",
        "#1歳10ヶ月",
    ]

    replied_ids = get_replied_tweet_ids()
    candidates = []
    seen_ids = set()

    for tag in hashtags:
        tweets = search_tweets(f"{tag} site:x.com")
        for t in tweets:
            if t["tweet_id"] not in replied_ids and t["tweet_id"] not in seen_ids:
                if _is_male_account(t):
                    logger.debug(f"  Skipping male account: @{t.get('username','?')}")
                    continue
                if _is_corporate_account(t):
                    logger.debug(f"  Skipping corporate account: @{t.get('username','?')}")
                    continue
                seen_ids.add(t["tweet_id"])
                candidates.append(t)
        if len(candidates) >= count * 4:  # enough candidates
            break

    logger.info(f"Found {len(candidates)} candidates (male accounts excluded)")

    posted = 0
    for tweet in candidates:
        if posted >= count:
            break

        reply_text = generate_reply(tweet)
        if not reply_text:
            continue

        ok, _ = validate_tweet_text(reply_text)
        if not ok:
            continue

        result = post_reply(
            tweet_id=tweet["tweet_id"],
            reply_text=reply_text,
            username=tweet.get("username", ""),
        )
        if result.get("status") == "published":
            log = load_engage_log()
            log["replies"].append({
                "target_tweet_id": tweet["tweet_id"],
                "target_username": tweet.get("username", ""),
                "reply_text": reply_text,
                "reply_id": result.get("reply_id", ""),
                "timestamp": get_jst_now().isoformat(),
                "source": "engagement_auto",
            })
            save_engage_log(log)
            posted += 1
            logger.info(f"  [{posted}/{count}] @{tweet.get('username','?')}: {reply_text[:50]}...")

    logger.info(f"=== Engagement done: {posted}/{count} replies posted ===")


def generate_weekly_plans(start_offset: int = 1):
    """Generate 7 days of tweet plans and upload ONE Excel with 7 sheets.

    Args:
        start_offset: first day offset from today (1=tomorrow for Friday auto-gen,
                      0=today for immediate/manual generation)

    Called every Friday at 09:00 JST (start_offset=1 → Sat through next Fri).
    Can also be called manually with start_offset=0 to generate from today.
    Creates tweet_plan_weekly_YYYY-MM-DD.xlsx with one sheet per day, uploads once.
    """
    from teams_dashboard import generate_daily_plan
    from plan_replies import plan_daily_replies, merge_replies_into_plan
    from generate_daily_excel import create_weekly_excel
    from teams_upload import upload_file

    now = get_jst_now()
    day_names_jp = ["月", "火", "水", "木", "金", "土", "日"]
    weekly_plans = {}  # date_str → plan dict

    # Load squad intelligence once for the entire weekly generation
    intel = load_twitter_intel()
    if intel:
        logger.info(f"Squad intelligence loaded ({len(intel)} chars)")
    else:
        logger.info("No squad intelligence available — generating without intel")

    for day_offset in range(start_offset, start_offset + 7):  # 7日分
        target = now + timedelta(days=day_offset)
        target_str = target.strftime("%Y-%m-%d")
        day_jp = day_names_jp[target.weekday()]

        logger.info(f"=== Generating {target_str} ({day_jp}) ===")

        # Step 1: Generate tweets via Claude API (with squad intel)
        plan = generate_daily_plan(slots=SLOTS, target_date=target_str,
                                   intel_text=intel)
        if not plan or not plan.get("slots"):
            logger.warning(f"{target_str} plan generation failed — skipping")
            continue

        # Save plan JSON locally and upload to SharePoint for GitHub Actions
        plan_file = TMP_DIR / f"daily_tweet_plan_{target_str}.json"
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        with open(plan_file, "w", encoding="utf-8") as _f:
            import json as _json
            _json.dump(plan, _f, ensure_ascii=False, indent=2)
        try:
            from teams_upload import upload_plan_json
            upload_plan_json(str(plan_file), target_str)
        except Exception as _e:
            logger.warning(f"SharePoint plan upload failed for {target_str}: {_e}")

        # Step 2: Generate reply drafts for slots with engage_count > 0
        reply_slots = [s for s in SLOTS if SLOT_CONFIG.get(s, {}).get("engage_count", 0) > 0]
        if reply_slots:
            try:
                reply_plans = plan_daily_replies(reply_slots)
                merged = merge_replies_into_plan(reply_plans, plan_file=str(plan_file))
                if merged:
                    plan = merged
            except Exception as e:
                logger.warning(f"Reply planning failed for {target_str}: {e}")

        weekly_plans[target_str] = plan

    if not weekly_plans:
        logger.error("No plans generated — weekly upload aborted")
        return

    # Step 3: Create ONE Excel with 7 sheets (one per day, tweets only)
    excel_path = create_weekly_excel(weekly_plans, include_replies=False)
    logger.info(f"Weekly Excel: {excel_path}")

    # Step 4: Upload once to Teams
    start_str = sorted(weekly_plans.keys())[0]
    end_str = sorted(weekly_plans.keys())[-1]
    try:
        msg = f"今週({start_str}〜{end_str})のツイートプランです（7日分・シート別）。Confirmed/Declinedで承認してください。"
        result = upload_file(excel_path, notify=True, message=msg)
        logger.info(f"Weekly Excel uploaded: {result.get('web_url', '')}")
    except Exception as e:
        logger.warning(f"Weekly Excel upload failed: {e}")

    logger.info(f"=== Weekly generation done: {len(weekly_plans)}/7 days in one file ===")


def _generate_weekend_plans():
    """Generate Saturday + Sunday tweet plans (no replies) and upload.

    Called on Friday at 16:00. Creates separate Excel files for each day.
    """
    from teams_dashboard import generate_daily_plan
    from generate_daily_excel import create_daily_excel
    from teams_upload import upload_file

    now = get_jst_now()

    for day_offset, day_label in [(1, "weekend_sat"), (2, "weekend_sun")]:
        target = now + timedelta(days=day_offset)
        target_str = target.strftime("%Y-%m-%d")
        day_name = "토요일" if day_offset == 1 else "일요일"

        logger.info(f"=== GENERATING {day_name} ({target_str}) PLAN ===")

        plan = generate_daily_plan(target_date=target_str)
        if not plan or not plan.get("slots"):
            logger.warning(f"{day_name} plan generation failed")
            continue

        excel_path = create_daily_excel(
            plan,
            include_replies=False,
            label=day_label,
        )
        logger.info(f"Weekend Excel: {excel_path}")

        try:
            msg = f"{day_name} ({target_str}) 트윗 플랜입니다. 주말은 트윗만 (리플 없음). Confirmed/Declined로 승인해주세요."
            result = upload_file(excel_path, notify=True, message=msg)
            logger.info(f"Uploaded: {result.get('web_url', '')}")
        except Exception as e:
            logger.warning(f"Weekend upload failed: {e}")


def run_daemon():
    """Run all day with AM/PM split schedule.

    Timeline (JST):
        08:00  Generate AM tweets + search AM reply targets
        08:30  AM Excel (9,11,13,15) → Teams upload
        09:00  Slot 9 (T-10min trigger at 08:50)
        11:00  Slot 11
        13:00  Slot 13
        15:00  Slot 15
        15:30  Generate PM tweets + search PM reply targets
        16:00  PM Excel (17,19,21,23) → Teams upload
               Friday: also upload Sat/Sun plans (tweets only)
        17:00  Slot 17 (T-10min trigger at 16:50)
        19:00  Slot 19
        21:00  Slot 21
        23:00  Slot 23
        00:00  Reset for next day
    """
    logger.info("=== DAEMON MODE: AM/PM split schedule ===")
    logger.info(f"AM slots: {AM_SLOTS} | PM slots: {PM_SLOTS}")

    executed_today = set()
    plan_generated = False

    # Check if plan already exists for today → skip regeneration
    plan_file = _plan_path()  # date-specific: daily_tweet_plan_YYYY-MM-DD.json
    if plan_file.exists():
        try:
            with open(plan_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_slots = set(int(s) for s in existing.get("slots", {}).keys())
            if set(SLOTS).issubset(existing_slots):
                plan_generated = True
                logger.info(f"Plan already exists for {existing.get('date')} — skipping generation")
        except Exception:
            pass

    while True:
      try:
        now = get_jst_now()
        h, m = now.hour, now.minute

        # ── 09:00 JST Friday: Generate next week's plans (Sat-Fri) ──────
        if h == 9 and m == 0 and now.weekday() == 4 and not plan_generated:
            logger.info("=== Weekly plan generation (Friday 09:00) ===")
            try:
                generate_weekly_plans()
            except Exception as e:
                logger.error(f"Weekly generation failed: {e}")
            plan_generated = True

        # ── Each slot: trigger at T-APPROVAL_WAIT_MINUTES ────────────────
        for slot in SLOTS:
            if slot in executed_today:
                continue

            trigger_time = datetime(
                now.year, now.month, now.day, slot, 0,
                tzinfo=now.tzinfo,
            ) - timedelta(minutes=APPROVAL_WAIT_MINUTES)

            if trigger_time.hour == h and trigger_time.minute == m:
                logger.info(f"Triggering slot {slot} (T-{APPROVAL_WAIT_MINUTES}min)")
                executed_today.add(slot)
                try:
                    run_slot(slot)
                except Exception as e:
                    logger.error(f"Slot {slot} failed: {e}")

        # ── 競合モニター: 毎日 09:00 JST ────────────────────────────────
        if h == 9 and m == 0 and "competitor_monitor" not in executed_today:
            executed_today.add("competitor_monitor")
            logger.info("=== Competitor monitor START ===")
            try:
                from competitor_monitor import run_monitor
                run_monitor()
            except Exception as e:
                logger.error(f"Competitor monitor failed: {e}")

        # ── 育児共感コメント (3 random batches/day, total 5 replies) ─────
        for eng_h, eng_m, eng_count in _get_daily_engage_schedule():
            eng_key = f"engage_{eng_h}_{eng_m}"
            if h == eng_h and m == eng_m and eng_key not in executed_today:
                executed_today.add(eng_key)
                logger.info(f"Engagement batch: {eng_h}:{eng_m:02d} ({eng_count} replies)")
                try:
                    run_engagement_replies(count=eng_count)
                except Exception as e:
                    logger.error(f"Engagement failed: {e}")

        # ── Reset at midnight ────────────────────────────────────────────
        if h == 0 and m == 0:
            logger.info(f"=== MIDNIGHT RESET: {now.strftime('%Y-%m-%d')} → {(now + timedelta(days=1)).strftime('%Y-%m-%d')} ===")
            executed_today.clear()
            plan_generated = False

      except Exception as e:
        logger.error(f"Daemon loop error: {e}", exc_info=True)

      time.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twitter auto-scheduler with Teams approval")
    parser.add_argument("--slot", type=int, help="Run specific slot")
    parser.add_argument("--daemon", action="store_true", help="Run all day")
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--generate-am", action="store_true", help="Generate AM plan + upload")
    parser.add_argument("--generate-pm", action="store_true", help="Generate PM plan + upload")
    parser.add_argument("--generate-weekend", action="store_true", help="Generate Sat/Sun plans")
    parser.add_argument("--generate-weekly", action="store_true", help="Generate 7-day plan from today + upload to Teams")
    args = parser.parse_args()

    if args.daemon:
        run_daemon()
    elif args.generate_weekly:
        generate_weekly_plans(start_offset=0)  # today through 6 days ahead
    elif args.generate_am:
        generate_and_upload(slots=AM_SLOTS, label="AM", include_replies=True)
    elif args.generate_pm:
        generate_and_upload(slots=PM_SLOTS, label="PM", include_replies=True)
    elif args.generate_weekend:
        _generate_weekend_plans()
    elif args.slot:
        run_slot(args.slot, dry_run=args.dry_run)
    else:
        # Run next upcoming slot
        now = get_jst_now()
        next_slot = None
        for s in SLOTS:
            if s > now.hour or (s == now.hour and now.minute < 50):
                next_slot = s
                break
        if next_slot is None:
            next_slot = SLOTS[0]  # wrap to tomorrow

        logger.info(f"Next slot: {next_slot}:00 JST")
        run_slot(next_slot, dry_run=args.dry_run)
