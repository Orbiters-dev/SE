"""
Helium 10 MCP 무인 클라이언트 (server-side, headless).
2026-08-24 확립: authorization_code 1회 로그인으로 refresh_token 확보 후,
refresh_token grant 로 매 실행마다 access_token 무인 갱신 → MCP tool 호출.
(device flow verification 페이지는 Helium10 서버 500 버그로 사용 불가)

크레덴셜:
  .env  또는 환경변수  HELIUM10_CLIENT_ID / HELIUM10_CLIENT_SECRET
                       HELIUM10_TOKEN_ENDPOINT / HELIUM10_MCP_URL (선택, 기본값 내장)
  credentials/helium10_token.json   refresh_token (매 갱신마다 회전 → 재저장)

주요 도구 (marketplace=JP 지원):
  analyze_keywords(keywords[≤200], marketplace)  — Cerebro 배치 검색량 enrichment
  get_keywords_by_keyword(seed_keyword, marketplace) — Magnet 시드 확장
  get_keywords_by_asin(asin, marketplace)        — Cerebro reverse ASIN (오가닉 랭킹 포함)

CLI:
  python tools/helium10_client.py --tool analyze_keywords --marketplace JP --keywords "ストローマグ,1歳 水筒"
  python tools/helium10_client.py --self-test
"""
import os
import sys
import json
import time
import base64
import argparse
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN_FILE = ROOT / "credentials" / "helium10_token.json"
# Cloudflare 가 기본 python-urllib UA 를 차단(Error 1010) → 브라우저 UA 필수. 버전은 롤링 갱신 대상.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
# MCP 스펙 버전 (달력 날짜가 아니라 스펙 릴리스 식별자). 2025-06-18 = 현행 안정 스펙,
# 2026-08-24 실측 initialize/tools/list/tools/call 전부 HTTP 200 확인. 상위호환이라 신버전 나와도 유효.
MCP_PROTOCOL_VERSION = "2025-06-18"


def _load_env():
    """.env 가 있으면 로드(기존 환경변수 우선). 없으면 조용히 통과 —
    환경변수를 직접 주입하는 실행(CI 등)을 허용. 최종 필수값 검증은 Helium10.__init__ 에서."""
    envp = ROOT / ".env"
    if not envp.exists():
        return
    for line in envp.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()
CLIENT_ID = os.environ.get("HELIUM10_CLIENT_ID")
CLIENT_SECRET = os.environ.get("HELIUM10_CLIENT_SECRET")
TOKEN_EP = os.environ.get("HELIUM10_TOKEN_ENDPOINT",
                          "https://members.helium10.com/authhub/api/scenarios/mcp/oauth2/token")
MCP_URL = os.environ.get("HELIUM10_MCP_URL", "https://mcp.helium10.com/mcp")
# OAuth resource(audience) = MCP 리소스 서버 URL. MCP_URL 을 그대로 써서 환경 전환(스테이징 등) 시
# 토큰 audience 와 실제 호출 대상이 어긋나지 않게 한다.
RESOURCE = MCP_URL


class Helium10Error(RuntimeError):
    pass


def _post_form(url, form, auth_b64):
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
        "User-Agent": UA, "Authorization": f"Basic {auth_b64}",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _mcp(payload, access_token, sid=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "User-Agent": UA, "Authorization": f"Bearer {access_token}", "MCP-Protocol-Version": MCP_PROTOCOL_VERSION}
    if sid:
        h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(MCP_URL, data=json.dumps(payload).encode(), method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def _parse_sse(body):
    """SSE(data: ...) 또는 순수 JSON 본문을 dict 로. 실패 시 None (호출부에서 방어)."""
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except Exception:
                pass
    try:
        return json.loads(body)
    except Exception:
        return None


class Helium10:
    def __init__(self):
        missing = [k for k, v in (("HELIUM10_CLIENT_ID", CLIENT_ID),
                                  ("HELIUM10_CLIENT_SECRET", CLIENT_SECRET)) if not v]
        if missing:
            raise Helium10Error(f"{', '.join(missing)} 미설정 (.env 또는 환경변수)")
        self._auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        self._access = None
        self._sid = None

    def _read_refresh(self):
        if not TOKEN_FILE.exists():
            raise Helium10Error(f"refresh token 없음: {TOKEN_FILE} (최초 1회 OAuth 로그인 필요 — "
                                f"tools/helium10_oauth_login.py 참조)")
        try:
            # utf-8-sig: 외부 도구(PowerShell 등)가 붙인 BOM 도 허용
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            raise Helium10Error(f"refresh token 파일 손상 {TOKEN_FILE}: {e}")
        rt = data.get("refresh_token")
        if not rt:
            raise Helium10Error(f"refresh_token 키 없음: {TOKEN_FILE}")
        return rt

    def _save_refresh(self, rt):
        # 디렉토리 보장 + 원자적 쓰기(임시파일 → replace)로 중단 시 토큰 유실 방지
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = TOKEN_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"refresh_token": rt}), encoding="utf-8")
        tmp.replace(TOKEN_FILE)

    def refresh(self):
        st, body = _post_form(TOKEN_EP, {
            "grant_type": "refresh_token", "refresh_token": self._read_refresh(), "resource": RESOURCE,
        }, self._auth)
        if st != 200:
            raise Helium10Error(f"refresh 실패 {st}: {body[:300]}")
        try:
            t = json.loads(body)
        except json.JSONDecodeError:
            raise Helium10Error(f"refresh 응답 JSON 파싱 실패: {body[:200]}")
        access = t.get("access_token")
        if not access:
            raise Helium10Error(f"refresh 응답에 access_token 없음: {body[:200]}")
        self._access = access
        if t.get("refresh_token"):
            self._save_refresh(t["refresh_token"])   # 회전 저장
        return self._access

    def _ensure(self):
        if not self._access:
            self.refresh()
        if not self._sid:
            st, hdrs, body = _mcp({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {},
                "clientInfo": {"name": "orbi-helium10-client", "version": "1.0"}}}, self._access)
            if st != 200:
                raise Helium10Error(f"MCP initialize 실패 {st}: {body[:200]}")
            self._sid = hdrs.get("Mcp-Session-Id") or hdrs.get("mcp-session-id")
            # session id 미제공 서버도 있음 → sid None 이면 헤더 없이 진행(정상 경로)
            _mcp({"jsonrpc": "2.0", "method": "notifications/initialized"}, self._access, self._sid)

    def call(self, tool, arguments, _retry=True):
        self._ensure()
        st, _, body = _mcp({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": tool, "arguments": arguments}}, self._access, self._sid)
        if st in (401, 403) and _retry:   # 토큰 만료 → 1회 재갱신 후 재시도
            self._access = None
            self._sid = None
            return self.call(tool, arguments, _retry=False)
        parsed = _parse_sse(body)
        if parsed is None:
            raise Helium10Error(f"tool {tool} 응답 파싱 실패 (http {st}): {body[:200]}")
        res = parsed.get("result", {})
        if res.get("isError"):
            sc = res.get("structuredContent") or res.get("content")
            raise Helium10Error(f"tool {tool} error: {json.dumps(sc, ensure_ascii=False)[:400]}")
        sc = res.get("structuredContent")
        if sc is not None:
            return sc
        for c in res.get("content", []):
            if c.get("type") == "text":
                try:
                    return json.loads(c["text"])
                except Exception:
                    return c["text"]
        return res

    # ── 편의 래퍼 ──
    def analyze_keywords(self, keywords, marketplace="JP"):
        """≤200개씩 자동 분할. ({keyword: search_volume}, raw_rows) 반환."""
        out = {}
        raw_rows = []
        for i in range(0, len(keywords), 200):
            batch = keywords[i:i + 200]
            data = self.call("analyze_keywords", {"keywords": batch, "marketplace": marketplace})
            rows = _extract_rows(data)
            raw_rows.extend(rows)
            for r in rows:
                kw = _row_kw(r)
                sv = _row_vol(r)
                if kw is not None:
                    out[kw] = sv
            time.sleep(0.5)
        return out, raw_rows


def _extract_rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "keywords", "results", "items", "rows"):
            v = data.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for k2 in ("keywords", "rows", "items", "results"):
                    if isinstance(v.get(k2), list):
                        return v[k2]
    return []


def _row_kw(r):
    if not isinstance(r, dict):
        return None
    return r.get("keyword") or r.get("phrase") or r.get("term") or r.get("keyword_phrase")


def _row_vol(r):
    if not isinstance(r, dict):
        return None
    for k in ("search_volume", "searchVolume", "volume", "search_volume_exact"):
        if r.get(k) is not None:
            return r[k]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", choices=["analyze_keywords", "get_keywords_by_keyword", "get_keywords_by_asin"])
    ap.add_argument("--marketplace", default="JP")
    ap.add_argument("--keywords", help="쉼표구분 (analyze_keywords)")
    ap.add_argument("--seed", help="시드 키워드 (get_keywords_by_keyword)")
    ap.add_argument("--asin", help="ASIN (get_keywords_by_asin)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    h = Helium10()
    if a.self_test:
        vol, rows = h.analyze_keywords(["ストローマグ", "1歳 水筒", "赤ちゃん マグ"], a.marketplace)
        print(json.dumps(vol, ensure_ascii=False, indent=1))
        print("rows returned:", len(rows))
        return
    if a.tool == "analyze_keywords":
        kws = [k.strip() for k in (a.keywords or "").split(",") if k.strip()]
        if not kws:
            print("ERROR: analyze_keywords 는 --keywords (쉼표구분) 필요", file=sys.stderr)
            sys.exit(2)
        vol, rows = h.analyze_keywords(kws, a.marketplace)
        print(json.dumps(vol, ensure_ascii=False, indent=1))
    elif a.tool == "get_keywords_by_keyword":
        if not a.seed:
            print("ERROR: get_keywords_by_keyword 는 --seed 필요", file=sys.stderr)
            sys.exit(2)
        print(json.dumps(h.call("get_keywords_by_keyword",
              {"seed_keyword": a.seed, "marketplace": a.marketplace}), ensure_ascii=False)[:2000])
    elif a.tool == "get_keywords_by_asin":
        if not a.asin:
            print("ERROR: get_keywords_by_asin 는 --asin 필요", file=sys.stderr)
            sys.exit(2)
        print(json.dumps(h.call("get_keywords_by_asin",
              {"asin": a.asin, "marketplace": a.marketplace}), ensure_ascii=False)[:2000])
    else:
        print("ERROR: --tool 지정 (analyze_keywords|get_keywords_by_keyword|get_keywords_by_asin) 또는 --self-test",
              file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    # 리다이렉트/구버전 환경에서 reconfigure 부재 대비
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    main()
