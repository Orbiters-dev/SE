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

_PROMPT = (
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
    if not ok or not b64_images:
        return None
    content = [{"type": "text", "text": _PROMPT}]
    for b64 in b64_images:
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}})
    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(OPENAI_URL, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {ok}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.load(r)
        txt = resp["choices"][0]["message"]["content"]
        return json.loads(txt) if txt else None
    except Exception as e:
        print(f"  [frame_vision] Vision 호출 실패: {str(e)[:120]}")
        return None


def fetch_frame_vision(ct_id, key, max_imgs=6):
    """content_posts id 로 프레임 이미지를 받아 얼굴/제품/CTA 를 Vision 실측.

    반환: dict(face, product3s, cta, child_visible in 0/1, note, _stored, _used) 또는
          None(프레임 없음/Vision 실패) → 호출자는 기존 텍스트 추정으로 폴백.
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
    # hook(3초 판정) 우선 + 시간순, 최대 max_imgs 장
    frames.sort(key=lambda f: (0 if f.get("kind") == "hook" else 1, f.get("t") or 0))
    frames = frames[:max_imgs]

    b64s = []
    for f in frames:
        url = f.get("url")
        if not url:
            continue
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                b64s.append(base64.b64encode(r.read()).decode())
        except Exception:
            continue
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
