"""
総監督: 毎日09:00 JSTに昨日の全部隊活動をTeamsへ報告。

序列: 総監督 → 監督 → ツイート・コメンター・調査マン

担当部隊:
  - ツイート     10:00 / 19:00 投稿（成功/失敗/スキップ）
  - コメンター   12:00〜16:00 育児ママへ共感コメント
  - 調査マン     水・金 09:00 競合ブランドTwitter調査
  - 監督         09:00 朝の承認確認
"""

import os
import sys
import json
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
GITHUB_REPO   = "kazukiii1128-del/Twitter"
WEBHOOK_URL   = os.getenv("TEAMS_MASTER_WEBHOOK_URL") or os.getenv("TEAMS_WEBHOOK_URL")

WORKFLOW_IDS = {
    "ツイート":             246628394,
    "コメンター":           246685095,
    "監督":                 246630423,
    "調査マン":             246698377,
    "ハッシュタグ調査マン": "hashtag.yml",
}


def get_yesterday_runs(wf_id: int) -> list[dict]:
    """昨日(JST)に実行されたrunを返す。09:00報告なので昨日の実績を確認。"""
    if not GITHUB_TOKEN:
        return []

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    yesterday_jst = (datetime.now(JST) - timedelta(days=1)).date()

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{wf_id}/runs",
            params={"per_page": 20},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        runs = []
        for run in resp.json().get("workflow_runs", []):
            created_utc = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            created_jst = created_utc.astimezone(JST)
            if created_jst.date() == yesterday_jst:
                runs.append({
                    "name":       run.get("name", ""),
                    "status":     run.get("status", ""),
                    "conclusion": run.get("conclusion", ""),
                    "created_jst": created_jst.strftime("%H:%M"),
                })
        return runs
    except Exception as e:
        logger.warning(f"GitHub API error for workflow {wf_id}: {e}")
        return []


def summarize_runs(runs: list[dict]) -> str:
    """run結果を1行テキストに要約。"""
    if not runs:
        return "実行なし"

    icons = {"success": "✅", "failure": "❌", "skipped": "⏭️"}
    parts = []
    for r in runs:
        icon = icons.get(r["conclusion"], "⏳")
        parts.append(f"{icon} {r['created_jst']}")
    return "  ".join(parts)


def get_tweet_detail() -> str:
    """ツイート部隊の詳細：昨日投稿されたツイートをプランJSONから取得。"""
    date_str = (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
    tmp_dir  = Path(__file__).parent.parent / ".tmp"
    plan_path = tmp_dir / f"daily_tweet_plan_{date_str}.json"

    if not plan_path.exists():
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from teams_upload import download_plan_json
            download_plan_json(date_str, str(plan_path))
        except Exception:
            pass

    if not plan_path.exists():
        return ""

    try:
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
        lines = []
        for slot in ["10", "19"]:
            data = plan.get("slots", {}).get(slot, {})
            tweet = data.get("tweet_jp", "")
            if tweet:
                label = "朝" if slot == "10" else "夜"
                lines.append(f"  {label}({slot}:00): {tweet[:60]}{'...' if len(tweet) > 60 else ''}")
        return "\n".join(lines)
    except Exception:
        return ""


def build_report() -> str:
    today = datetime.now(JST)
    yesterday = today - timedelta(days=1)
    date_str = yesterday.strftime("%Y-%m-%d")
    day_names = ["月", "火", "水", "木", "金", "土", "日"]
    day_jp = day_names[yesterday.weekday()]
    was_chousa_day   = yesterday.weekday() in (2, 4)  # 水=2, 金=4
    was_hashtag_day  = yesterday.weekday() == 4       # 金=4のみ

    lines = [f"📊 **総監督 朝報告 — 昨日({date_str}・{day_jp})の実績**\n"]
    lines.append("序列: 総監督 → 監督 → ツイート・コメンター・調査マン\n")

    # ── 監督 ─────────────────────────────────────
    kantoku_runs = get_yesterday_runs(WORKFLOW_IDS["監督"])
    lines.append(f"**📋 監督** (09:00 朝の確認)")
    lines.append(f"  {summarize_runs(kantoku_runs)}")
    lines.append("")

    # ── ツイート ──────────────────────────────────
    tweet_runs = get_yesterday_runs(WORKFLOW_IDS["ツイート"])
    lines.append(f"**🐦 ツイート投稿** (10:00 / 19:00)")
    lines.append(f"  {summarize_runs(tweet_runs)}")
    tweet_detail = get_tweet_detail()
    if tweet_detail:
        lines.append(tweet_detail)
    lines.append("")

    # ── コメンター ────────────────────────────────
    commenter_runs = get_yesterday_runs(WORKFLOW_IDS["コメンター"])
    success_count = sum(1 for r in commenter_runs if r["conclusion"] == "success")
    fail_count    = sum(1 for r in commenter_runs if r["conclusion"] == "failure")
    lines.append(f"**💬 コメンター** (12〜16時 × 5本)")
    if commenter_runs:
        lines.append(f"  {summarize_runs(commenter_runs)}")
        lines.append(f"  成功 {success_count}本 / 失敗 {fail_count}本")
    else:
        lines.append("  実行なし")
    lines.append("")

    # ── 調査マン（水・金のみ）─────────────────────
    if was_chousa_day:
        chousa_runs = get_yesterday_runs(WORKFLOW_IDS["調査マン"])
        lines.append(f"**🔍 調査マン** (09:00 競合Twitter調査)")
        lines.append(f"  {summarize_runs(chousa_runs)}")
        lines.append("")

    # ── ハッシュタグ調査マン（金曜のみ）─────────────
    if was_hashtag_day:
        hashtag_runs = get_yesterday_runs(WORKFLOW_IDS["ハッシュタグ調査マン"])
        lines.append(f"**#️⃣ ハッシュタグ調査マン** (09:00 人気ハッシュタグ調査)")
        lines.append(f"  {summarize_runs(hashtag_runs)}")
        lines.append("")

    # ── 問題サマリー ──────────────────────────────
    all_runs = tweet_runs + commenter_runs + kantoku_runs
    if was_chousa_day:
        all_runs += get_yesterday_runs(WORKFLOW_IDS["調査マン"])
    if was_hashtag_day:
        all_runs += get_yesterday_runs(WORKFLOW_IDS["ハッシュタグ調査マン"])

    failures = [r for r in all_runs if r["conclusion"] == "failure"]
    no_runs  = []
    if not tweet_runs:
        no_runs.append("ツイート（昨日実行なし）")
    if not commenter_runs:
        no_runs.append("コメンター（昨日実行なし）")

    if failures or no_runs:
        lines.append("---")
        lines.append("🚨 **【総監督より】昨日、動いてへんやつがおる。すぐ確認して！**\n")
        for r in failures:
            lines.append(f"❌ **{r['name']}** ({r['created_jst']}) — 失敗してる！GitHub Actionsのログを確認して！")
        for name in no_runs:
            lines.append(f"⚠️ **{name}** — 昨日1回も実行されてへん！スケジュール確認して！")
        lines.append("\n**→ 今すぐ https://github.com/kazukiii1128-del/Twitter/actions を確認してください**")
    else:
        lines.append("---")
        lines.append("✅ **【総監督より】昨日の全部隊、問題なく稼働。今日もよろしく！**")

    return "\n".join(lines)


def main():
    report = build_report()
    logger.info("Report built:\n" + report)

    if not WEBHOOK_URL:
        logger.warning("TEAMS_WEBHOOK_URL not set — skipping notification")
        return

    try:
        resp = requests.post(WEBHOOK_URL, json={"text": report}, timeout=10)
        resp.raise_for_status()
        logger.info("Report sent to Teams")
    except Exception as e:
        logger.error(f"Teams notification failed: {e}")
        raise


if __name__ == "__main__":
    main()
