"""
CI Whisper — OpenAI Whisper API로 음성→텍스트 + 제품 키워드 감지
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
WHISPER_API = "https://api.openai.com/v1/audio/transcriptions"

# JP 제품 키워드 (Whisper transcript에서 감지)
JP_KEYWORDS = {
    "grosmimi", "グロスミミ", "ぐろみみ",
    "onzenna", "オンゼンナ",
    "ストローカップ", "ストロー", "離乳食", "マグカップ",
    "zezebaebae", "ゼゼベベ",
}

US_KEYWORDS = {
    "grosmimi", "onzenna", "straw cup", "training cup",
    "sippy cup", "baby bottle", "zezebaebae",
}


def transcribe(audio_path: Path, language: str = "ja") -> str | None:
    """mp3 파일을 Whisper API로 텍스트화."""
    if not OPENAI_API_KEY:
        print("  [WHISPER] No OPENAI_API_KEY")
        return None
    if not audio_path or not audio_path.exists():
        print("  [WHISPER] No audio file")
        return None

    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 24:
        print(f"  [WHISPER] File too large ({file_size_mb:.1f}MB)")
        return None

    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    boundary = "WbBoundary12345"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="language"\r\n\r\n{language}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audio.mp3"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    ).encode() + audio_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(WHISPER_API, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {OPENAI_API_KEY}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read())
        return result.get("text", "").strip()
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  [WHISPER] API error {e.code}: {body_err}")
        return None
    except Exception as e:
        print(f"  [WHISPER] Error: {e}")
        return None


def detect_product_mention(transcript: str, region: str = "jp") -> bool:
    """transcript에서 제품 키워드 감지."""
    if not transcript:
        return False
    keywords = JP_KEYWORDS if region == "jp" else US_KEYWORDS
    text_lower = transcript.lower()
    return any(kw.lower() in text_lower for kw in keywords)


SCRIPT_ANALYSIS_API = "https://api.openai.com/v1/chat/completions"

SCRIPT_SYSTEM = """You are an expert influencer script analyst for baby/toddler brands.
Analyze the transcript and return JSON with:

- delivery_verbal_score: integer 1-10 (vocal pacing, natural flow, conversational vs scripted)
- hook_text: string (the first sentence/phrase that hooks the viewer — extract verbatim from transcript)
- persuasion_type: "social_proof" | "personal_story" | "problem_solution" | "educational" | "aesthetic_only" | "humor" | "emotional_appeal"
- key_message: string (one-sentence core message of the video)
- script_structure: "hook_value_cta" | "story_arc" | "list_tips" | "demo_narration" | "vlog_casual" | "no_speech"
- vocabulary_level: "simple" | "conversational" | "professional" (audience accessibility)
- repeat_watchability: integer 1-10 (would someone share or rewatch this?)

Return ONLY valid JSON."""

SCRIPT_USER = """Transcript from a {lang} parenting/baby influencer video:

\"\"\"{transcript}\"\"\"

Analyze the script quality, delivery style, and persuasion effectiveness."""


def analyze_script(transcript: str, language: str = "ja") -> dict:
    """Transcript 기반 대사/스크립트 분석."""
    if not OPENAI_API_KEY or not transcript or len(transcript.strip()) < 10:
        return _default_script()

    lang = "Japanese" if language == "ja" else "English"
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SCRIPT_SYSTEM},
            {"role": "user", "content": SCRIPT_USER.format(transcript=transcript[:2000], lang=lang)},
        ],
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(SCRIPT_ANALYSIS_API, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {OPENAI_API_KEY}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            resp = json.loads(r.read())
        result = json.loads(resp["choices"][0]["message"]["content"])
        return {
            "delivery_verbal_score": int(result.get("delivery_verbal_score", 0)),
            "hook_text": result.get("hook_text", ""),
            "persuasion_type": result.get("persuasion_type", "aesthetic_only"),
            "key_message": result.get("key_message", ""),
            "script_structure": result.get("script_structure", "no_speech"),
            "vocabulary_level": result.get("vocabulary_level", "simple"),
            "repeat_watchability": int(result.get("repeat_watchability", 0)),
        }
    except Exception as e:
        print(f"  [SCRIPT] Error: {e}")
        return _default_script()


def _default_script() -> dict:
    return {
        "delivery_verbal_score": 0,
        "hook_text": "",
        "persuasion_type": "aesthetic_only",
        "key_message": "",
        "script_structure": "no_speech",
        "vocabulary_level": "simple",
        "repeat_watchability": 0,
    }
