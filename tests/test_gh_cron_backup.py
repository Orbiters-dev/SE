import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import gh_cron_backup  # noqa: E402

NOW = datetime(2026, 9, 23, 3, 40, tzinfo=timezone.utc)  # KST 12:40 (Wed)
DAILY = {"wf": "ppc_briefing", "owner": "o", "freq": "daily", "crons": ["0 0 * * *"]}
WEEKLY = {"wf": "wednesday_ig_competitor", "owner": "o", "freq": "weekly", "crons": ["0 1 * * 3"]}
HOURLY = {"wf": "h", "owner": "o", "freq": "hourly+", "crons": ["*/30 * * * *"]}
TWICE = {"wf": "meta_ads_daily", "owner": "o", "freq": "daily", "crons": ["0 8 * * *", "0 20 * * *"]}


def _run(event, conclusion, at, status="completed"):
    return {"event": event, "conclusion": conclusion, "status": status,
            "created_at": at.strftime("%Y-%m-%dT%H:%M:%SZ")}


def _decide(monkeypatch, meta, runs, now=NOW):
    monkeypatch.setattr(gh_cron_backup, "gh_get", lambda tok, path, params=None: {"workflow_runs": runs})
    return gh_cron_backup.check_workflow("token", meta, now)["decision"]


@pytest.mark.parametrize("meta,runs,expected", [
    # 미트리거 (run 없음) → 보충 dispatch
    (DAILY, [], "dispatch"),
    (WEEKLY, [], "dispatch"),
    (HOURLY, [_run("schedule", "failure", NOW - timedelta(hours=3))], "dispatch"),
    (DAILY, [_run("schedule", "failure", NOW - timedelta(days=1))], "dispatch"),
    # 마지막 fire 이전의 수동 dispatch 실패는 그 fire 를 덮지 않는다
    (DAILY, [_run("workflow_dispatch", "failure", NOW.replace(day=22, hour=16))], "dispatch"),
    # schedule 이 이미 fire → 실패여도 재dispatch 하지 않는다
    (DAILY, [_run("schedule", "failure", NOW.replace(hour=0, minute=18))], "skip"),
    (WEEKLY, [_run("schedule", "failure", NOW.replace(hour=1, minute=17))], "skip"),
    (HOURLY, [_run("schedule", "failure", NOW - timedelta(minutes=20))], "skip"),
    # 백업이 이미 보충 dispatch 한 fire 는 실패여도 다시 dispatch 하지 않는다
    (DAILY, [_run("workflow_dispatch", "failure", NOW.replace(hour=0, minute=40))], "skip"),
    # 기존 동작 유지: 창 안 success 가 있으면 skip
    (DAILY, [_run("workflow_dispatch", "success", NOW.replace(day=22, hour=16))], "skip"),
])
def test_dispatch_only_when_schedule_never_fired(monkeypatch, meta, runs, expected):
    assert _decide(monkeypatch, meta, runs) == expected


def test_earlier_fire_does_not_mask_later_missing_fire(monkeypatch):
    # 08:00 / 20:00 UTC 2-cron: 어제 20:00 fire 의 실패 run 이 오늘 08:00 fire 미트리거를 가리면 안 된다
    now = datetime(2026, 9, 23, 8, 40, tzinfo=timezone.utc)
    prev_fire = _run("schedule", "failure", datetime(2026, 9, 22, 20, 10, tzinfo=timezone.utc))
    assert _decide(monkeypatch, TWICE, [prev_fire], now) == "dispatch"
    this_fire = _run("schedule", "failure", datetime(2026, 9, 23, 8, 13, tzinfo=timezone.utc))
    assert _decide(monkeypatch, TWICE, [prev_fire, this_fire], now) == "skip"


def test_kst_midnight_window_reset_does_not_redispatch(monkeypatch):
    # 15:40 UTC = KST 00:40: 새 KST 창엔 run 이 없어도 오늘(UTC) 00:00 fire 는 00:18 에 이미 돌았다
    now = datetime(2026, 9, 22, 15, 40, tzinfo=timezone.utc)
    ran = _run("schedule", "success", datetime(2026, 9, 22, 0, 18, tzinfo=timezone.utc))
    assert _decide(monkeypatch, DAILY, [ran], now) == "skip"


def test_disabled_workflow_is_not_dispatched(monkeypatch):
    # disabled_manually 워크플로우 dispatch → HTTP 422 → 백업 run 실패 (communicator.yml 매시간)
    disabled = {**DAILY, "state": "disabled_manually"}
    assert _decide(monkeypatch, disabled, []) == "skip"
