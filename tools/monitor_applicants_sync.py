# -*- coding: utf-8 -*-
"""모니터 응모자 자동 동기화 (Typeform Nqea8Gic → Google Sheet).

매일 1회(GitHub Actions) 실행:
  1) Typeform 전체 응답 재수집 (field-id 매핑)
  2) 시트 기존 핸들과 대조 → 신규만 추출 (yu_baby_mom 제외)
  3) Apify 팔로워(instagram-profile-scraper) + 최고재생(instagram-scraper playCount)
  4) 普段の投稿 키워드 자동 유형분류
  5) 응모일시(submitted_at) 오름차순으로 시트에 append (기존 행 불변)

env:
  TYPEFORM_API_KEY, APIFY_API_TOKEN, GOOGLE_SERVICE_ACCOUNT_PATH,
  MONITOR_SHEET_ID(기본값 내장), MONITOR_FORM_ID(기본 Nqea8Gic)

실패 시 비-0 종료 → CI가 fail 처리(감시견/알림).
"""
from __future__ import annotations
import os, re, sys, json, urllib.request, urllib.error
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
try:
    from env_loader import load_env; load_env()
except Exception:
    pass

FORM_ID = os.getenv("MONITOR_FORM_ID", "Nqea8Gic")
SHEET_ID = os.getenv("MONITOR_SHEET_ID", "10VCIPf6nthLVXbuWHP7Rrf0bhSfYR0z7Y8VKJ1A_eTo")
TYPEFORM_KEY = os.getenv("TYPEFORM_API_KEY")
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
EXCLUDE = {"yu_baby_mom"}  # 세은 기존 제외분

# ── 1. Typeform ─────────────────────────────────────────────
def tf_api(path):
    req = urllib.request.Request("https://api.typeform.com" + path,
                                 headers={"Authorization": "Bearer " + TYPEFORM_KEY})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"[FATAL] Typeform HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"[FATAL] Typeform 연결 실패: {e.reason}")

def collect_fields(fields, out):
    for f in fields:
        out[f["id"]] = f.get("title", "")
        props = f.get("properties", {})
        if "fields" in props:
            collect_fields(props["fields"], out)

def classify_field(t):
    if "Instagram" in t or "ユーザーネーム" in t or "アカウント" in t: return "ig"
    if "名前" in t or "お名前" in t: return "name"
    if "メール" in t or "mail" in t.lower() or "アドレス" in t: return "email"
    if "月齢" in t or "年齢" in t or "お子" in t: return "age"
    if "普段" in t or "投稿" in t or "どんな" in t or "内容" in t: return "post_desc"
    return None

def answer_value(a):
    t = a.get("type"); v = a.get(t)
    if isinstance(v, dict): return v.get("label") or v.get("labels") or ""
    if isinstance(v, list): return ", ".join(str(x) for x in v)
    return v

def clean_handle(h):
    if not h: return ""
    h = str(h).strip()
    m = re.search(r"instagram\.com/([^/?#\s]+)", h)
    if m: return m.group(1).strip("/").lower()
    for p in re.split(r"または|,|/|\s+|・|、", h):
        p = re.sub(r"[^A-Za-z0-9._]", "", p.replace("@", "").replace("＠", ""))
        if re.fullmatch(r"[A-Za-z0-9._]{2,30}", p):
            return p.lower()
    return re.sub(r"[^A-Za-z0-9._]", "", h).lower()

def fetch_responses():
    form = tf_api(f"/forms/{FORM_ID}")
    fmap = {}; collect_fields(form.get("fields", []), fmap)
    items = []; token = None
    while True:
        q = f"/forms/{FORM_ID}/responses?page_size=1000"
        if token: q += f"&before={token}"
        r = tf_api(q); batch = r.get("items", [])
        if not batch: break
        items.extend(batch)
        if len(batch) < 1000: break
        token = batch[-1].get("token")
    recs = []
    for it in items:
        rec = {"submitted": it.get("submitted_at", ""), "name": "", "ig": "",
               "email": "", "age": "", "post_desc": ""}
        for a in it.get("answers", []):
            k = classify_field(fmap.get(a.get("field", {}).get("id"), ""))
            if k:
                val = answer_value(a)
                if val and not rec.get(k): rec[k] = val
        rec["handle"] = clean_handle(rec["ig"])
        recs.append(rec)
    return recs

# ── 2. 유형분류 ──────────────────────────────────────────────
def categorize(desc):
    d = (desc or "").strip()
    if not d: return "未記入"
    if re.search(r"モニター|ＰＲ|PR|案件|使用感|レビュー|ご紹介|アンバサダー|頂いた(商品|お品)", d): return "PR・モニター"
    if re.search(r"おでかけ|お出かけ|旅行|お出掛け", d): return "おでかけ・旅行"
    if re.search(r"フィルム写真|写真風|映像", d): return "写真・映像"
    if re.search(r"コスメ|美容|スキンケア", d): return "美容・コスメ"
    return "育児・日常"

# ── 3. Apify ────────────────────────────────────────────────
def apify_client():
    from apify_client import ApifyClient
    return ApifyClient(APIFY_TOKEN)

def _dataset_id(run):
    # apify-client 버전 호환: 구버전(2.5)은 dict, 신버전(2.6+)은 Run 객체 반환
    if isinstance(run, dict):
        return run["defaultDatasetId"]
    return run.default_dataset_id

def crawl_followers(handles):
    c = apify_client()
    run = c.actor("apify/instagram-profile-scraper").call(run_input={"usernames": handles})
    out = {}
    for it in c.dataset(_dataset_id(run)).iterate_items():
        u = (it.get("username") or "").lower()
        if u: out[u] = it.get("followersCount")
    return out

def crawl_top(handles):
    c = apify_client()
    urls = [f"https://www.instagram.com/{h}/" for h in handles]
    run = c.actor("apify/instagram-scraper").call(run_input={
        "directUrls": urls, "resultsType": "posts", "resultsLimit": 15})
    posts = defaultdict(list)
    for it in c.dataset(_dataset_id(run)).iterate_items():
        u = (it.get("ownerUsername") or "").lower()
        if u: posts[u].append(it)
    def play(p):
        return (p.get("videoPlayCount") or p.get("igPlayCount") or p.get("playCount")
                or p.get("videoViewCount") or 0)
    top = {}
    for h in handles:
        ps = posts.get(h.lower(), [])
        vids = [p for p in ps if play(p) > 0]
        best = max(vids, key=play) if vids else (max(ps, key=lambda p: p.get("likesCount") or 0) if ps else None)
        if best:
            sc = best.get("shortCode") or best.get("id") or ""
            top[h.lower()] = f"https://www.instagram.com/p/{sc}/" if sc else ""
        else:
            top[h.lower()] = ""
    return top

# ── 4. Sheet ────────────────────────────────────────────────
def main():
    for k, v in [("TYPEFORM_API_KEY", TYPEFORM_KEY), ("APIFY_API_TOKEN", APIFY_TOKEN)]:
        if not v: sys.exit(f"[FATAL] env {k} 없음")
    sys.path.insert(0, os.path.dirname(__file__))
    from sheets_utils import get_sheets_client
    gc = get_sheets_client()
    ws = gc.open_by_key(SHEET_ID).sheet1

    # 기존 식별자 = 핸들(B) + 이메일(F) 둘 다. 세은이 시트에서 핸들을 교정해도
    # 이메일이 같으면 신규로 오인해 중복 추가되는 것을 방지.
    existing = {h.strip().lower() for h in ws.col_values(2)[1:] if h.strip()}
    existing_emails = {e.strip().lower() for e in ws.col_values(6)[1:] if e.strip()}
    recs = fetch_responses()
    print(f"[Typeform] 전체 {len(recs)}건 | 시트 기존 핸들 {len(existing)} · 이메일 {len(existing_emails)}")

    seen = set(); seen_emails = set(); new = []
    for r in sorted(recs, key=lambda x: x["submitted"]):
        h = r["handle"]; em = (r.get("email") or "").strip().lower()
        if not h or h in EXCLUDE or h in existing or h in seen: continue
        if em and (em in existing_emails or em in seen_emails): continue
        seen.add(h); seen_emails.add(em); new.append(r)

    if not new:
        print("[OK] 신규 없음 — 종료"); return

    handles = [r["handle"] for r in new]
    print(f"[신규] {len(handles)}명: {', '.join(handles)}")
    foll = crawl_followers(handles)
    top = crawl_top(handles)

    rows = []
    for r in new:
        h = r["handle"]
        rows.append([r.get("name", ""), h, f"https://www.instagram.com/{h}/",
                     foll.get(h, ""), r.get("age", ""), r.get("email", ""),
                     categorize(r.get("post_desc")), top.get(h, "")])
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"[OK] {len(rows)}명 append 완료 (응모일시순)")
    for r in rows:
        print(f"  {r[0]} @{r[1]} f={r[3]} {r[6]} top={'O' if r[7] else '-'}")

if __name__ == "__main__":
    main()
