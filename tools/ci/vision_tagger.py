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

SYSTEM_PROMPT = """You are an expert influencer content analyst for a baby/toddler product brand (Grosmimi / Onzenna).
Analyze video keyframes and return a JSON object with ALL these fields:

BRAND FIT:
- scene_fit: "HIGH" | "MED" | "LOW"
- brand_fit_score: integer 0-10 (10=perfect match for baby product brand)
- scene_tags: array from ["baby", "toddler", "product_shown", "eating", "outdoor", "indoor", "face_closeup", "text_heavy", "lifestyle", "tutorial", "before_after", "unboxing"]
- subject_age: "infant" (0-24m) | "toddler" (2-4y) | "child" (4y+) | "none"

CONTENT QUALITY (HVA Framework):
- hook_score: integer 1-10 (how compelling is the opening frame? Would viewers stop scrolling?)
- hook_type: "question" | "shocking" | "relatable" | "tutorial" | "before_after" | "aesthetic" | "text_hook" | "other"
- storytelling_score: integer 1-10 (narrative arc, emotional journey, structure)
- authenticity_score: integer 1-10 (natural/real-life feel vs over-produced/ad-like)
- has_subtitles: true | false

DELIVERY & PERSUASION:
- delivery_score: integer 1-10 (vocal clarity, pacing, confidence, warmth — judge from visual cues like expressions, gestures, subtitle style)
- emotional_tone: "warm" | "funny" | "educational" | "dramatic" | "aspirational" | "casual" | "emotional"
- demo_present: true | false (product demonstration / usage scene visible?)
- cta_present: true | false (call to action: follow, link, comment prompt)

- reasoning: one sentence summarizing overall content quality

Return ONLY valid JSON, no markdown."""

USER_PROMPT_LT = """These are keyframes from an Instagram/TikTok video by a parenting influencer.
Brand context: Grosmimi makes straw cups, training cups, and baby tableware for 6m-3y.
Evaluate brand fit and content characteristics."""

USER_PROMPT_HT = """These are keyframes from an Instagram/TikTok video by a parenting influencer.
The first few frames are the HOOK zone (first 3 seconds). Remaining frames show the full content.
Brand context: Grosmimi makes straw cups, training cups, and baby tableware for 6m-3y.

Evaluate brand fit and content quality. For HT/DY analysis, also assess:
- product_visibility_score: 0-10 (how clearly/frequently is the product shown throughout the video)
- production_quality: "high" | "medium" | "low" (lighting, framing, editing quality)
- thumbnail_appeal: 0-10 (would the first frame make someone click?)
- text_overlay_content: extract any visible text overlays from the frames
- product_center_pct: integer 0-100 (what percentage of ALL frames show the product prominently in the center of the frame?)
- product_first_appearance_pct: integer 0-100 (at what point in the video does the product FIRST appear? Express as percentage of video length. 0=very start, 100=very end, -1=never shown)
- child_appearance_pct: integer 0-100 (what percentage of ALL frames show a baby/toddler/child?)
- main_question: string (the central thesis, question, or hook premise of this content — one sentence, e.g. "We tried 12 sippy cups and this is the only one she uses")"""


def encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def analyze_frames(frame_paths: list[Path], tier: str = "LT") -> dict:
    """GPT-4o Vision으로 키프레임 분석. 결과 dict 반환.

    Args:
        frame_paths: 키프레임 경로 리스트 (LT: ~10장, HT: ~30장)
        tier: "LT" or "HT" — HT는 확장 프롬프트 + 추가 필드
    """
    if not OPENAI_API_KEY:
        return _default_result("No OPENAI_API_KEY")
    if not frame_paths:
        return _default_result("No frames")

    user_prompt = USER_PROMPT_HT if tier.upper() in ("HT", "DY") else USER_PROMPT_LT

    # 이미지 content 블록 구성
    content = [{"type": "text", "text": user_prompt}]
    for p in frame_paths:
        if p.exists():
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{encode_image(p)}",
                    "detail": "low",  # low = $0.000085/image — 충분
                },
            })

    max_tokens = 900 if tier.upper() in ("HT", "DY") else 500

    payload = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "max_tokens": max_tokens,
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
        parsed = {
            "scene_fit": result.get("scene_fit", "LOW"),
            "has_subtitles": bool(result.get("has_subtitles", False)),
            "brand_fit_score": int(result.get("brand_fit_score", 0)),
            "scene_tags": result.get("scene_tags", []),
            "subject_age": result.get("subject_age", "none"),
            "hook_score": int(result.get("hook_score", 0)),
            "hook_type": result.get("hook_type", "other"),
            "storytelling_score": int(result.get("storytelling_score", 0)),
            "authenticity_score": int(result.get("authenticity_score", 0)),
            "delivery_score": int(result.get("delivery_score", 0)),
            "emotional_tone": result.get("emotional_tone", "casual"),
            "demo_present": bool(result.get("demo_present", False)),
            "cta_present": bool(result.get("cta_present", False)),
            "reasoning": result.get("reasoning", ""),
        }
        # HT/DY 추가 필드
        if tier.upper() in ("HT", "DY"):
            parsed["product_visibility_score"] = int(result.get("product_visibility_score", 0))
            parsed["production_quality"] = result.get("production_quality", "medium")
            parsed["thumbnail_appeal"] = int(result.get("thumbnail_appeal", 0))
            parsed["text_overlay_content"] = result.get("text_overlay_content", "")
            parsed["product_center_pct"] = int(result.get("product_center_pct", 0))
            parsed["product_first_appearance_pct"] = int(result.get("product_first_appearance_pct", -1))
            parsed["child_appearance_pct"] = int(result.get("child_appearance_pct", 0))
            parsed["main_question"] = result.get("main_question", "")
        return parsed
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
        "hook_score": 0,
        "hook_type": "other",
        "storytelling_score": 0,
        "authenticity_score": 0,
        "delivery_score": 0,
        "emotional_tone": "casual",
        "demo_present": False,
        "cta_present": False,
        "reasoning": reason,
    }
