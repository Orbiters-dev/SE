# -*- coding: utf-8 -*-
"""WL D+3 감시견 — 3소스 원장(DK coauthor ∪ 투고완료 폼 ∪ IG DM 투고보고) 합집합을
Graph 실시간 광고 커버(광고명 CT-###)와 대조해, D+3 도달했는데 광고 미세팅/미부착인 게시물을 알림.

배경: 2026-08-31 riono_nichijou 누락 사고 (DK 단독 원장 의존 — 세은 지적).
      memory/reference_meta_wl_branded_ad_api_creation.md · mistakes_20260831_wl_ledger_missed_riono.md

read-only (광고 계정 쓰기 없음). 발견 0건이면 침묵. 발견 시 Teams 웹훅 + Gmail 이중 알림
(웹훅 단독 신뢰 불가 전례 8/26). 가용 소스 2개 미만 또는 알림 전 채널 실패 시 exit 1.

사용: python tools/wl_d3_watchdog.py [--dry-run]   (--dry-run = 알림 미발송, 판정만 출력)
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))

ACT = "act_4117678028561958"
# 전 스택(8/27 WL API 생성·8/31 세팅)이 v21.0에서 검증됨. Graph 버전 수명 ~2년(v21.0=2024-10 출시)
# → 2026-10 전후 만료 예상. 만료 에러 시 이 상수만 상향 후 재검증.
GRAPH_VER = "v21.0"
FORM_SHEET_ID = "1Gd8JrWm-nOzscmL2tPLTW23EoC_QGtA07C0xMY6Jr8E"
FORM_TAB_ID = 1196213398          # 투고완료 탭
TODAY = date.today()
D3_CUT = (TODAY - timedelta(days=3)).isoformat()   # post_date <= 이 값 = D+3 도달 (게이트: post_date ≤ 당일-3)
WINDOW = (TODAY - timedelta(days=28)).isoformat()  # 관찰 창 (그 이전 백로그는 별도 정책)
DM_CONV_CUTOFF = (TODAY - timedelta(days=10)).isoformat()

# 전체 실행 데드라인 — ledger_dm 이 IG DM 레이트리밋에 재시도 백오프가 누적되면
# 수 분씩 블록돼 JPDash 체인 전체를 막는 사고가 있었다(hang 16분). main 에서 설정.
_DEADLINE = None


def _over_deadline():
    return _DEADLINE is not None and time.monotonic() > _DEADLINE


SC_RE = re.compile(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)")
DATE_YMD = re.compile(r"(20\d{2})/(\d{1,2})/(\d{1,2})")   # 2026/08/25 (폼 투고일)
DATE_MDY = re.compile(r"(\d{1,2})/(\d{1,2})/(20\d{2})")   # 8/26/2026 (폼 제출 타임스탬프)
# 광고명 7토큰 규칙 (reference_adname_framework_v1) — 크리에이터·CT 토큰 앵커
# CT 값 = 숫자(content_posts.id 정본) 또는 shortcode(미적재 임시 — feedback_no_ctnew_placeholder)
ADNAME_RE = re.compile(r"Y\d+M\d+D\d+_Grosmimi_[A-Z]+_WL-[GP]_(.+?)_(?:B0[A-Z0-9]{8}|GENERAL)_CT-([\w-]+)")

_ENV_CACHE = None


def envget(key):
    """개별 키 부재 = None (호출부가 FAIL 처리). .env 파일 자체를 못 읽으면 즉시 예외 — 무음 진행 금지."""
    global _ENV_CACHE
    if _ENV_CACHE is None:
        env_path = os.path.join(BASE, ".env")
        try:
            text = io.open(env_path, encoding="utf-8").read()
        except OSError as e:
            raise RuntimeError(f".env 읽기 실패({env_path}) — 감시견 실행 불가: {e}") from e
        _ENV_CACHE = dict(re.findall(r"^([A-Z0-9_]+)=(.+)$", text, re.M))
    val = _ENV_CACHE.get(key)
    return val.strip().strip('"') if val else None


def hnorm(handle):
    """핸들 정규화 — 밑줄/점/@/대소문자 차이 무시 비교용"""
    return re.sub(r"[^a-z0-9]", "", (handle or "").lower())


def http_json(url, tries=4):
    """백오프 재시도 — 429/500 및 일시적(is_transient/한도 code 4·17·32) 403만. 권한 403은 즉시 raise."""
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if i >= tries - 1:
                raise
            if e.code in (429, 500):
                time.sleep(15 * (i + 1))
                continue
            if e.code == 403:
                body = e.read().decode(errors="replace")
                try:
                    err = json.loads(body).get("error", {})
                except ValueError:
                    err = {}
                if err.get("is_transient") or err.get("code") in (4, 17, 32):
                    time.sleep(15 * (i + 1))
                    continue
                raise urllib.error.HTTPError(url, e.code, body[:200], e.headers, None)
            raise


def graph_pages(token, path, **params):
    """graph.facebook.com edge 전 페이지 순회"""
    params["access_token"] = token
    url = f"https://graph.facebook.com/{GRAPH_VER}/{path}?" + urllib.parse.urlencode(params)
    while url:
        if _over_deadline():
            print(f"WARN: 데드라인 초과 — {path} 순회 중단(부분)", file=sys.stderr)
            break
        res = http_json(url)
        for row in res.get("data", []):
            yield row
        url = (res.get("paging") or {}).get("next")


def parse_post_date(text):
    """행 텍스트에서 게시일 추정 (YYYY/M/D = 폼 투고일 우선, 없으면 M/D/YYYY 제출 타임스탬프)"""
    m = DATE_YMD.search(text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = DATE_MDY.search(text)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


def covered_sets(token):
    """Graph 실시간 커버 상태 1회 스캔.

    반환 dict:
      ad_ct          광고명 CT-숫자 (정본 조인키 — creative permalink는 광고 복사본이라 원본 sc와 다름)
      ad_sc          creative permalink shortcode ∪ 광고명 CT-shortcode (API 생성분·임시 CT — 보조키)
      ad_handles_all 광고 있는 크리에이터 핸들 전체 — URL 없는 DM 보고(dm:핸들 키) 판정 전용
      adset_by_ct    CT-숫자 → adset 정보(광고 부착 여부 포함. 빈 adset = 세팅 미완)
      adset_by_sc    CT-shortcode(미적재 임시 CT) → adset 정보
      adset_by_h     핸들 → adset 정보 (CT 조인 실패 시 최후 fallback)
    """
    cov = {"ad_ct": set(), "ad_sc": set(), "ad_handles_all": set(),
           "adset_by_ct": {}, "adset_by_sc": {}, "adset_by_h": {}}
    adsets_with_ads = set()
    for a in graph_pages(token, f"{ACT}/ads",
                         fields="name,adset_id,campaign{name},creative{instagram_permalink_url}", limit="100"):
        if "WL" not in ((a.get("campaign") or {}).get("name", "")):
            continue
        m = ADNAME_RE.search(a.get("name", ""))
        if m:
            cov["ad_handles_all"].add(hnorm(m.group(1)))
            if m.group(2).isdigit():
                cov["ad_ct"].add(int(m.group(2)))
            else:
                cov["ad_sc"].add(m.group(2))  # 임시 CT-shortcode
        m2 = SC_RE.search(((a.get("creative") or {}).get("instagram_permalink_url")) or "")
        if m2:
            cov["ad_sc"].add(m2.group(1))
        adsets_with_ads.add(a.get("adset_id"))
    for s in graph_pages(token, f"{ACT}/adsets", fields="id,name,campaign{name}", limit="100"):
        if "WL" not in ((s.get("campaign") or {}).get("name", "")):
            continue
        m = ADNAME_RE.search(s.get("name", ""))
        if not m:
            continue
        info = {"has_ads": s["id"] in adsets_with_ads, "name": s.get("name", "")}
        cov["adset_by_h"].setdefault(hnorm(m.group(1)), info)
        if m.group(2).isdigit():
            cov["adset_by_ct"][int(m.group(2))] = info
        else:
            cov["adset_by_sc"][m.group(2)] = info
    return cov


def ledger_dk():
    """DK content_posts — JP 코라보(coauthor grosmimi) 또는 캡션 언급, 관찰 창 내.
    주의: DK date_from은 수집일 기준이라 post_date는 로컬에서 재필터."""
    from data_keeper_client import DataKeeper
    out = {}
    for r in DataKeeper().get("content_posts", date_from=WINDOW):
        if (r.get("region") or "").lower() != "jp":
            continue
        # 자사(owned) 게시물 제외 — @grosmimi_japan 은 IHV 파이프라인(ih_auto_upload)이
        # D+3 자동집행 + 자체 Teams/Gmail 알림을 담당. WL(인플루언서 화이트리스팅) 감시 대상 아님.
        # IH 캠페인은 covered_sets("WL" 캠페인 한정)에 안 잡혀, 이대로 두면 이미 ACTIVE 인
        # 자사 IH 광고가 매일 "미세팅"으로 오탐됨 (2026-09-28 세은 지적, 5건 유령).
        # IH 광고 permalink 는 FB 복사본 shortcode 라 원본 sc 로 커버 매칭도 불가.
        # reference_review_queue_partnered_and_metrics_cap (심사 큐도 owned 제외 원칙).
        if hnorm(r.get("username")) == "grosmimijapan":
            continue
        pd = str(r.get("post_date") or "")
        if pd < WINDOW:
            continue
        partner_blob = (str(r.get("coauthor_usernames") or "") + str(r.get("partner_brand") or "")).lower()
        caption_blob = str(r.get("caption") or "").lower()
        is_collab = (r.get("is_partner") and "grosmimi" in partner_blob) \
            or "grosmimi" in caption_blob or "グロミミ" in caption_blob
        if not is_collab:
            continue
        m = SC_RE.search(r.get("url") or "")
        if m:
            out[m.group(1)] = {"src": "DK", "u": r.get("username"), "d": pd, "ct": r.get("id")}
    return out


def ledger_form():
    """투고완료 폼 — 인플루언서 본인 제출 투고 URL (최상급 원장). u = 성명(핸들 아님)."""
    from google.oauth2.service_account import Credentials
    import gspread
    creds = Credentials.from_service_account_file(
        os.path.join(BASE, "credentials", "google_service_account.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    ws = next((w for w in gspread.authorize(creds).open_by_key(FORM_SHEET_ID).worksheets()
               if w.id == FORM_TAB_ID), None)
    if ws is None:
        raise ValueError(f"투고완료 탭(id={FORM_TAB_ID}) 없음 — 시트 구조 변경 여부 확인 필요")
    out = {}
    for row in ws.get_all_values()[1:]:
        blob = " ".join(row)
        for sc in SC_RE.findall(blob):
            out[sc] = {"src": "폼", "u": (row[1] if len(row) > 1 else "")[:20],
                       "d": parse_post_date(blob), "ct": None}
    return out


def ledger_dm(token):
    """IG DM — 최근 10일 갱신 대화에서 인플루언서 측 투고 보고.
    d = DM 보고일(게시일 상한 근사 — 보통 게시 당일~익일 보고라 판정이 최대 하루 늦을 수 있음)."""
    host = f"https://graph.instagram.com/{GRAPH_VER}"
    # 투고 "보고" 동사 필수 — URL 존재만으로 판정하면 타 게시물 인용(질문/레퍼런스)이 오탐됨 (8/31 dry-run 실측)
    report_kw = ("投稿しました", "投稿いたしました", "投稿させていただきました", "アップしました",
                 "アップいたしました", "公開しました", "投稿完了")
    convs = []
    url = (f"{host}/me/conversations?" + urllib.parse.urlencode(
        {"fields": "id,participants,updated_time", "limit": "50", "access_token": token}))
    while url:
        if _over_deadline():
            print("WARN: 데드라인 초과 — 대화 목록 순회 중단(부분)", file=sys.stderr)
            break
        res = http_json(url)
        page = res.get("data", [])
        convs.extend(c for c in page if (c.get("updated_time") or "") >= DM_CONV_CUTOFF)
        if page and (page[-1].get("updated_time") or "") < DM_CONV_CUTOFF:
            break  # conversations edge는 updated_time 내림차순
        url = (res.get("paging") or {}).get("next")
    out = {}
    skipped = 0
    for c in convs:
        if _over_deadline():
            print(f"WARN: 데드라인 초과 — DM 메시지 조회 중단(부분, {len(out)}건까지)", file=sys.stderr)
            break
        users = [p.get("username") for p in (c.get("participants") or {}).get("data", [])
                 if p.get("username") != "grosmimi_japan"]
        if not users:
            continue
        user = users[0]  # 브랜드 DM은 1:1 스레드 — 그룹 DM은 운영상 없음
        try:
            res = http_json(f"{host}/{c['id']}/messages?" + urllib.parse.urlencode(
                {"fields": "message,from,created_time", "limit": "30", "access_token": token}))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            skipped += 1
            continue
        for m in res.get("data", []):
            text = m.get("message") or ""
            if ((m.get("from") or {}).get("username") == user
                    and (m.get("created_time") or "")[:10] >= WINDOW
                    and any(k in text for k in report_kw)):
                d = (m.get("created_time") or "")[:10]
                for key in (SC_RE.findall(text) or [f"dm:{user}"]):
                    out.setdefault(key, {"src": "DM", "u": user, "d": d, "ct": None})
                break
    if skipped:
        print(f"WARN: DM 대화 {skipped}건 조회 실패(레이트리밋/네트워크) — 부분 커버", file=sys.stderr)
    return out


def collect_ledger(igdm_token):
    """3소스 합집합. 먼저 잡힌 소스 우선 (DK가 CT id 보유). 반환: (원장, 성공한 소스 목록)"""
    ledger, sources_ok = {}, []
    sources = (("DK", ledger_dk), ("폼", ledger_form),
               ("DM", lambda: ledger_dm(igdm_token) if igdm_token else {}))
    for name, fn in sources:
        try:
            for k, v in fn().items():
                ledger.setdefault(k, v)
            sources_ok.append(name)
        except Exception as e:
            print(f"WARN: {name} 소스 실패 — {str(e)[:120]}")
    return ledger, sources_ok


def judge(ledger, cov):
    """원장 각 게시물 → 미세팅/미부착 판정 (D+3 도달분만. 날짜 미상 = 도달로 간주, 보수적).
    커버 판정 우선순위: CT-숫자 → creative sc → 핸들 fallback(숫자 CT 없는 자산 한정)."""
    findings = []
    for key, info in sorted(ledger.items(), key=lambda kv: kv[1]["d"]):
        if info["d"] and info["d"] > D3_CUT:
            continue
        sc = None if key.startswith("dm:") else key
        ct = info.get("ct")
        hn = hnorm(info.get("u"))
        if (ct and ct in cov["ad_ct"]) or (sc and sc in cov["ad_sc"]):
            continue
        if sc is None and hn and hn in cov["ad_handles_all"]:
            continue  # URL 없는 DM 보고 — 해당 크리에이터 광고가 하나라도 있으면 커버로 간주 (핸들 단위 판정)
        adset = (cov["adset_by_ct"].get(ct) if ct else None) \
            or (cov["adset_by_sc"].get(sc) if sc else None) \
            or (cov["adset_by_h"].get(hn) if hn else None)
        if adset:
            if adset["has_ads"]:
                continue
            findings.append(f"광고미부착 {adset['name'][:70]} @{info['u']} 게시 {info['d']} [{info['src']}]")
        else:
            findings.append(f"미세팅 @{info['u']} 게시 {info['d'] or '날짜미상'} sc={sc or '-'} [{info['src']}]")
    return findings


def notify(text, subject="[WL감시견] D+3 미세팅 감지"):
    """Teams + Gmail 이중 발송. 실제 성공 확인된 채널명만 반환 (도달까지가 완료 — 8/26 교훈).
    subject = Gmail 제목(호출자별 상이. 기본=감시견. auto_upload 등은 자체 제목 전달)."""
    ok = []
    hook = envget("TEAMS_WEBHOOK_URL_SEEUN")
    if hook:
        try:
            body = json.dumps({"text": text}).encode()
            req = urllib.request.Request(hook, data=body, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=30)
            ok.append("teams")
        except Exception as e:
            print(f"WARN: Teams 발송 실패 — {str(e)[:100]}")
    try:
        env2 = dict(os.environ,
                    GMAIL_OAUTH_CREDENTIALS_PATH=os.path.join(BASE, "credentials", "gmail_oauth_credentials.json"),
                    GMAIL_TOKEN_PATH=os.path.join(BASE, "credentials", "gmail_token.json"))
        proc = subprocess.run([sys.executable, os.path.join(BASE, "tools", "send_gmail.py"),
                               "--to", "se.heo@orbiters.co.kr",
                               "--subject", subject,
                               "--body", "<pre>" + text + "</pre>"],
                              env=env2, timeout=120, capture_output=True)
        if proc.returncode == 0:
            ok.append("gmail")
        else:
            print(f"WARN: Gmail 발송 실패 exit {proc.returncode} — {proc.stderr.decode(errors='replace')[:120]}")
    except Exception as e:
        print(f"WARN: Gmail 발송 실패 — {str(e)[:100]}")
    return ok


def main():
    ap = argparse.ArgumentParser(description="WL D+3 미세팅 감시견")
    ap.add_argument("--dry-run", action="store_true", help="알림 미발송, 판정만 출력")
    ap.add_argument("--max-seconds", type=int, default=300,
                    help="전체 실행 상한(초). 초과 시 부분 원장으로 판정 — 체인 블록 방지(기본 300)")
    args = ap.parse_args()

    global _DEADLINE
    _DEADLINE = time.monotonic() + args.max_seconds

    meta_token = envget("META_JP_ACCESS_TOKEN")
    if not meta_token:
        print("FAIL: META_JP_ACCESS_TOKEN 없음 — 커버 판정 불가")
        return 1
    cov = covered_sets(meta_token)
    ledger, sources_ok = collect_ledger(envget("IG_DM_ACCESS_TOKEN"))
    findings = judge(ledger, cov)

    print(f"{TODAY} 원장 {len(ledger)}건 (소스 {len(sources_ok)}/3: {','.join(sources_ok)}) "
          f"/ D+3 미세팅·미부착 {len(findings)}건")
    for f in findings:
        print(" ", f)

    if len(sources_ok) < 2:
        print("FAIL: 가용 소스 2개 미만 — 판정 신뢰 불가")
        return 1
    if findings and not args.dry_run:
        sent = notify(f"[WL감시견 {TODAY}] D+3 도달·광고 미세팅 {len(findings)}건:\n" + "\n".join(findings))
        print("알림 발송:", ",".join(sent) if sent else "전 채널 실패")
        if not sent:
            return 1  # 알림 도달 실패 = 감시 실패
    return 0


if __name__ == "__main__":
    sys.exit(main())
