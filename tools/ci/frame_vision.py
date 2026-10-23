# -*- coding: utf-8 -*-
"""프레임 API → GPT-4o Vision 전용 판정(얼굴/제품/CTA) — 심사 채점 보강용.

배경(2026-09-29): 파이프라인은 비용 때문에 얼굴·제품 Vision 을 안 돌리고 앞3초 OCR 만 함.
심사 채점기(jp_content_ai_review)의 face·product3s·cta 축이 텍스트 추정에 그쳐, DataKeeper 가
개통한 프레임 이미지 공개 API 에서 이미지를 받아 직접 Vision 으로 실측해 보강한다.
심사 큐 대상(수십 건)만 호출하므로 전체 파이프라인 비용과 무관.

주의: 기존 범용 태거 vision_tagger.analyze_frames 는 이 프레임들에서 빈 응답/오판(얼굴 있는데 0)이
잦아 재사용 불가(2026-09-29 육안 대조로 확인). → 얼굴/제품/CTA 만 묻는 **전용 프롬프트**로 직접 호출.

API: GET /api/public/v1/content/content_posts/<id>/frames/  (헤더 X-Api-Key)
     → {frame_count, stored, expires_in, frames:[{i,kind,t,url}]}  (url 1h 만료)
"""
import os, json, base64, tempfile, urllib.request, urllib.parse
from pathlib import Path

FRAMES_BASE = "https://orbitools.orbiters.co.kr/api/public/v1/content"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# GROSMIMI 공식 제품 사진(흰 배경 정면컷) — Vision 판정에 참조 이미지로 선행 주입.
# 색만 다른 SKU 는 폼이 같아 한 장으로 커버. 라인업 바뀌면 사진 교체/추가만 하면 됨 (재학습 불요).
# 출처: Notion 제품 DB 39d86c6dc04681df934bc016bcb3679b (2026-10-22 덤프)
_REF_DIR = Path(__file__).resolve().parents[2] / "data" / "product_ref"
_ref_cache: list[str] | None = None


_REF_MAX_COUNT = 8                 # 참조 이미지 상한 (초과분은 이름순 뒤쪽 무시)
_REF_MAX_BYTES = 2 * 1024 * 1024   # 장당 2MB 초과는 스킵 (detail:low 라 저용량이면 충분)


def _load_ref_images() -> list[str]:
    """data/product_ref/ 의 참조 이미지를 base64 로 로드 (모듈 캐시 — 단일 스레드 CLI 전용)."""
    global _ref_cache
    if _ref_cache is not None:
        return _ref_cache
    imgs = []
    if _REF_DIR.is_dir():
        for p in sorted(_REF_DIR.iterdir()):
            if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            if len(imgs) >= _REF_MAX_COUNT:
                print(f"  [frame_vision] 참조 이미지 {_REF_MAX_COUNT}장 상한 — {p.name} 이후 무시")
                break
            try:
                data = p.read_bytes()
            except OSError as e:
                print(f"  [frame_vision] 참조 이미지 읽기 실패 {p.name}: {e}")
                continue
            if len(data) > _REF_MAX_BYTES:
                print(f"  [frame_vision] 참조 이미지 {p.name} {len(data)//1024}KB > 2MB — 스킵")
                continue
            imgs.append(base64.b64encode(data).decode())
    _ref_cache = imgs
    return imgs


_REF_INTRO = (
    "最初の{n}枚は【GROSMIMI公式商品写真(参考画像)】です。これが我々の商品: "
    "①PPSUストローマグ(両側ハンドル+円錐形キャップ&リング+Gロゴ) ②同ダークGロゴ(チャコール透明) "
    "③PPSUワンタッチキャップ型(恐竜/ユニコーン等キャラ柄+フリップ蓋) ④ステンレス製ストローマグ(キャラ柄+ワンタッチ蓋) "
    "⑤交換用ストロー(透明シリコン・台紙パック) ⑥ステンレスキッズタンブラー(持ち手ストラップ+ワンタッチ蓋)。"
    "色違いは同一フォルムとして扱うこと。この後に続くのが判定対象の動画フレームです。"
)

_PROMPT = (
    "ここからは日本の育児リール動画のフレーム(冒頭hook=0〜3秒＋本文body)です。映像を実際に見て次をJSONで判定: "
    "face=乳幼児の顔がモザイクなしで明確に映るか(0/1), "
    "product3s=最初のhookフレーム(3秒以内)に【GROSMIMI商品(参考画像と同一フォルムの商品)】が映るか(0/1) — "
    "他社のコップ/マグ/ボトルは0とする, "
    "is_our_product=全フレームのどこかにGROSMIMI商品(参考画像と同一フォルム)が映るか(0/1) — "
    "映っている容器が他社品のみなら0, "
    "cta=画面に行動喚起テキスト・矢印・「詳細は」等が表示されるか(0/1), "
    "child_visible=乳幼児が映るフレームがあるか(0/1)。"
    "商品の同一性はフォルム(ハンドル形状・キャップ構造・Gロゴ・キャラ柄)で判断し、確信が持てなければ0。"
    '出力は {"face":0,"product3s":0,"is_our_product":0,"cta":0,"child_visible":0,"note":"根拠を短く"} 形式のJSONのみ。'
)

# 참조 이미지가 없을 때(폴백) 쓰는 구 프롬프트 — 제품 식별력 없음(범용 컵 판정)
_PROMPT_NOREF = (
    "これは日本の育児リール動画のフレーム(冒頭hook=0〜3秒＋本文body)です。映像を実際に見て次をJSONで判定: "
    "face=乳幼児の顔がモザイクなしで明確に映るか(0/1), "
    "product3s=最初のhookフレーム(3秒以内)に商品(コップ/マグ/ボトル/ストロー)が映るか(0/1), "
    "cta=画面に行動喚起テキスト・矢印・「詳細は」等が表示されるか(0/1), "
    "child_visible=乳幼児が映るフレームがあるか(0/1)。"
    '出力は {"face":0,"product3s":0,"cta":0,"child_visible":0,"note":"根拠を短く"} 形式のJSONのみ。'
)


def _get(url, key, timeout=40):
    req = urllib.request.Request(url, headers={"X-Api-Key": key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _vision_call(b64_images: list, timeout=60) -> dict | None:
    ok = os.getenv("OPENAI_API_KEY", "")
    if not ok:
        print("  [frame_vision] OPENAI_API_KEY 없음 — Vision 스킵")
        return None
    if not b64_images:
        return None

    def img(b64):
        return {"type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}}

    refs = _load_ref_images()
    if refs:
        # 참조 이미지(공식 제품 사진) 선행 주입 → 프레임 → 판정 프롬프트
        content = [{"type": "text", "text": _REF_INTRO.format(n=len(refs))}]
        content.extend(img(b) for b in refs)
        content.append({"type": "text", "text": _PROMPT})
    else:
        # 참조 세트 부재 시 범용 컵 판정으로 폴백 (is_our_product 미판정)
        content = [{"type": "text", "text": _PROMPT_NOREF}]
    content.extend(img(b) for b in b64_images)
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }).encode()
    # 일시 오류 1회 재시도. 응답 구조는 방어적으로 파싱 (스키마 변동/오류 응답 시 None 폴백).
    last_err = ""
    for attempt in (1, 2):
        req = urllib.request.Request(OPENAI_URL, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {ok}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.load(r)
            choices = resp.get("choices") if isinstance(resp, dict) else None
            if not choices:
                last_err = f"choices 없음: {str(resp)[:120]}"
                continue
            txt = (choices[0].get("message") or {}).get("content")
            if not txt:
                last_err = "content 비어있음"
                continue
            obj = json.loads(txt)
            return obj if isinstance(obj, dict) else None
        except Exception as e:
            last_err = str(e)[:120]
    print(f"  [frame_vision] Vision 호출 실패(재시도 포함): {last_err}")
    return None


def fetch_frame_vision(ct_id, key, max_imgs=6):
    """content_posts id 로 프레임 이미지를 받아 얼굴/제품/CTA 를 Vision 실측.

    반환: dict(face, product3s, cta, child_visible in 0/1,
              is_our_product in 0/1|None(참조 세트 부재로 미판정),
              note, _stored, _used) 또는
          None(프레임 없음/Vision 실패) → 호출자는 기존 텍스트 추정으로 폴백.
    product3s/is_our_product 는 data/product_ref/ 참조 이미지가 있으면
    GROSMIMI 제품 한정 판정, 없으면 범용 컵 판정(_PROMPT_NOREF 폴백).
    """
    if not ct_id or not key:
        return None
    try:
        meta = _get(f"{FRAMES_BASE}/content_posts/{ct_id}/frames/", key)
    except Exception as e:
        print(f"  [frame_vision] frames API 실패 id={ct_id}: {str(e)[:120]}")
        return None
    frames = meta.get("frames") or []
    if not frames or (meta.get("stored") or 0) == 0:
        return None
    # hook(3초 판정) 최대 4장 + 나머지 body 균등 간격 샘플.
    # hook 만 보내면 is_our_product(영상 전체 등장)가 본문 등장분을 놓침 (2026-10-22 ct76257 실측:
    # stored 40 중 hook 6장만 전송돼 body 미관측).
    hooks = sorted((f for f in frames if f.get("kind") == "hook"),
                   key=lambda f: f.get("t") or 0)[:4]
    bodies = sorted((f for f in frames if f.get("kind") != "hook"),
                    key=lambda f: f.get("t") or 0)
    n_body = max(0, max_imgs - len(hooks))
    if bodies and n_body:
        step = max(1, len(bodies) // n_body)
        bodies = bodies[::step][:n_body]
    else:
        bodies = []
    frames = hooks + bodies

    b64s = []
    failed = 0
    for f in frames:
        url = f.get("url")
        if not url:
            continue
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                b64s.append(base64.b64encode(r.read()).decode())
        except Exception:
            failed += 1    # 서명 URL 1h 만료 등 — 건너뛰되 집계는 남김
    if failed:
        print(f"  [frame_vision] 프레임 다운로드 실패 {failed}/{len(frames)} id={ct_id}")
    if not b64s:
        return None

    vt = _vision_call(b64s)
    if not vt:
        return None

    def bit(k):
        try:
            return 1 if int(vt.get(k, 0)) >= 1 else 0
        except Exception:
            return 0
    return {
        "face": bit("face"),
        "product3s": bit("product3s"),
        # 참조 세트 부재(_PROMPT_NOREF) 땐 모델에 안 물었으므로 None = 미판정
        "is_our_product": bit("is_our_product") if "is_our_product" in vt else None,
        "cta": bit("cta"),
        "child_visible": bit("child_visible"),
        "note": str(vt.get("note", ""))[:200],
        "_stored": meta.get("stored"),
        "_used": len(b64s),
    }


if __name__ == "__main__":
    import sys
    key = sys.argv[1] if len(sys.argv) > 1 else os.getenv("DK_CONTENT_FRAMES_KEY", "")
    pid = sys.argv[2] if len(sys.argv) > 2 else "72735"
    print(json.dumps(fetch_frame_vision(pid, key), ensure_ascii=False, indent=2))
