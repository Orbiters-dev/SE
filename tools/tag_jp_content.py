"""
JP 콘텐츠 요소별 자동 태깅 (키메세지 S##_F## + Hook v2 HV-##/HC-## 2축)
=========================================================
DK content_posts(JP) → KM SSOT + WL 훅 taxonomy v2(고정 라벨) → LLM constrained-label 분류
→ 시트 'Content Tags (auto)' 탭 저장 (post_id 키 + taxonomy 버전 스탬프).

훅 v2 (2026-07-09~): 비주얼훅 HV-## / 캡션훅 HC-## 2축 분리 태깅 (코드 목록 = 시트가 SSOT).
hook_primary = 두 축 중 지배 훅 1개 (meta-app 단일 코드 소비 호환).

유의미성 분석(group-by)의 전제 = 요소별 범주 태그. 합산 스코어는 나중.

Usage:
    # 로드·필터·라벨집합만 확인 (LLM/쓰기 X)
    PYTHONIOENCODING=utf-8 python tools/tag_jp_content.py --dry-run

    # 소량 태깅 → 로컬 CSV + 콘솔 (시트 미기록)
    PYTHONIOENCODING=utf-8 python tools/tag_jp_content.py --limit 5

    # 전체 태깅 + 시트 탭 write
    PYTHONIOENCODING=utf-8 python tools/tag_jp_content.py --write-sheet

    # 신규분만 (JP 탭에 태그 없는 shortcode) 태깅 + 앱 탭 편입 — 데일리 자동잡용
    PYTHONIOENCODING=utf-8 python tools/tag_jp_content.py --incremental --write-sheet --sync-jp

데이터 근거:
    - JP 식별 = content_posts.region == 'jp' (+ 노이즈필터: 일본어비율≥10% & 제품명사)
    - 입력 = caption(일본어 원문, 정확) 주 + whisper.key_message/hook_text_3s 보조
      (transcript 는 영어 자동번역이라 분류 근거로 부정확 → 제외)
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DIR = Path(__file__).resolve().parent
ROOT = DIR.parent
sys.path.insert(0, str(DIR))

try:
    from env_loader import load_env
    load_env()
except Exception:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass

try:
    from data_keeper_client import DataKeeper
    from sheets_utils import get_sheets_client, safe_range
except ImportError as e:  # tools/ 밖 실행·의존성 누락 시 원인 즉시 안내
    sys.exit(f"[FATAL] 필수 모듈 로드 실패: {e} — SE 루트에서 실행 + tools/ 경로 확인")

# ── Config ──
TAXONOMY_SHEET_ID = "1HnouC4gMRVTcGwGeInJlGJl_W7eNgI_4m63ZDSxzfZY"  # Inhouse Content Tracker
KM_TAB = "KM SSOT_GR"  # 시트 브랜드별 재편(2026-07-27 실측): 구 'KM SSOT (JIAH)_v2' 폐기, GR=Grosmimi 탭이 실사용 코드 45/45 커버
KM_GID = 44578416  # 탭 개명 내성 — gid 우선, KM_TAB 제목은 폴백
HOOK_GID = 1298743912  # WL 훅 taxonomy v2 (HV/HC) — 구 'Hook Type' 탭(H##) 폐기
OUTPUT_TAB = "Content Tags (auto)"
TAXONOMY_VER = "KM_SSOT_v2+HOOK_v2"

# meta-app 소비 탭 (앱 자동 태그 표시 + 요소별 티어 집계 소스). --sync-jp 로 자동 컬럼 upsert.
TAG_SHEET_ID = "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
TAG_TAB = "Content Tags (JP)"
DESC_CAP = 55  # 라벨 설명 길이 (setup_tag_dropdowns 컨벤션)

# repo 표준 모델 — tools/plan_weekly_content.py:44 와 동일 ID (2026 환경 검증됨).
# env 로 override 가능. 폐기 ID(claude-sonnet-4-2025xxxx) 사용 금지.
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
BATCH_SIZE = 5

# 노이즈 필터 (project_meta_jp_content_tagging.md 룰 재사용)
JP_CHAR = re.compile(r"[぀-ヿ一-龯]")
PRODUCT_NOUN = re.compile(r"(マグ|ストロー|PPSU|ステンレス|ボトル|哺乳|コップ|ニップル|グロミミ|grosmimi)", re.I)

KM_CODE_RE = re.compile(r"^(?:[A-Z]{2,3}_)?S\d{2}_F\d{2}$")  # 26-07 시트 개편: GR_/NAE_ 등 브랜드 프리픽스 허용
KM_BRAND_PREFIX_RE = re.compile(r"^[A-Z]{2,3}_(?=S\d{2}_F\d{2}$)")  # 맵 키는 프리픽스 제거 (기존 태그 S##_F## 호환)
HOOK_CODE_RE = re.compile(r"^H[VC]-\d{2}$")

# hook_visual/hook_caption = v2 2축 (기존 컬럼 뒤에 추가 — 구 행 열 정렬 보존)
OUTPUT_COLS = [
    "post_id", "ct_pk", "shortcode", "username", "url", "region", "content_type",
    "km_primary", "km_primary_desc", "km_sub", "hook_primary", "hook_primary_name",
    "confidence", "evidence", "taxonomy_ver", "tagged_at",
    "hook_visual", "hook_visual_name", "hook_caption", "hook_caption_name",
]


# ── Taxonomy 로드 ──

def _km_worksheet(sh):
    """KM SSOT 탭 해석 — gid 우선(개명 내성), 제목 폴백.

    2026-07-27: 'KM SSOT (JIAH)_v2' 개명으로 택소노미 로드가 통째로 죽은 사고 재발 방지.
    """
    tabs = sh.worksheets()
    ws = next((w for w in tabs if w.id == KM_GID), None)
    if ws is None:
        ws = next((w for w in tabs if w.title == KM_TAB), None)
    if ws is None:
        raise RuntimeError(
            f"KM SSOT 탭 없음 (gid {KM_GID} / 제목 {KM_TAB!r} 둘 다 미존재) — "
            f"시트 탭 목록 확인: {[w.title for w in tabs]}")
    return ws


def load_taxonomy() -> tuple[dict, dict, dict]:
    """시트에서 KM SSOT(S##_F##) + 훅 v2(HV-##/HC-##) 라벨집합을 읽는다.

    Returns: (km_map {code: desc}, hook_map {code: 훅이름KO}, hook_desc {code: 설명})
    각 행을 regex 스캔 → 컬럼 이동에도 견고.
    훅 v2 행: Code | 그룹 | 훅 이름(KO) | Name(EN) | 설명 … (코드 셀 기준 상대 오프셋)
    """
    gc = get_sheets_client()
    sh = gc.open_by_key(TAXONOMY_SHEET_ID)

    def scan(ws, code_re: re.Pattern) -> dict:
        out = {}
        for row in ws.get_all_values():
            cells = [c.strip() for c in row]
            for i, c in enumerate(cells):
                if code_re.match(c):
                    # 코드 다음의 첫 비어있지 않은 셀 = 설명/이름
                    desc = next((cells[j] for j in range(i + 1, len(cells)) if cells[j]), "")
                    key = KM_BRAND_PREFIX_RE.sub("", c)  # GR_S01_F01 → S01_F01 (태그 코드 호환)
                    if key not in out:
                        out[key] = desc
                    break
        return out

    km = scan(_km_worksheet(sh), KM_CODE_RE)

    hook_map, hook_desc = {}, {}
    try:
        ws = sh.get_worksheet_by_id(HOOK_GID)  # gspread ≥5.6 (7/9 실행 검증)
    except AttributeError:  # 구버전 gspread fallback — gid 로 직접 매칭
        ws = next((w for w in sh.worksheets() if w.id == HOOK_GID), None)
        if ws is None:
            raise RuntimeError(f"HOOK_GID {HOOK_GID} 탭 없음 — 시트 확인")
    for row in ws.get_all_values():
        cells = [c.strip() for c in row]
        for i, c in enumerate(cells):
            if HOOK_CODE_RE.match(c):
                if c not in hook_map:
                    name = cells[i + 2] if len(cells) > i + 2 and cells[i + 2] else \
                        next((cells[j] for j in range(i + 1, len(cells)) if cells[j]), "")
                    hook_map[c] = name
                    hook_desc[c] = cells[i + 4] if len(cells) > i + 4 else ""
                break

    if not km or not hook_map:  # 시트 포맷 변경/컬럼 이동 시 조용히 빈 맵 반환 방지
        raise RuntimeError(f"택소노미 로드 실패: KM {len(km)}개 / Hook {len(hook_map)}개 — 시트 포맷 확인")
    return km, hook_map, hook_desc


# ── JP 콘텐츠 로드 + 노이즈 필터 ──

def _text_of(row: dict) -> str:
    return ((row.get("caption") or "") + " " + (row.get("text") or "")).strip()


def is_noise(row: dict) -> bool:
    """일본어비율<10% 또는 제품명사 없음 → 제외 후보."""
    cap = _text_of(row)
    if not cap:
        return True
    jp = sum(1 for ch in cap if JP_CHAR.match(ch))
    if jp / max(len(cap), 1) < 0.10:
        return True
    if not PRODUCT_NOUN.search(cap):
        return True
    return False


DK_ROW_CAP = 10000  # DK /query/ 요청당 행 캡 (2026-07-20 실측)


def load_jp_content(limit: int = 0) -> list[dict]:
    """DK content_posts(최근 365d, grosmimi) → JP 필터 + 노이즈 제거, 최신순.

    limit 인자 = 최종 반환 상한 (0=무제한). DK 쿼리는 요청당 DK_ROW_CAP 행 캡이 있어
    캡 도달 시에만 날짜 창 이분할로 재수집 (silent truncation 방지 — 평시엔 단일 쿼리).
    """
    dk = DataKeeper()
    today = datetime.now(timezone.utc).date()

    def fetch(d_from, d_to, depth: int = 0) -> list[dict]:
        rows = dk.get("content_posts", date_from=d_from.isoformat(),
                      date_to=d_to.isoformat(), brand="grosmimi", limit=DK_ROW_CAP)
        if len(rows) < DK_ROW_CAP:
            return rows
        if depth >= 4 or d_from >= d_to:  # 분할 한계 (하루 창에서도 캡이면 더 못 쪼갬)
            print(f"    ⚠️ content_posts {d_from}~{d_to} 창 {DK_ROW_CAP}행 캡 도달 — 초과분 누락 가능")
            return rows
        mid = d_from + (d_to - d_from) // 2
        return fetch(d_from, mid, depth + 1) + fetch(mid + timedelta(days=1), d_to, depth + 1)

    raw = fetch(today - timedelta(days=365), today)
    seen, rows = set(), []
    for r in raw:  # 분할 경계/서버 필터 무시 대비 dedup
        key = r.get("post_id") or r.get("shortcode") \
            or json.dumps(r, sort_keys=True, ensure_ascii=False, default=str)
        if key not in seen:
            seen.add(key)
            rows.append(r)
    jp = [r for r in rows if (r.get("region") or "").lower() == "jp"]
    clean = [r for r in jp if not is_noise(r)]
    clean.sort(key=lambda r: r.get("post_date") or "", reverse=True)
    if limit:
        clean = clean[:limit]
    return clean


def _jp_tab_table() -> tuple[list[str], list[dict]]:
    """Content Tags (JP) 탭 → (헤더, 행 dict 목록). 행 순서 보존.

    시트가 완전히 비어 있으면 ([], []) — 호출자가 헤더 유무로 검증 분기.
    행 dict 접근은 .get() 전제 (짧은 행은 빈 문자열로 패딩됨).
    """
    gc = get_sheets_client()
    ws = gc.open_by_key(TAG_SHEET_ID).worksheet(TAG_TAB)
    vals = ws.get_all_values()
    if not vals:
        return [], []
    hdr = [h.strip() for h in vals[0]]
    recs = [{h: (r[i] if i < len(r) else "").strip() for i, h in enumerate(hdr)}
            for r in vals[1:]]
    return hdr, recs


def load_tagged_shortcodes() -> set[str]:
    """Content Tags (JP) 탭에서 이미 태그가 있는 shortcode 집합.

    '태그 있음' = 자동 km_primary 또는 수동 km_manual 이 채워진 행.
    빈태그 행(LLM 실패분)은 포함 안 됨 → --incremental 다음 실행에서 재시도.
    헤더가 존재하는데 필수 컬럼이 없으면 데이터 행 수와 무관하게 즉시 중단
    (잘못된 탭 구조로 전량 재태깅되는 사고 방지).
    """
    hdr, recs = _jp_tab_table()
    if hdr and not {"shortcode", "km_primary", "km_manual"} <= set(hdr):
        raise RuntimeError("JP 탭 헤더 누락 (shortcode/km_primary/km_manual) — 증분 기준 판단 불가, 중단")
    return {r.get("shortcode", "") for r in recs
            if r.get("shortcode") and (r.get("km_primary") or r.get("km_manual"))}


# ── 사람 교정 few-shot (점진 개선 루프, 2026-07-13) ──

CORR_MAX = 12
_KM_PAT = r"S\d{2}_F\d{2}"
_HOOK_PAT = r"H[VC]-\d{2}"  # 교정 예시는 v2 코드만 (구 H## 자동값은 예시 가치 낮음)


def build_corrections_block(content_by_sc: dict) -> str:
    """앱에서 사람이 고친 태그(수동 선택·자동 기각) → LLM few-shot 블록.

    자동(km_primary/hook_primary)과 수동(km_manual/hook_manual)이 다른 행 =
    사람 교정 사례. 캡션 신호와 (오답→정답) 쌍을 프롬프트에 주입해 같은
    오분류를 반복하지 않게 한다. km_manual "-" = 자동 기각(정답 미지정) → 부정 예시.
    시트 fetch 실패는 태깅 자체를 막지 않는다 (빈 블록 반환).
    """
    try:
        _, recs = _jp_tab_table()
    except Exception as e:
        print(f"    ⚠️ 교정 사례 로드 실패 (few-shot 없이 진행): {e}")
        return ""

    def code_of(v: str, pat: str) -> str:
        m = re.search(pat, v or "")
        return m.group(0) if m else ""

    def codes_of(v: str, pat: str) -> list[str]:
        return [c for c in (code_of(p.strip(), pat) for p in (v or "").split(",")) if c]

    examples = []
    for rec in reversed(recs):  # 아래쪽 = 최근 추가분 → 최신 교정 우선
        if len(examples) >= CORR_MAX:
            break
        sc = rec.get("shortcode", "")
        row = content_by_sc.get(sc)
        if not row:
            continue
        cap = _text_of(row)[:180]
        if not cap:
            continue
        auto_km = code_of(rec.get("km_primary", ""), _KM_PAT)
        km_manual_raw = rec.get("km_manual", "")
        manual_km = codes_of(km_manual_raw, _KM_PAT)
        auto_hook = code_of(rec.get("hook_primary", ""), _HOOK_PAT)
        manual_hook = codes_of(rec.get("hook_manual", ""), _HOOK_PAT)

        lines = []
        if km_manual_raw == "-" and auto_km:
            lines.append(f"❌ 自動 km={auto_km} は誤り (人間が棄却。正解コードは未指定 — このようなcaptionに{auto_km}を付けない)")
        elif manual_km and set(manual_km) != {auto_km}:
            lines.append(f"❌ 自動 km={auto_km or 'なし'} → ✅ 人間の正解 km={','.join(manual_km)}")
        if manual_hook and auto_hook and auto_hook not in manual_hook:
            lines.append(f"❌ 自動 hook={auto_hook} → ✅ 人間の正解 hook={','.join(manual_hook)}")
        if not lines:
            continue
        examples.append(f"[例{len(examples)+1}] caption: 「{cap}」\n  " + "\n  ".join(lines))

    if not examples:
        return ""
    return (
        "\n## 人間のレビュアーによる過去の修正例 — 同じ誤分類を絶対に繰り返さないこと。"
        "修正のパターン(なぜ間違いだったか)を推論し、下の分類にも適用する:\n"
        + "\n".join(examples) + "\n"
    )


# ── 콘텐츠 → LLM 입력 ──

def _shortcode(url: str) -> str:
    if not url:
        return ""
    m = re.search(r"/(?:p|reel|reels)/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/video/(\d+)", url)
    return m.group(1) if m else ""


def _ci_whisper(row: dict) -> dict:
    ci = row.get("ci_analysis")
    if isinstance(ci, dict):
        w = ci.get("whisper")
        if isinstance(w, dict):
            return w
    return {}


def content_signal(row: dict) -> str:
    """LLM 분류용 신호. caption(일본어 원문) 주 + whisper 보조."""
    w = _ci_whisper(row)
    parts = [
        f"caption: {_text_of(row)[:600]}",
        f"hashtags: {(row.get('hashtags') or '')[:200]}",
        f"hook_visual: {(row.get('hook_caption_visual') or '')[:150]}",
        f"whisper.key_message: {(w.get('key_message') or '')[:200]}",
        f"whisper.hook_text_3s: {(w.get('hook_text_3s') or '')[:150]}",
    ]
    return "\n".join(parts)


# ── LLM constrained-label 분류 ──

def build_prompt(batch: list[dict], km_map: dict, hook_map: dict, hook_desc: dict,
                 corrections: str = "") -> str:
    km_list = "\n".join(f"{c}: {d}" for c, d in km_map.items())
    fmt = lambda c: f"{c}: {hook_map[c]}" + (f" — {hook_desc[c]}" if hook_desc.get(c) else "")
    hv_list = "\n".join(fmt(c) for c in hook_map if c.startswith("HV"))
    hc_list = "\n".join(fmt(c) for c in hook_map if c.startswith("HC"))
    items = "\n\n".join(
        f"[{i}]\n{content_signal(r)}" for i, r in enumerate(batch)
    )
    return f"""あなたはベビー用品ブランド Grosmimi のコンテンツ分類器です。
各コンテンツを、下記の**固定コードのみ**から分類してください。存在しないコードは絶対に出力しない。

## キーメッセージ(訴求点)コード一覧 (S##_F##):
{km_list}

## ビジュアルフック一覧 (HV-##) — 映像アクションによるフック:
{hv_list}

## キャプションフック一覧 (HC-##) — 画面テキスト/コピーによるフック:
{hc_list}
{corrections}
## 分類ルール:
- km_primary: 最も中心的なキーメッセージ 1つ (S##_F## から)
- km_sub: 副次的なキーメッセージ 1つ (無ければ "")
- hook_visual: 冒頭のビジュアルフック 1つ (HV-## から。無し/曖昧なら HV-00)
- hook_caption: 冒頭のキャプションフック 1つ (HC-## から。無し/曖昧なら HC-00)
- hook_primary: hook_visual と hook_caption のうち、実際にフックを主に担う方のコード 1つ
- confidence: 高/中/低 (根拠がcaptionに明確=高 / 推測含む=中 / 薄い=低)
- evidence: 判断根拠を caption の語句を引用して日本語1行

## 出力: 各アイテムにつき1オブジェクト、JSON配列のみ。他の文章禁止。
[{{"idx":0,"km_primary":"S01_F01","km_sub":"","hook_visual":"HV-05","hook_caption":"HC-06","hook_primary":"HC-06","confidence":"高","evidence":"..."}}]

## 分類対象 ({len(batch)}件):
{items}
"""


def call_llm(client, prompt: str) -> list[dict] | None:
    """3회 시도 후에도 실패하면 None (부분 성공 []와 구분 — 배치 전체 실패 신호).

    호출자는 None 이든 부분 누락이든 batch 아이템마다 validate(None)=빈태그·低 로 채워
    content↔tags 1:1 정렬을 보장한다. 빈 km_primary 행은 --incremental 이 '미태깅'으로
    간주해 다음 실행에서 자동 재시도된다 (실패분 유실 없음).
    """
    import anthropic  # noqa
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            txt = resp.content[0].text.strip()
            m = re.search(r"\[.*\]", txt, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception as e:
            print(f"  [LLM] attempt {attempt+1} failed: {e}")
    return None


def validate(tag: dict, km_map: dict, hook_map: dict) -> dict:
    """없는 코드/형식위반 리젝트 (drift 방지). 무효 코드는 빈값+低.

    tag 가 None/빈 dict(=LLM 누락분)여도 모든 필수 키를 채워 반환 → 하류 KeyError 방지.
    훅 v2: hook_visual 은 HV-## / hook_caption 은 HC-## 축 강제.
    hook_primary 는 두 축 중 하나 — 무효면 유효 축(미분류 -00 제외 우선)으로 폴백.
    """
    tag = tag or {}
    kmp = tag.get("km_primary", "")
    kms = tag.get("km_sub", "")
    hkv = tag.get("hook_visual", "")
    hkc = tag.get("hook_caption", "")
    hkp = tag.get("hook_primary", "")
    conf = tag.get("confidence", "低")
    flags = []
    if kmp not in km_map:
        flags.append(f"km_primary invalid:{kmp}")
        kmp = ""
    if kms and kms not in km_map:
        kms = ""
    if hkv not in hook_map or not hkv.startswith("HV"):
        flags.append(f"hook_visual invalid:{hkv}")
        hkv = ""
    if hkc not in hook_map or not hkc.startswith("HC"):
        flags.append(f"hook_caption invalid:{hkc}")
        hkc = ""
    if hkp not in (hkv, hkc) or hkp not in hook_map:
        hkp = next((c for c in (hkv, hkc) if c and not c.endswith("-00")), hkv or hkc or "")
    if conf not in ("高", "中", "低"):
        conf = "低"
    if flags:
        conf = "低"
    return {"km_primary": kmp, "km_sub": kms,
            "hook_visual": hkv, "hook_caption": hkc, "hook_primary": hkp,
            "confidence": conf, "evidence": tag.get("evidence", ""),
            "_flags": flags}


# ── Output ──

def build_rows(content: list[dict], tags: list[dict], km_map: dict, hook_map: dict) -> list[dict]:
    if len(content) != len(tags):
        raise ValueError(f"정렬 불일치: content({len(content)}) != tags({len(tags)})")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = []
    for r, t in zip(content, tags):
        out.append({
            "post_id": r.get("post_id", ""),
            "ct_pk": r.get("id", ""),
            "shortcode": _shortcode(r.get("url", "")),
            "username": r.get("username", ""),
            "url": r.get("url", ""),
            "region": r.get("region", ""),
            "content_type": r.get("content_type", ""),
            "km_primary": t["km_primary"],
            "km_primary_desc": km_map.get(t["km_primary"], ""),
            "km_sub": t["km_sub"],
            "hook_primary": t["hook_primary"],
            "hook_primary_name": hook_map.get(t["hook_primary"], ""),
            "confidence": t["confidence"],
            "evidence": t["evidence"],
            "taxonomy_ver": TAXONOMY_VER,
            "tagged_at": now,
            "hook_visual": t["hook_visual"],
            "hook_visual_name": hook_map.get(t["hook_visual"], ""),
            "hook_caption": t["hook_caption"],
            "hook_caption_name": hook_map.get(t["hook_caption"], ""),
        })
    return out


def write_csv(rows: list[dict]) -> Path:
    p = ROOT / ".tmp" / "jp_content_tags_auto.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in OUTPUT_COLS})
    return p


def read_csv() -> list[dict]:
    """직전 태깅 결과 CSV 로드 (LLM 재실행 없이 시트 반영용)."""
    p = ROOT / ".tmp" / "jp_content_tags_auto.csv"
    if not p.exists():
        raise FileNotFoundError(f"CSV 없음: {p} — 먼저 태깅 실행")
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_sheet(rows: list[dict]):
    """시트 OUTPUT_TAB 에 upsert (post_id 키). 탭 없으면 생성."""
    # 입력 내 post_id 중복 제거 (last wins) — upsert 예측가능성 보장
    dedup = {}
    for r in rows:
        dedup[r.get("post_id", "")] = r
    dropped = len(rows) - len(dedup)
    rows = list(dedup.values())

    gc = get_sheets_client()
    sh = gc.open_by_key(TAXONOMY_SHEET_ID)
    try:
        ws = sh.worksheet(OUTPUT_TAB)
    except Exception:
        ws = sh.add_worksheet(title=OUTPUT_TAB, rows=1000, cols=len(OUTPUT_COLS))

    existing = ws.get_all_values()
    # 헤더 보장: 없거나 불일치면 최상단 삽입 (기존 데이터 보존). 빈 탭 선생성 케이스 대비.
    if not existing or existing[0][:len(OUTPUT_COLS)] != OUTPUT_COLS:
        ws.insert_row(OUTPUT_COLS, 1)
        existing = ws.get_all_values()
    header = existing[0]
    id_col = header.index("post_id") if "post_id" in header else 0
    row_by_id = {r[id_col]: idx + 2 for idx, r in enumerate(existing[1:]) if r and len(r) > id_col}

    appends, updates = [], []
    for r in rows:
        line = [str(r.get(k, "")) for k in OUTPUT_COLS]
        pid = r.get("post_id", "")
        if pid in row_by_id:
            updates.append({"range": safe_range(OUTPUT_TAB, f"A{row_by_id[pid]}"), "values": [line]})
        else:
            appends.append(line)

    if updates:
        ws.spreadsheet.values_batch_update({"valueInputOption": "RAW", "data": updates})
    if appends:
        ws.append_rows(appends, value_input_option="RAW", table_range="A1")
    if dropped:
        print(f"  ⚠️ 입력 post_id 중복 {dropped}건 제거 (last wins)")
    return len(updates), len(appends)


def sync_jp_tab(rows: list[dict], km_map: dict, hook_map: dict):
    """Content Tags (JP) 탭(앱 소비) 자동 컬럼 upsert — shortcode 키.

    자동 컬럼(km_subject~tagged_at)만 갱신. km_manual/hook_manual(O/P)은 불가침.
    셀 값은 라벨 컨벤션 ("S06_F01 설명…" / "HC-09 부모 필독 어필") — 앱은 라벨에서 코드 추출.
    JP 탭에 없는 shortcode 는 자동 행으로 append (탭 자체가 태그 저장소).
    """
    gc = get_sheets_client()
    ws = gc.open_by_key(TAG_SHEET_ID).worksheet(TAG_TAB)
    vals = ws.get_all_values()
    hdr = [h.strip() for h in vals[0]]
    ix = {h: i for i, h in enumerate(hdr)}
    # 시트 실제 배치 순서 (7/13 세은 재배열: 비주얼·캡션이 지배훅 앞)
    auto_cols = ["km_subject", "km_primary", "km_primary_desc",
                 "hook_visual", "hook_caption", "hook_primary", "hook_primary_name",
                 "evidence", "tagged_at"]
    missing = [c for c in auto_cols + ["shortcode", "km_manual", "hook_manual"] if c not in ix]
    if missing:
        raise RuntimeError(f"JP 탭 헤더 누락: {missing} — 구조 변경됨, 동기화 중단")
    # 자동 컬럼 연속 배치 확인 (단일 range 쓰기 전제 — 어긋나면 중단이 안전)
    base = ix["km_subject"]
    if [ix[c] for c in auto_cols] != list(range(base, base + len(auto_cols))):
        raise RuntimeError("JP 탭 자동 컬럼 순서가 예상과 다름 — 동기화 중단")

    # subject 라벨 (S## → 이름) — KM SSOT 탭 스캔
    subj_label = {}
    tax = _km_worksheet(gc.open_by_key(TAXONOMY_SHEET_ID))
    subj_re = re.compile(r"^S\d{2}$")
    for row in tax.get_all_values():
        cells = [c.strip() for c in row]
        for i, c in enumerate(cells):
            if subj_re.match(c):
                if c not in subj_label:
                    subj_label[c] = next((cells[j] for j in range(i + 1, len(cells)) if cells[j]), "")
                break

    def cap(d):
        return d if len(d) <= DESC_CAP else d[:DESC_CAP - 1] + "…"

    def km_label(code):
        return f"{code} {cap(km_map.get(code, ''))}".strip() if code else ""

    def hk_label(code):
        return f"{code} {hook_map.get(code, '')}".strip() if code else ""

    def subj_of(code):
        s = code.split("_")[0] if code else ""
        return f"{s} {subj_label.get(s, '')}".strip() if s in subj_label else ""

    def col_letter(idx0):
        s, n = "", idx0
        while True:
            s = chr(ord("A") + n % 26) + s
            n = n // 26 - 1
            if n < 0:
                return s

    sc_i = ix["shortcode"]
    row_by_sc = {}
    for rix, r in enumerate(vals[1:], start=2):
        sc = (r[sc_i] if len(r) > sc_i else "").strip()
        if sc and sc not in row_by_sc:
            row_by_sc[sc] = rix

    L0, L1 = col_letter(base), col_letter(base + len(auto_cols) - 1)
    updates, appends = [], []
    for r in rows:
        sc = r.get("shortcode", "")
        if not sc:
            continue
        # km_primary_desc/hook_primary_name 은 라벨-인-셀 컨벤션이라 공란 유지
        auto_vals = [subj_of(r.get("km_primary", "")), km_label(r.get("km_primary", "")), "",
                     hk_label(r.get("hook_visual", "")), hk_label(r.get("hook_caption", "")),
                     hk_label(r.get("hook_primary", "")), "",
                     r.get("evidence", ""), r.get("tagged_at", "")]
        if sc in row_by_sc:
            rix = row_by_sc[sc]
            updates.append({"range": safe_range(TAG_TAB, f"{L0}{rix}:{L1}{rix}"), "values": [auto_vals]})
        else:
            line = [""] * len(hdr)
            for k in ("post_id", "ct_pk", "shortcode", "username", "url", "region", "content_type"):
                if k in ix:
                    line[ix[k]] = str(r.get(k, ""))
            line[base:base + len(auto_cols)] = auto_vals
            appends.append(line)

    if updates:
        ws.spreadsheet.values_batch_update({"valueInputOption": "RAW", "data": updates})
    if appends:
        ws.append_rows(appends, value_input_option="RAW", table_range="A1")
    return len(updates), len(appends)


# ── Main ──

def main():
    ap = argparse.ArgumentParser(description="JP 콘텐츠 요소별 자동 태깅")
    ap.add_argument("--dry-run", action="store_true", help="로드·필터·라벨집합만 (LLM/쓰기 X)")
    ap.add_argument("--limit", type=int, default=0, help="태깅 건수 제한 (0=전체)")
    ap.add_argument("--write-sheet", action="store_true", help="시트 탭에도 기록")
    ap.add_argument("--from-csv", action="store_true",
                    help="직전 CSV → 시트 반영 (LLM 재실행 없음)")
    ap.add_argument("--sync-jp", action="store_true",
                    help="Content Tags (JP) 탭(앱 소비) 자동 컬럼 동기화")
    ap.add_argument("--incremental", action="store_true",
                    help="JP 탭에 태그(자동/수동) 없는 shortcode 만 태깅 — 데일리 자동잡용")
    args = ap.parse_args()

    if args.from_csv:
        rows = read_csv()
        print(f"[from-csv] {len(rows)}건 로드 → 시트 '{OUTPUT_TAB}' 기록...")
        u, a = write_sheet(rows)
        print(f"  갱신 {u}건 / 추가 {a}건")
        if args.sync_jp:
            km_map, hook_map, _ = load_taxonomy()
            su, sa = sync_jp_tab(rows, km_map, hook_map)
            print(f"  '{TAG_TAB}' 동기화: 갱신 {su}건 / 추가 {sa}건")
        return

    print("[1] 택소노미 로드...")
    km_map, hook_map, hook_desc = load_taxonomy()
    n_hv = sum(1 for c in hook_map if c.startswith("HV"))
    n_hc = sum(1 for c in hook_map if c.startswith("HC"))
    print(f"    키메세지 코드 {len(km_map)}개 / Hook v2 HV {n_hv}개 + HC {n_hc}개")

    print("[2] JP 콘텐츠 로드 + 노이즈필터...")
    content = load_jp_content(limit=args.limit)
    print(f"    태깅 대상 {len(content)}건 (region=jp, 노이즈 제외)")
    # few-shot 캡션 룩업은 증분 필터 **전** 전체 로드분으로 고정 —
    # 교정된 행은 이미 태깅돼 incremental 에서 빠지므로, 필터 후 맵이면 예시가 공집합이 된다.
    all_by_sc = {_shortcode(r.get("url", "")): r for r in content if _shortcode(r.get("url", ""))}

    if args.incremental:
        done = load_tagged_shortcodes()
        before = len(content)
        # shortcode 없는 행은 JP 탭 upsert 키가 없어 편입 불가 → 증분 대상에서 제외
        content = [r for r in content
                   if _shortcode(r.get("url", "")) and _shortcode(r.get("url", "")) not in done]
        print(f"    [incremental] 기태깅 {len(done)}건 제외 → 신규 {len(content)}건 (스킵 {before - len(content)}건)")

    if args.dry_run:
        print("\n--- DRY RUN (LLM/쓰기 X) ---")
        for r in content[:10]:
            print(f"  @{(r.get('username') or '')[:20]:21} {r.get('content_type',''):14} {(_text_of(r)[:50])}")
        print(f"\n  샘플 라벨: KM {list(km_map)[:3]} ... / Hook {list(hook_map)[:5]}")
        return

    if not content:
        print("대상 없음. 종료.")
        return

    try:
        import anthropic
    except ImportError:
        sys.exit("[FATAL] anthropic 미설치 — pip install anthropic 후 재실행")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(f"ANTHROPIC_API_KEY not found — {ROOT / '.env'} 확인")
    client = anthropic.Anthropic(api_key=api_key)

    # 사람 교정 few-shot 주입 — 앱 심사(KM 확정)·콘텐츠 풀에서 고친 km_manual/기각("-")을
    # (오답→정답) 예시로 프롬프트에 포함 (2026-10-21 배선: 정의만 있고 호출 누락이던 버그 수정).
    # 룩업은 all_by_sc(증분 필터 전 전체분) — 교정된 행은 기태깅이라 필터 후엔 빠진다.
    corrections = build_corrections_block(all_by_sc)
    if corrections:
        print(f"    사람 교정 few-shot {corrections.count('[例')}건 주입")

    print("[3] LLM constrained-label 분류...")
    all_tags = []
    for i in range(0, len(content), BATCH_SIZE):
        batch = content[i:i + BATCH_SIZE]
        raw = call_llm(client, build_prompt(batch, km_map, hook_map, hook_desc, corrections))
        if raw is None:  # 배치 전체 실패 — 빈태그로 채워 정렬 유지, 다음 --incremental 재시도
            print(f"    ⚠️ 배치 {i}: LLM 3회 전부 실패 → {len(batch)}건 빈태그(低) 처리")
            raw = []
        # idx 중복 = LLM 출력 이상 신호 — 침묵 덮어쓰기 대신 경고 (뒤 항목이 이김)
        idx_seen = [t.get("idx") for t in raw if isinstance(t, dict)]
        dup_idx = sorted({x for x in idx_seen if idx_seen.count(x) > 1})
        if dup_idx:
            print(f"    ⚠️ 배치 {i}: LLM idx 중복 {dup_idx} — 마지막 항목만 사용")
        raw_by_idx = {t.get("idx"): t for t in raw if isinstance(t, dict)}
        missing = [j for j in range(len(batch)) if j not in raw_by_idx]
        if missing:
            print(f"    ⚠️ 배치 {i}: LLM 누락 {len(missing)}/{len(batch)}건 → 低 처리(정렬 유지)")
        # batch 아이템마다 정확히 1개 태그 append → all_tags 길이 == content 길이 불변 보장
        for j in range(len(batch)):
            all_tags.append(validate(raw_by_idx.get(j), km_map, hook_map))
        print(f"    {min(i+BATCH_SIZE, len(content))}/{len(content)}")

    if len(all_tags) != len(content):  # 방어적 불변식 (정상 경로에선 항상 성립)
        raise RuntimeError(f"정렬 불변식 위반: tags({len(all_tags)}) != content({len(content)})")

    rows = build_rows(content, all_tags, km_map, hook_map)

    print("\n[4] 결과:")
    print(f"  {'@user':22} {'km':10} {'HV':6} {'HC':6} {'主':6} {'信':3} evidence")
    for r in rows:
        print(f"  @{(r['username'])[:20]:21} {r['km_primary']:10} {r['hook_visual']:6} {r['hook_caption']:6} {r['hook_primary']:6} {r['confidence']:3} {r['evidence'][:36]}")
    from collections import Counter
    print("\n  km_primary 분포:", dict(Counter(r["km_primary"] for r in rows)))
    print("  信頼 분포:", dict(Counter(r["confidence"] for r in rows)))
    flagged = sum(1 for t in all_tags if t.get("_flags"))
    if flagged:
        print(f"  ⚠️ 무효코드 리젝트 {flagged}건 (低 강등)")

    p = write_csv(rows)
    print(f"\n  로컬 CSV: {p}")

    if args.write_sheet:
        u, a = write_sheet(rows)
        print(f"  시트 '{OUTPUT_TAB}' 갱신 {u}건 / 추가 {a}건")
    else:
        print("  (시트 미기록 — --write-sheet 로 반영)")

    if args.sync_jp:
        su, sa = sync_jp_tab(rows, km_map, hook_map)
        print(f"  '{TAG_TAB}' 동기화: 갱신 {su}건 / 추가 {sa}건")


if __name__ == "__main__":
    main()
