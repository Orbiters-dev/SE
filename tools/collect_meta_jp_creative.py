"""Collect Meta JP ad creative state → DataKeeper gk_raw_meta_ad_creative.

WONGI 의 raw_meta_ad_creative 크론은 US 계정만 수집한다 (JP 미포함, 2026-07-06 확인).
그래서 JP 계정(act_4117678028561958)의 effective_status / media_id / permalink 를
SE 가 Graph 로 뽑아 WONGI 게이트웨이(/save/, table=raw_meta_ad_creative)로 적재한다.
meta-app 의 OFF/졸업 필터가 이 테이블을 DK 단일소스로 읽는다.

인증: 조회는 META_JP_ACCESS_TOKEN(Graph), 적재는 DK_SE_CRM_TOKEN(Bearer, write:ingest tier).
      Basic(ORBITOOLS_USER/PASS) 은 write tier 에 거부됨.
"""
import os
import sys
import requests

GRAPH = "https://graph.facebook.com/v21.0"
SAVE = "https://orbitools.orbiters.co.kr/api/datakeeper/save/"
TABLE = "raw_meta_ad_creative"


def _env(key: str) -> str:
    v = os.environ.get(key)
    if v:
        return v
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return ""


def fetch_jp_creatives(token: str, acct: str) -> list[dict]:
    """JP 계정 전체 광고의 현재 status + creative 식별자."""
    fields = ("id,campaign_id,adset_id,effective_status,"
              "creative{id,effective_instagram_media_id,instagram_permalink_url,effective_object_story_id}")
    url = f"{GRAPH}/{acct}/ads?fields={fields}&limit=200&access_token={token}"
    rows = []
    while url:
        r = requests.get(url, timeout=40)
        r.raise_for_status()
        d = r.json()
        for a in d.get("data", []):
            cr = a.get("creative", {}) or {}
            rows.append({
                "ad_id": a.get("id", ""),
                "campaign_id": a.get("campaign_id", ""),
                "adset_id": a.get("adset_id", ""),
                "creative_id": cr.get("id", ""),
                "effective_status": a.get("effective_status", ""),
                "effective_instagram_media_id": cr.get("effective_instagram_media_id", ""),
                "instagram_permalink_url": cr.get("instagram_permalink_url", ""),
                "effective_object_story_id": cr.get("effective_object_story_id", ""),
            })
        url = d.get("paging", {}).get("next")
    return rows


def push(rows: list[dict], write_token: str) -> tuple[int, int]:
    created = updated = 0
    headers = {"Authorization": f"Bearer {write_token}"}
    for i in range(0, len(rows), 1000):
        resp = requests.post(SAVE, json={"table": TABLE, "rows": rows[i:i + 1000]},
                             headers=headers, timeout=90)
        resp.raise_for_status()
        res = resp.json()
        created += res.get("created", 0)
        updated += res.get("updated", 0)
        if res.get("errors"):
            print(f"  [WARN] {len(res['errors'])} errors in chunk {i // 1000}")
    return created, updated


def main() -> int:
    token = _env("META_JP_ACCESS_TOKEN")
    acct = _env("META_JP_AD_ACCOUNT_ID")
    write_token = _env("DK_SE_CRM_TOKEN")
    if not token or not acct:
        print("[SKIP] META_JP_ACCESS_TOKEN / META_JP_AD_ACCOUNT_ID 없음")
        return 0
    if not write_token:
        print("[ERROR] DK_SE_CRM_TOKEN 없음 (write:ingest tier 필요)")
        return 1
    if not acct.startswith("act_"):
        acct = f"act_{acct}"

    rows = fetch_jp_creatives(token, acct)
    import collections
    dist = dict(collections.Counter(r["effective_status"] for r in rows))
    print(f"[Meta JP Creative] fetched {len(rows)} ads | status: {dist}")
    if not rows:
        return 0
    created, updated = push(rows, write_token)
    print(f"[Meta JP Creative] pushed → +{created} new, ~{updated} updated (table={TABLE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
