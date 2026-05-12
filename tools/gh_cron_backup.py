"""GH Actions schedule cron 미트리거 백업 → webhook (workflow_dispatch) 강제 실행.

매시간 (X:30 권장) 외부 cron에서 호출:
- 37개 schedule cron 워크플로우 점검
- daily 워크플로우: 오늘 KST schedule success 없고, 마지막 cron 예상시각 + 30분 경과 → dispatch
- weekly 워크플로우: 이번 주 (KST 월 0시 기준) success 없고, 마지막 예상시각 + 30분 경과 → dispatch
- hourly+ 워크플로우: 마지막 schedule run + 1.5h 경과 → dispatch

Env:
  GH_TOKEN (PAT) — repo:write 권한
  GH_REPO       — Orbiters-dev/SE (기본값)
"""
from __future__ import annotations
import argparse, json, os, sys, re, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

KST = timezone(timedelta(hours=9))
REPO = os.getenv('GH_REPO', 'Orbiters-dev/SE')
WF_DIR = Path(__file__).resolve().parent.parent / '.github' / 'workflows'

OWNER_MAP = {
    'meta_jp_daily': 'meta-ads', 'meta_jp_weekly': 'meta-ads', 'meta_ads_daily': 'meta-ads',
    'chousa': 'twitter-squad', 'kantoku': 'twitter-squad', 'kikaku': 'twitter-squad',
    'soukantoku': 'twitter-squad', 'hashtag': 'twitter-squad', 'commenter': 'twitter-squad',
    'tweet': 'twitter-squad', 'twitter_slot_notify': 'twitter-squad',
    'data_keeper': 'data-keeper', 'data_keeper_keywords': 'data-keeper',
    'amazon_ppc_pipeline': 'amazon-ppc', 'amazon_ppc_check_execute': 'amazon-ppc',
    'ppc_briefing': 'amazon-ppc', 'ppc_dashboard_action': 'amazon-ppc',
    'ppc_email_check': 'amazon-ppc', 'ppc_simulator': 'amazon-ppc',
    'auto_posted_tracker': 'rigongi', 'wl_codes_sync': 'rigongi',
    'syncly_daily': 'syncly', 'apify_daily': 'syncly', 'apify_twitter_daily': 'syncly',
    'weekly_ig_content': 'inhwagi', 'wednesday_ig_competitor': 'inhwagi',
    'communicator': 'communicator',
    'kpi_validator': 'golmani', 'kpi_weekly': 'golmani', 'financial_dashboard': 'golmani',
    'einstein_daily': 'einstein', 'einstein_weekly': 'einstein',
    'ci_watchdog': 'general', 'workflow_analyzer': 'general', 'skill_optimizer': 'general',
    'skill_optimizer_check': 'general', 'youtube_to_teams': 'general',
    'gh_cron_backup': 'self',
}

# required-input 워크플로우는 dispatch 불가 (skip + 경고)
SKIP_REQUIRED_INPUT = {'twitter_slot_notify'}


def scan_workflows() -> list[dict]:
    metas = []
    for yml in sorted(WF_DIR.glob('*.yml')):
        text = yml.read_text(encoding='utf-8', errors='ignore')
        if 'cron:' not in text:
            continue
        crons = re.findall(r"cron:\s*['\"]([^'\"]+)['\"]", text)
        name = yml.stem
        freq = 'daily'
        for c in crons:
            parts = c.split()
            if len(parts) == 5:
                if parts[4] != '*':
                    freq = 'weekly'
                if '*/' in parts[0] or '*/' in parts[1]:
                    freq = 'hourly+'
                if ',' in parts[1] and freq == 'daily':
                    freq = 'multi-daily'
        metas.append({
            'wf': name,
            'owner': OWNER_MAP.get(name, 'unknown'),
            'freq': freq,
            'crons': crons,
        })
    return metas


def gh_token() -> str:
    tok = os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')
    if tok:
        return tok
    try:
        p = subprocess.run(
            ['git', 'credential', 'fill'],
            input='protocol=https\nhost=github.com\n\n',
            capture_output=True, text=True, timeout=5,
        )
        for line in p.stdout.splitlines():
            if line.startswith('password='):
                return line[len('password='):]
    except Exception:
        pass
    raise RuntimeError('GH_TOKEN not found (env or git credential)')


def gh_get(token: str, path: str, params: Optional[dict] = None) -> dict:
    r = requests.get(
        f'https://api.github.com{path}',
        headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github+json'},
        params=params or {},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def gh_post(token: str, path: str, body: dict) -> int:
    r = requests.post(
        f'https://api.github.com{path}',
        headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github+json'},
        json=body,
        timeout=15,
    )
    return r.status_code


def crons_for(meta: dict) -> list[str]:
    return meta.get('crons', [])


CRON_DOW_TO_UTC_WEEKDAY = {0: 6, 7: 6, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}


def _expand_dow(dow_part: str) -> list[int]:
    """cron dow 필드를 UTC weekday (0=월..6=일) 리스트로 변환. '*' 는 [].
    daily 처리(*) 는 caller가 따로 분기."""
    out: set[int] = set()
    for token in dow_part.split(','):
        if '-' in token:
            try:
                a, b = map(int, token.split('-'))
                for n in range(a, b + 1):
                    if n in CRON_DOW_TO_UTC_WEEKDAY:
                        out.add(CRON_DOW_TO_UTC_WEEKDAY[n])
            except ValueError:
                pass
        else:
            try:
                n = int(token)
            except ValueError:
                continue
            if n in CRON_DOW_TO_UTC_WEEKDAY:
                out.add(CRON_DOW_TO_UTC_WEEKDAY[n])
    return sorted(out)


def last_fire_in_period(crons: list[str], now_utc: datetime, freq: str) -> Optional[datetime]:
    """이번 주기(daily=today / weekly=이번 주 월요일~) 안에서 cron이 fire되어야 했던 시각 중,
    이미 지나간 것의 max."""
    if freq == 'weekly':
        period_start = (now_utc - timedelta(days=now_utc.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        days = 7
    else:
        period_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        days = 1

    fires: list[datetime] = []
    for c in crons:
        parts = c.split()
        if len(parts) != 5:
            continue
        m_part, h_part, _, _, dow_part = parts
        if '*/' in m_part or '*/' in h_part:
            continue
        m_list = m_part.split(',') if ',' in m_part else [m_part]
        h_list = h_part.split(',') if ',' in h_part else [h_part]

        if dow_part == '*':
            day_offsets = list(range(days))
        else:
            target_weekdays = _expand_dow(dow_part)
            day_offsets = [d for d in range(days) if (period_start + timedelta(days=d)).weekday() in target_weekdays]

        for off in day_offsets:
            for h in h_list:
                for m in m_list:
                    try:
                        fires.append(period_start + timedelta(days=off, hours=int(h), minutes=int(m)))
                    except ValueError:
                        pass
    past = [f for f in fires if f <= now_utc]
    return max(past) if past else None


def kst_today_start_utc(now_utc: datetime) -> datetime:
    return now_utc.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def kst_week_start_utc(now_utc: datetime) -> datetime:
    kst = now_utc.astimezone(KST)
    monday = kst - timedelta(days=kst.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def check_workflow(token: str, meta: dict, now_utc: datetime) -> dict:
    wf = meta['wf']
    freq = meta['freq']
    crons = meta['crons']

    runs = gh_get(
        token,
        f'/repos/{REPO}/actions/workflows/{wf}.yml/runs',
        params={'per_page': 30},
    ).get('workflow_runs', [])

    # 윈도우 정의
    if freq == 'weekly':
        window_start = kst_week_start_utc(now_utc)
    elif freq == 'hourly+':
        window_start = now_utc - timedelta(hours=1, minutes=30)
    else:  # daily / multi-daily
        window_start = kst_today_start_utc(now_utc)

    def parse_dt(s: str) -> datetime:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))

    in_window = [r for r in runs if parse_dt(r['created_at']) >= window_start]
    success_in_window = [r for r in in_window if r.get('conclusion') == 'success']
    inprogress = [r for r in in_window if r.get('status') in ('in_progress', 'queued', 'requested')]

    # 트리거 결정
    decision = 'skip'
    reason = ''

    if success_in_window:
        reason = f'success in window ({len(success_in_window)})'
    elif inprogress:
        reason = f'in_progress ({len(inprogress)})'
    else:
        # 트리거 시점 결정
        if freq == 'hourly+':
            # 1.5h 안에 schedule run 없으면 트리거
            decision = 'dispatch'
            reason = 'no run in last 1.5h'
        else:
            # daily / weekly / multi-daily: 이번 주기에 이미 지나간 cron 중 마지막 + 30분 경과 시 트리거
            last = last_fire_in_period(crons, now_utc, freq)
            if last is None:
                reason = 'no fire in current period yet'
            else:
                threshold = last + timedelta(minutes=30)
                if now_utc >= threshold:
                    decision = 'dispatch'
                    reason = f'last fire {last.strftime("%m/%d %H:%M UTC")} + 30min passed'
                else:
                    reason = f'waiting until {threshold.strftime("%m/%d %H:%M UTC")} (last fire + 30min)'

    return {
        'wf': wf,
        'owner': meta['owner'],
        'freq': freq,
        'decision': decision,
        'reason': reason,
        'in_window': len(in_window),
        'success_in_window': len(success_in_window),
    }


def dispatch(token: str, wf: str) -> tuple[bool, str]:
    code = gh_post(
        token,
        f'/repos/{REPO}/actions/workflows/{wf}.yml/dispatches',
        {'ref': 'main'},
    )
    return (200 <= code < 300, f'HTTP {code}')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='dispatch 없이 결정만 출력')
    ap.add_argument('--filter', default='', help='wf 이름 substring 필터')
    args = ap.parse_args()

    metas = scan_workflows()
    if args.filter:
        metas = [m for m in metas if args.filter in m['wf']]

    token = gh_token()
    now_utc = datetime.now(timezone.utc)
    print(f'now UTC: {now_utc.strftime("%Y-%m-%d %H:%M:%S")}  (KST {now_utc.astimezone(KST).strftime("%H:%M")})')
    print(f'repo: {REPO}  |  workflows: {len(metas)}  |  dry-run: {args.dry_run}')
    print('-' * 90)

    summary = {'dispatch': 0, 'skip': 0, 'failed': 0}
    for m in metas:
        try:
            r = check_workflow(token, m, now_utc)
        except Exception as e:
            print(f'  ERR {m["wf"]}: {e}')
            summary['failed'] += 1
            continue
        flag = '>>>' if r['decision'] == 'dispatch' else '   '
        print(f"  {flag} {r['wf']:35s} [{r['owner']:14s}|{r['freq']:11s}] {r['decision']:8s} | {r['reason']}")
        if r['decision'] == 'dispatch':
            if m['wf'] in SKIP_REQUIRED_INPUT:
                print(f'      ↷ skipped (required input — owner: {r["owner"]})')
                summary['skip'] += 1
                continue
            if args.dry_run:
                summary['dispatch'] += 1
            else:
                ok, msg = dispatch(token, m['wf'])
                if ok:
                    summary['dispatch'] += 1
                    print(f'      → dispatched ({msg})')
                else:
                    summary['failed'] += 1
                    print(f'      ✗ dispatch failed ({msg})')
        else:
            summary['skip'] += 1

    print('-' * 90)
    print(f"dispatch={summary['dispatch']}  skip={summary['skip']}  failed={summary['failed']}")
    return 0 if summary['failed'] == 0 else 2


if __name__ == '__main__':
    sys.exit(main())
