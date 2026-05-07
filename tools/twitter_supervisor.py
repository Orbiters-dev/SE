"""
監督: 毎朝09:00 JSTに今日の全部隊スケジュールをTeamsに通知する。

- 今日のプランをSharePoint/ローカルから読み込む
- 10:00・19:00の予定ツイートをTeamsに送信
- コメンター・調査マンの予定も案内
- 承認待ちの場合は「承認してください」と促す
"""

import os
import sys
import json
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

PROJECT_ROOT = Path(__file__).parent.parent
TMP_DIR = PROJECT_ROOT / ".tmp"

JST = timezone(timedelta(hours=9))
SLOT_INFO = {
    10: "朝の投稿",
    19: "夜の投稿",
}


def get_today_plan() -> dict:
    """今日のプランをローカルまたはSharePointから取得する。"""
    date_str = datetime.now(JST).strftime("%Y-%m-%d")
    local_path = TMP_DIR / f"daily_tweet_plan_{date_str}.json"

    if not local_path.exists():
        try:
            from teams_upload import download_plan_json
            download_plan_json(date_str, str(local_path))
        except Exception as e:
            logger.warning(f"SharePoint download failed: {e}")

    if local_path.exists():
        with open(local_path, encoding="utf-8") as f:
            return json.load(f), date_str

    return {}, date_str


def get_approval_status(date_str: str) -> dict:
    """ExcelからConfirmed/Declined状態を取得する。"""
    status = {10: "pending", 19: "pending"}
    try:
        from excel_feedback import download_plan_excel, read_feedback
        excel_path = download_plan_excel()
        if excel_path:
            feedbacks = read_feedback(excel_path)
            for fb in feedbacks:
                slot = fb.get("slot")
                if slot in (10, 19):
                    status[slot] = fb.get("action", "pending")
    except Exception as e:
        logger.warning(f"Excel check failed: {e}")
    return status


def send_daily_briefing(plan: dict, date_str: dict, approval: dict):
    """今日のツイート予定をTeamsに通知する。"""
    import requests

    webhook_url = os.getenv("TEAMS_WEBHOOK_URL") or os.getenv("TEAMS_MASTER_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("No Teams webhook URL configured")
        return

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_names = ["月", "火", "水", "木", "金", "土", "日"]
    day_jp = day_names[dt.weekday()]

    slots = plan.get("slots", {})

    lines = [f"📋 **{date_str}（{day_jp}）のツイート予定**\n"]

    for slot in [10, 19]:
        slot_data = slots.get(str(slot), {})
        tweet = slot_data.get("tweet_jp", "")
        category = slot_data.get("category", "")
        approval_status = approval.get(slot, "pending")

        if approval_status == "approve":
            status_icon = "✅ 承認済み"
        elif approval_status == "cancel":
            status_icon = "❌ Declined"
        else:
            status_icon = "⏳ 承認待ち"

        label = SLOT_INFO.get(slot, f"{slot}:00")
        lines.append(f"**{slot}:00 {label}** [{category}] {status_icon}")
        if tweet:
            lines.append(f"> {tweet[:100]}{'...' if len(tweet) > 100 else ''}")
        else:
            lines.append("> （プランなし）")
        lines.append("")

    pending = [s for s in [10, 19] if approval.get(s, "pending") == "pending" and slots.get(str(s))]
    if pending:
        slots_str = "・".join([f"{s}:00" for s in pending])
        lines.append(f"⚠️ **{slots_str} の承認をお願いします。**")
        lines.append("Excelで「Confirmed」を入力して保存してください。")
        lines.append("")

    lines.append("---")
    lines.append("🗓️ **今日の部隊スケジュール**")
    lines.append("12:00〜16:00 コメンター（1時間ごとに共感コメント × 5）")
    lines.append("16:00 調査マン（競合・参考ブランドのTwitter調査レポート）")

    message = "\n".join(lines)

    payload = {"text": message}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Daily briefing sent to Teams")
    except Exception as e:
        logger.error(f"Teams notification failed: {e}")


def persist_approval_to_plan(date_str: str, approval: dict) -> bool:
    """Excelの承認状態をプランJSONに書き込んでSharePointに再アップロードする。

    これにより、10:00のツイート投稿時にExcelが読めなくても
    プランJSONのapprovedフラグでフォールバックできる。
    """
    local_path = TMP_DIR / f"daily_tweet_plan_{date_str}.json"
    if not local_path.exists():
        logger.info("Plan JSON not found locally — skipping approval persistence")
        return False

    try:
        with open(local_path, encoding="utf-8") as f:
            plan = json.load(f)

        changed = False
        for slot, action in approval.items():
            slot_key = str(slot)
            if slot_key in plan.get("slots", {}):
                if action == "approve" and not plan["slots"][slot_key].get("approved"):
                    plan["slots"][slot_key]["approved"] = True
                    changed = True
                    logger.info(f"Slot {slot}: approved=True persisted to plan JSON")
                elif action in ("cancel", "replace"):
                    if action == "cancel":
                        plan["slots"][slot_key]["cancelled"] = True
                    changed = True

        if not changed:
            return False

        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)

        # Re-upload to SharePoint so tweet runner can download it
        try:
            from teams_upload import upload_plan_json
            upload_plan_json(str(local_path), date_str)
            logger.info(f"Updated plan JSON re-uploaded to SharePoint for {date_str}")
            return True
        except Exception as e:
            logger.warning(f"Plan JSON re-upload failed: {e}")
            return False

    except Exception as e:
        logger.warning(f"Approval persistence failed: {e}")
        return False


def main():
    plan, date_str = get_today_plan()

    if not plan or not plan.get("slots"):
        logger.warning(f"No plan found for {date_str}")
        # プランがない場合もその旨をTeamsに通知
        import requests
        webhook_url = os.getenv("TEAMS_WEBHOOK_URL") or os.getenv("TEAMS_MASTER_WEBHOOK_URL")
        if webhook_url:
            requests.post(webhook_url, json={
                "text": f"⚠️ **監督**: {date_str} のツイートプランが見つかりません。企画マンを手動実行してください。"
            }, timeout=10)
        return

    approval = get_approval_status(date_str)

    # 承認状態をプランJSONに保存（10:00投稿時のフォールバック用）
    persist_approval_to_plan(date_str, approval)

    send_daily_briefing(plan, date_str, approval)


if __name__ == "__main__":
    main()
