"""
CI Vision Tagger — GPT-4o Vision으로 키프레임 분석
→ scene_fit, has_subtitles, brand_fit_score 반환
"""
import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
VISION_API = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = """You are an influencer content analyst for a baby/toddler product brand (Grosmimi / Onzenna).
Analyze video keyframes and return a JSON object with these fields:
- scene_fit: "HIGH" | "MED" | "LOW" (how well does the content match a baby/toddler product brand?)
- has_subtitles: true | false (are there text overlays/subtitles in the video?)
- brand_fit_score: integer 0-10 (overall brand fit; 10=perfect)
- scene_tags: array of strings from ["baby", "toddler", "product_shown", "eating", "outdoor", "indoor", "face_closeup", "text_heavy", "lifestyle"]
- subject_age: "infant" if a baby aged 0-24 months appears, "toddler" if 2-4 years old appears, "child" if 4+ years old appears, "none" if no baby/child visible
- reasoning: one sentence explaining your score

Return ONLY valid JSON, no markdown."""

USER_PROMPT = """These are keyframes (start/middle/end) from an Instagram/TikTok video by a parenting influencer.
Brand context: Grosmimi makes straw cups, training cups, and baby tableware for 6m-3y.
Evaluate brand fit and content characteristics."""


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def analyze_frames(frame_paths: list[Path]) -> dict:
    """GPT-4o Vision으로 키프레임 분석. 결과 dict 반환."""
    if not OPENAI_API_KEY:
        return _default_result("No OPENAI_API_KEY")
    if not frame_paths:
        return _default_result("No frames")

    # 이미지 content 블록 구성
    content = [{"type": "text", "text": USER_PROMPT}]
    for p in frame_paths:
        if p.exists():
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encode_image(p)}",
                    "detail": "low",  # low = $0.000085/image — 충분
                },
            })

    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(VISION_API, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {OPENAI_API_KEY}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
        text = resp["choices"][0]["message"]["content"]
        result = json.loads(text)
        return {
            "scene_fit": result.get("scene_fit", "LOW"),
            "has_subtitles": bool(result.get("has_subtitles", False)),
            "brand_fit_score": int(result.get("brand_fit_score", 0)),
            "scene_tags": result.get("scene_tags", []),
            "subject_age": result.get("subject_age", "none"),
            "reasoning": result.get("reasoning", ""),
        }
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  [VISION] API error {e.code}: {err}")
        return _default_result(f"API error {e.code}")
    except Exception as e:
        print(f"  [VISION] Error: {e}")
        return _default_result(str(e))


def _default_result(reason: str) -> dict:
    return {
        "scene_fit": "LOW",
        "has_subtitles": False,
        "brand_fit_score": 0,
        "scene_tags": [],
        "subject_age": "none",
        "reasoning": reason,
    }
