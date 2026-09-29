"""JP 콘텐츠 AI 1차 채점 — content 신호(caption·Whisper transcript·ci_analysis) → 7축 채점 → 시트 ai_* 기록.

human-in-the-loop: 이 도구가 AI 1차, 메타몽 app /influencer/review 에서 인간 2차 확정.
시트 "JP Content Review" 의 AI 블록(A:P)만 쓴다 (인간 블록 Q:AC 는 앱이 씀).
컬럼 레이아웃은 meta-app/lib/review-store.ts HEADER 와 반드시 동일.

루브릭 정본: memory/reference_jp_content_review_rubric.md
  정량(예선): D+3 오가닉 좋아요 ≥10 통과분만 채점.
  정성 7축(만점9·컷4): KM단일성(0-2)·실음성/AI(0-1)·CTA(0-1)·3초제품(0-1)·얼굴노출(0-1)·문제해결(0-1)·훅(0-2).

사용:
  python tools/jp_content_ai_review.py --dry-run           # 시트 미기록, 채점 출력만
  python tools/jp_content_ai_review.py --limit 5           # 상위 5건 채점+기록
  python tools/jp_content_ai_review.py --rescore <shortcode>  # 특정 건 재채점
"""
from __future__ import annotations
import os
import sys
import re
import json
import argparse
import datetime as dt
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from env_loader import load_env
    load_env()
except Exception:
    pass
from sheets_utils import get_sheets_client, safe_range  # noqa: E402
try:
    from ci.frame_vision import fetch_frame_vision  # noqa: E402
except Exception:
    fetch_frame_vision = None

DK_BASE = "https://orbitools.orbiters.co.kr/api/datakeeper"
FRAMES_KEY = os.getenv("DK_CONTENT_FRAMES_KEY", "")
DK_TOKEN = os.getenv("DK_SE_READ_TOKEN") or "dk_SE_7de6ec154f3d7b7bd0cc571a9e5b7220e125af197cf9dc1d40b893b086e13023"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TAG_SHEET_ID = os.getenv("TAG_SHEET_ID") or "13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE"
TAB = "JP Content Review"

TARGET_DAY = 3
FALLBACK_WINDOW = 7
RECENT_MAX_AGE = 21
D3_LIKES_GATE = 10

# meta-app/lib/review-store.ts HEADER 와 동일 (30열: A~AD)
HEADER = [
    "shortcode", "ct_id", "handle", "post_date", "d3_likes",
    "ai_km", "ai_voice", "ai_cta", "ai_product3s", "ai_face", "ai_problem", "ai_hook",
    "ai_total", "ai_verdict", "ai_reasoning", "ai_scored_at",
    "km", "voice", "cta", "product3s", "face", "problem", "hook",
    "total", "verdict", "reviewer", "reviewed_at", "creator_memo", "playbook_memo",
    "correction_notes",   # 인간이 바꾼 축별 이유 (AI 학습 신호). AI 는 안 씀(인간 블록).
]
AXES = ["km", "voice", "cta", "product3s", "face", "problem", "hook"]
AX_MAX = {"km": 2, "voice": 1, "cta": 1, "product3s": 1, "face": 1, "problem": 1, "hook": 2}


def dk_query(table: str, **params) -> list[dict]:
    params["table"] = table
    url = f"{DK_BASE}/query/?{urlencode(params)}"
    req = Request(url, headers={"Authorization": f"Bearer {DK_TOKEN}"})
    try:
        with urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        sys.exit(f"[DK {table}] HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}")
    if isinstance(data, list):
        return data
    return data.get("rows", [])


def resolve_d3_likes(post_date: str, rows: list[dict]) -> int | None:
    """post_date+3 에 가장 가까운 실측 likes (±7일). 누적 likes."""
    target = dt.date.fromisoformat(post_date) + dt.timedelta(days=TARGET_DAY)
    best = None
    for r in rows:
        lk = r.get("likes")
        if lk is None or lk < 0:   # likes=-1 = 크롤 실패 마커 (2026-09-22)
            continue
        try:
            d = dt.date.fromisoformat(r["date"])
        except Exception:
            continue
        gap = abs((d - target).days)
        if gap > FALLBACK_WINDOW:
            continue
        if best is None or gap < best[0]:
            best = (gap, lk)
    return best[1] if best else None


def build_queue() -> list[dict]:
    posts = dk_query(
        "content_posts", region="jp", days=30, limit=2000,
        fields="id,post_id,post_date,username,platform,content_type,brand,url,caption,transcript,ci_analysis",
    )
    metrics = dk_query("content_metrics_daily", days=60, limit=50000, fields="post_id,date,likes")
    by_post: dict[str, list[dict]] = {}
    for m in metrics:
        by_post.setdefault(m.get("post_id"), []).append(m)

    today = dt.date.today()
    out = []
    for p in posts:
        if p.get("platform") != "instagram":
            continue
        # 우리 콜라보 = brand='grosmimi' OR content_type='partnered' 합집합 (2026-09-23).
        # brand 는 non_partnered 묻힌 콜라보를, partnered(coauthor)는 brand 빈 콜라보를 건짐.
        # 자사 계정(owned)만 제외. meta-app/lib/review.ts buildReviewQueue 와 동일 필터.
        ct = (p.get("content_type") or "").lower()
        is_collab = (p.get("brand") or "").lower() == "grosmimi" or ct == "partnered"
        if not is_collab or ct == "owned":
            continue
        pid, pdate = p.get("post_id"), p.get("post_date")
        if not pid or not pdate:
            continue
        try:
            age = (today - dt.date.fromisoformat(pdate)).days
        except Exception:
            continue
        if age < TARGET_DAY or age > RECENT_MAX_AGE:
            continue
        d3 = resolve_d3_likes(pdate, by_post.get(pid, []))
        if d3 is None or d3 < D3_LIKES_GATE:   # 정량 예선 통과분만 AI 채점
            continue
        out.append({
            "shortcode": pid, "ct_id": str(p.get("id") or pid), "handle": p.get("username", ""),
            "post_date": pdate, "d3_likes": d3, "url": p.get("url") or "",
            "caption": p.get("caption") or "", "transcript": p.get("transcript") or "",
            "ci": p.get("ci_analysis") or {},
        })
    out.sort(key=lambda x: x["post_date"], reverse=True)
    return out


SYSTEM = """あなたは日本の育児系インフルエンサー動画を広告出稿すべきか審査するアシスタントです。
提供された動画のシグナル(キャプション・音声書き起こし・CI分析)から、7つの軸を客観的に採点します。
主観ではなく観察可能な事実で判断し、確信が持てない軸は保守的に低めを選び理由に明記してください。
必ず指定のJSONだけを返します。"""

RUBRIC = """採点軸 (JSON keys):
- km (0-2) KM単一性: 一つのキーメッセージが明確に伝わるか。2=単一メッセージが動画全体を貫き無音でも伝わる / 1=複数メッセージ混在 or 音声が要る / 0=主張が特定できない
- voice (0-1) 実音声・自然音(1)/AI音声・BGMのみ・無音(0): 実在の人物の声(ナレーション)、または自然な現場音・生活音(自然音=非BGMの環境音)が含まれるか。書き起こしが自然な口語 or 自然音ありなら1。AI生成音声/自然言語・自然音なくBGM(音源)のみ/無音 のみ0
- cta (0-1) CTA有無: 購入/リンク/プロフィール等の行動喚起があるか。script_structure に cta が含まれる/「詳細は本文」等
- product3s (0-1) 3秒以内に製品登場: 冒頭3秒で製品が画面に出るか。フレーム映像信号が乏しい場合は hook/product_mention から保守的に推定し理由に不確実性を明記
- face (0-1) 子供の顔出し(モザイクなし=1): 実証的に効果あり。映像信号が乏しい場合は保守的に0寄りで推定し不確実性を明記
- problem (0-1) 問題→解決構造: persuasion_type=problem_solution なら1
- hook (0-2) フック: 冒頭の掴み+本編との接続。2=最初の場面/キャプションが目を引きフックの約束を本編が回収 / 1=フックはあるが本編と繋がらない or 出だしが平凡 / 0=単調な挨拶やVlog形式で掴みなし

返すJSON(これだけ):
{"km":0,"voice":0,"cta":0,"product3s":0,"face":0,"problem":0,"hook":0,
 "reasons":{"km":"","voice":"","cta":"","product3s":"","face":"","problem":"","hook":""}}
reasons は各軸ごとに、その軸だけの根拠を1〜2文で簡潔に。**必ず韓国語で書くこと(日本語禁止)**。
product3s と face は映像信号が乏しい場合は不確実性を韓国語で明記すること。"""

# 시트/앱 표시용 한국어 축 라벨
AX_LABEL = {
    "km": "KM 단일성", "voice": "실음성/AI", "cta": "CTA", "product3s": "3초 내 제품",
    "face": "아이 얼굴 노출", "problem": "문제→해결", "hook": "훅",
}

# 학습(few-shot) 파라미터 — 세은 확정 2026-09-23: 축당 최근 6건 / 전체 40건 상한
LEARN_PER_AXIS = 6
LEARN_TOTAL_CAP = 40
_CORR_LINE = re.compile(r"^\s*(.+?)\s*[:：]\s*AI\s*(\d+)\s*→\s*(\d+)\s*[·・]\s*(.+?)\s*$")


def build_correction_examples(ws, per_axis: int = LEARN_PER_AXIS,
                              total_cap: int = LEARN_TOTAL_CAP) -> str:
    """시트 correction_notes(인간 축별 교정)를 few-shot 블록으로 구성.
    형식 "축: AI X→Y · 이유" 를 축별로 그룹핑, 최신순 축당 per_axis·전체 total_cap 상한.
    세은 교정 = AI 채점의 최우선 기준으로 주입 (in-context 학습)."""
    try:
        rows = ws.get_all_values()
    except Exception:
        return ""
    if not rows:
        return ""
    hdr = rows[0]
    if "correction_notes" not in hdr:
        return ""
    i_cn = hdr.index("correction_notes")
    by_axis: dict[str, list[str]] = {}
    for r in reversed(rows[1:]):        # 최신(아래)부터
        if len(r) <= i_cn or not r[i_cn].strip():
            continue
        for line in r[i_cn].splitlines():
            m = _CORR_LINE.match(line)
            if not m:
                continue
            axis, ai, human, reason = m.group(1), m.group(2), m.group(3), m.group(4)
            bucket = by_axis.setdefault(axis, [])
            if len(bucket) < per_axis:
                bucket.append(f"【{axis}】AI {ai}→{human}: {reason}")
    flat = []
    for axis in by_axis:
        flat.extend(by_axis[axis])
    flat = flat[:total_cap]
    if not flat:
        return ""
    return (
        "\n\n=== レビュアー(セウン)による過去の採点修正 — これを最優先の基準とせよ ===\n"
        "以下は人間レビュアーが実際にAI採点を直した実例。類似ケースでは必ずこの基準に合わせること。\n"
        "(表記: 【軸】AI(元の点)→(人間の点): 理由)\n"
        + "\n".join(flat)
    )


def call_openai(system_prompt: str, user_prompt: str, model: str = "gpt-4.1") -> dict:
    url = "https://api.openai.com/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_tokens": 1200,
    }).encode("utf-8")
    req = Request(url, data=payload, method="POST", headers={
        "Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return {"ok": True, "content": data["choices"][0]["message"]["content"]}
    except HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def signal_block(item: dict) -> str:
    ci = item.get("ci") or {}
    w = ci.get("whisper") or {}
    v = ci.get("vision") or {}
    parts = [
        f"handle: @{item['handle']}",
        f"caption: {item['caption'][:800]}",
        f"transcript(Whisper): {item['transcript'][:600]}",
        f"whisper.key_message: {w.get('key_message','')}",
        f"whisper.hook_text_3s: {w.get('hook_text_3s','')}",
        f"whisper.main_question: {w.get('main_question','')}",
        f"whisper.persuasion_type: {w.get('persuasion_type','')}",
        f"whisper.script_structure: {w.get('script_structure','')}",
        f"whisper.product_mention: {w.get('product_mention','')}",
        f"whisper.delivery_verbal_score: {w.get('delivery_verbal_score','')}",
        f"vision.hook_caption_visual: {v.get('hook_caption_visual','')}",
        f"video_url: {item['url']}",
    ]
    # 프레임 이미지 실측(GPT-4o Vision 전용 판정) — 있으면 face/product3s/cta 축은 텍스트 추정보다
    # 이 실측(0/1)을 우선 근거로 삼을 것(画像を実際に見た判定).
    fv = item.get("frame_vision") or {}
    if fv:
        parts.append(
            "[映像フレーム実測(GPT-4o Vision・画像を実見／テキスト推定より優先)] "
            f"顔出し(モザイクなし)={fv.get('face')} 3秒以内商品={fv.get('product3s')} "
            f"CTA画面表示={fv.get('cta')} 乳幼児出現={fv.get('child_visible')} "
            f"根拠:{fv.get('note','')}"
        )
    return "\n".join(parts)


def score_item(item: dict, model: str, examples: str = "") -> dict | None:
    # examples = 세은 과거 교정(few-shot). SYSTEM 뒤에 붙여 최우선 기준으로 반영.
    # 프레임 이미지 Vision 실측 주입(심사 큐만·미보관 건은 None→기존 텍스트 추정 폴백).
    if fetch_frame_vision and FRAMES_KEY and item.get("frame_vision") is None:
        try:
            item["frame_vision"] = fetch_frame_vision(item.get("ct_id"), FRAMES_KEY) or {}
        except Exception as e:
            print(f"  [frame_vision] skip: {str(e)[:80]}", file=sys.stderr)
            item["frame_vision"] = {}
    res = call_openai(SYSTEM + examples, RUBRIC + "\n\n=== 動画シグナル ===\n" + signal_block(item), model)
    if not res["ok"]:
        print(f"  ✗ LLM 실패: {res['error'][:150]}", file=sys.stderr)
        return None
    try:
        obj = json.loads(res["content"])
    except Exception:
        print(f"  ✗ JSON 파싱 실패: {res['content'][:150]}", file=sys.stderr)
        return None
    scores = {}
    for ax in AXES:
        try:
            v = int(obj.get(ax, 0))
        except Exception:
            v = 0
        scores[ax] = max(0, min(AX_MAX[ax], v))
    # 근거: 축별로 "라벨 (점수): 근거" 한 줄씩 (항목별 정리). reasons 없으면 구 reasoning 폴백.
    reasons = obj.get("reasons") if isinstance(obj.get("reasons"), dict) else {}
    if reasons:
        lines = [f"{AX_LABEL[ax]} ({scores[ax]}): {str(reasons.get(ax, '')).strip()}" for ax in AXES]
        scores["reasoning"] = "\n".join(lines)[:1900]
    else:
        scores["reasoning"] = str(obj.get("reasoning", ""))[:1900]
    return scores


def load_scored_shortcodes(ws) -> set[str]:
    """이미 AI 채점된 shortcode (ai_scored_at 있음)."""
    rows = ws.get_all_values()
    if not rows:
        return set()
    hdr = rows[0]
    try:
        i_sc, i_at = hdr.index("shortcode"), hdr.index("ai_scored_at")
    except ValueError:
        return set()
    return {r[i_sc].strip() for r in rows[1:] if len(r) > i_at and r[i_at].strip()}


def get_or_create_ws(gc):
    sh = gc.open_by_key(TAG_SHEET_ID)
    try:
        ws = sh.worksheet(TAB)
    except Exception:
        ws = sh.add_worksheet(title=TAB, rows=2000, cols=len(HEADER))
    # 헤더 보장: 없거나 스키마 불일치면 1행을 HEADER 로 갱신.
    # (insert_row 는 중복 헤더를 만들므로 update 사용 — correction_notes 등 컬럼 추가 대응)
    existing = ws.get_all_values()
    if not existing or existing[0][:len(HEADER)] != HEADER:
        ws.spreadsheet.values_batch_update({
            "valueInputOption": "RAW",
            "data": [{"range": safe_range(TAB, "A1:AD1"), "values": [HEADER]}],
        })
    return ws


def write_ai(ws, item: dict, scores: dict):
    """AI 블록(A:P)만 기록. 인간 블록(Q:AC)은 건드리지 않음."""
    total = sum(scores[a] for a in AXES)
    verdict = "집행" if total >= 4 else "미집행"
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    ai_row = [
        item["shortcode"], item["ct_id"], item["handle"], item["post_date"], item["d3_likes"],
        scores["km"], scores["voice"], scores["cta"], scores["product3s"], scores["face"],
        scores["problem"], scores["hook"], total, verdict, scores["reasoning"], now_iso,
    ]  # A:P (16열)
    rows = ws.get_all_values()
    hdr = rows[0] if rows else HEADER
    i_sc = hdr.index("shortcode")
    row_ix = None
    for r_i in range(1, len(rows)):
        if len(rows[r_i]) > i_sc and rows[r_i][i_sc].strip() == item["shortcode"]:
            row_ix = r_i + 1
            break
    if row_ix:
        ws.spreadsheet.values_batch_update({
            "valueInputOption": "RAW",
            "data": [{"range": safe_range(TAB, f"A{row_ix}:P{row_ix}"), "values": [ai_row]}],
        })
    else:
        ws.append_rows([ai_row], value_input_option="RAW", table_range="A1")
    return total, verdict


REVIEW_URL = "https://meta-app-one.vercel.app/influencer/review"


def send_summary_email(results: list[dict], skipped: int, to_email: str) -> None:
    """배치 채점 결과 요약을 세은에게 메일 발송 (Task Scheduler 자동 실행용).
    Gmail OAuth 경로(send_gmail) 사용 — SMTP SENDER_PASSWORD 는 미설정이라 안 씀."""
    n = len(results)
    exe = [r for r in results if r["verdict"] == "집행"]
    rows = "".join(
        f"<tr><td style='padding:4px 10px'>@{r['handle']}</td>"
        f"<td style='padding:4px 10px'>{r['post_date']}</td>"
        f"<td style='padding:4px 10px;text-align:center'>&#9829;{r['d3_likes']}</td>"
        f"<td style='padding:4px 10px;text-align:center'>{r['total']}/9</td>"
        f"<td style='padding:4px 10px;text-align:center;color:{'#2e7d32' if r['verdict']=='집행' else '#b0b0b0'}'>{r['verdict']}</td>"
        f"<td style='padding:4px 10px'><a href='{r['url']}'>보기</a></td></tr>"
        for r in sorted(results, key=lambda x: -x["total"])
    )
    html = f"""<div style="font-family:sans-serif;font-size:14px;color:#333">
    <h2>JP 콘텐츠 AI 1차 채점 완료</h2>
    <p>신규 <b>{n}건</b> 채점 (집행 후보 <b>{len(exe)}</b> / 미집행 {n-len(exe)}) · 이미 채점됨 {skipped}건 제외</p>
    <table style="border-collapse:collapse;border:1px solid #ddd">
    <tr style="background:#f5f5f5"><th style='padding:6px 10px'>핸들</th><th>게시일</th><th>D+3♥</th><th>AI점수</th><th>판정</th><th></th></tr>
    {rows if n else '<tr><td colspan=6 style="padding:10px">신규 채점 건 없음</td></tr>'}
    </table>
    <p style="margin-top:16px">→ <a href="{REVIEW_URL}">심사 페이지에서 2차 검수</a> (AI 1차가 프리필됨)</p>
    <p style="color:#999;font-size:12px">Task Scheduler 자동 실행 · brand='grosmimi' 콜라보 큐</p></div>"""

    subject = f"[그로미미] JP 콘텐츠 AI 1차 채점 {n}건 (집행후보 {len(exe)})"
    try:
        from send_gmail import send_email as gmail_send   # 자동화 검증된 Gmail OAuth 경로
        gmail_send(to=to_email, subject=subject, body_html=html)
        print(f"[MAIL] 요약 발송 완료 → {to_email}")
    except Exception as e:
        print(f"[MAIL] 발송 실패: {e}")


def main():
    ap = argparse.ArgumentParser(description="JP 콘텐츠 AI 1차 채점")
    ap.add_argument("--dry-run", action="store_true", help="시트 미기록, 채점 출력만")
    ap.add_argument("--limit", type=int, default=0, help="상위 N건만 (0=전체)")
    ap.add_argument("--rescore", default="", help="특정 shortcode 재채점(이미 채점된 것도)")
    ap.add_argument("--model", default="gpt-4.1")
    ap.add_argument("--email", default="", help="완료 후 요약 발송할 이메일 (Task Scheduler용)")
    args = ap.parse_args()

    if not OPENAI_API_KEY:
        sys.exit("ERROR: OPENAI_API_KEY 없음 (.env 확인)")

    queue = build_queue()
    print(f"[큐] 정량 통과 JP IG 콜라보 {len(queue)}건 (최근 {RECENT_MAX_AGE}일·D+3 좋아요≥{D3_LIKES_GATE})")

    gc = get_sheets_client()
    if args.dry_run:
        try:
            ws = gc.open_by_key(TAG_SHEET_ID).worksheet(TAB)
        except Exception:
            ws = None
        scored = set()
    else:
        ws = get_or_create_ws(gc)
        scored = load_scored_shortcodes(ws)

    examples = build_correction_examples(ws) if ws else ""
    if examples:
        print(f"[학습] 세은 교정 few-shot {examples.count(chr(0x3010))}건 주입 (축당≤{LEARN_PER_AXIS}·전체≤{LEARN_TOTAL_CAP})")

    if args.rescore:
        queue = [q for q in queue if q["shortcode"] == args.rescore]
        scored = set()
        if not queue:
            sys.exit(f"shortcode {args.rescore} 가 정량 통과 큐에 없음")
    else:
        queue = [q for q in queue if q["shortcode"] not in scored]
    if args.limit > 0:
        queue = queue[:args.limit]
    print(f"[채점 대상] {len(queue)}건 (이미 채점 {len(scored)}건 제외)\n")

    done = 0
    results = []
    for i, item in enumerate(queue, 1):
        print(f"[{i}/{len(queue)}] @{item['handle']} CT{item['ct_id']} ♥{item['d3_likes']} ({item['post_date']})")
        sc = score_item(item, args.model, examples)
        if not sc:
            continue
        total = sum(sc[a] for a in AXES)
        verdict = "집행" if total >= 4 else "미집행"
        print(f"   AI: km{sc['km']} voice{sc['voice']} cta{sc['cta']} prod{sc['product3s']} "
              f"face{sc['face']} prob{sc['problem']} hook{sc['hook']} → {total}/9 {verdict}")
        print(f"   근거: {sc['reasoning'][:160]}")
        results.append({"handle": item["handle"], "post_date": item["post_date"],
                        "d3_likes": item["d3_likes"], "total": total, "verdict": verdict,
                        "url": item.get("url", "")})
        if not args.dry_run:
            write_ai(ws, item, sc)
            done += 1
    print(f"\n완료: {done}건 기록" + (" (dry-run — 미기록)" if args.dry_run else f" → 시트 '{TAB}'"))

    if args.email and not args.dry_run:
        send_summary_email(results, len(scored), args.email)


if __name__ == "__main__":
    main()
