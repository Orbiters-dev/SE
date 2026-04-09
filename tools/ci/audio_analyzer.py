"""
CI Audio Analyzer — Gemini 2.5 Flash native audio tone analysis
================================================================
Analyzes cached audio.mp3 files for voice energy, speech pace,
hook timing, baby audio cues, and overall mood.

Uses google.genai SDK with structured JSON output.

Input:  ci_cache/{username}/{post_id}/audio.mp3
Output: dict with 5 audio signal fields for score_calculator v2
"""

import json
import os
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
TOOLS_DIR = DIR.parent
PROJECT_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Max file size: 20MB (Gemini inline audio limit)
MAX_AUDIO_BYTES = 20 * 1024 * 1024

AUDIO_PROMPT = """\
You are an audio content analyst for short-form social media videos (Instagram Reels, TikTok).
Analyze this audio track and return a JSON object with exactly these fields:

1. voice_energy_score (integer 1-10): How energetic/bright is the speaker's voice?
   1=very monotone/flat, 5=calm/warm, 8=bright/enthusiastic, 10=extremely hyped
2. speech_pace_score (integer 1-10): How fast does the speaker talk?
   1=very slow, 4=moderate/conversational, 7=fast/dynamic, 10=extremely rapid
3. audio_hook_timing (float, seconds): When does the first notable vocal tone shift,
   emphasis, or attention-grabbing moment occur? 0.0 if no clear hook detected.
4. baby_audio_cues (boolean): Are there baby sounds (laughing, crying, babbling, cooing)?
5. audio_mood (string, one of): "bright", "calm", "excited", "neutral"

If the audio has no speech (music only or silent), return default values:
voice_energy_score=5, speech_pace_score=5, audio_hook_timing=0.0,
baby_audio_cues=false, audio_mood="neutral"

Return ONLY valid JSON, no markdown fences.
"""


def _default_audio_result() -> dict:
    """Fallback when Gemini is unavailable or audio is invalid.
    Scores use 0 to signal 'not analyzed' (distinct from valid 1-10 range).
    Downstream consumers (calc_audio_tone) check _source=='default' to skip scoring.
    """
    return {
        "voice_energy_score": 0,
        "speech_pace_score": 0,
        "audio_hook_timing": 0.0,
        "baby_audio_cues": False,
        "audio_mood": "neutral",
        "_source": "default",
    }


def analyze_audio(audio_path: Path, duration_sec: float = 0.0) -> dict:
    """
    Send audio file to Gemini 2.5 Flash for native audio analysis.

    Args:
        audio_path: Path to MP3 file (from ci_cache)
        duration_sec: Video duration in seconds (for context)

    Returns:
        dict with voice_energy_score, speech_pace_score, audio_hook_timing,
        baby_audio_cues, audio_mood, _source
    """
    if not audio_path or not audio_path.exists():
        print(f"  [audio_analyzer] File not found: {audio_path}")
        return _default_audio_result()

    file_size = audio_path.stat().st_size
    if file_size > MAX_AUDIO_BYTES:
        print(f"  [audio_analyzer] File too large ({file_size / 1024 / 1024:.1f}MB > 20MB), skipping")
        return _default_audio_result()

    if file_size == 0:
        print(f"  [audio_analyzer] Empty file, skipping")
        return _default_audio_result()

    if not GEMINI_API_KEY:
        print("  [audio_analyzer] GEMINI_API_KEY not set, returning defaults")
        return _default_audio_result()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        # Read audio bytes
        audio_bytes = audio_path.read_bytes()

        # Build prompt with duration context
        prompt = AUDIO_PROMPT
        if duration_sec > 0:
            prompt += f"\nVideo duration: {duration_sec:.1f} seconds."

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type="audio/mpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        # Parse response
        text = response.text.strip()
        # Strip markdown fences if present (```json ... ``` or ``` ... ```)
        if "```" in text:
            import re
            json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1).strip()
            elif text.startswith("```"):
                text = text.lstrip("`").lstrip("json").strip()
                if text.endswith("```"):
                    text = text[:-3].strip()

        result = json.loads(text)

        # Validate and clamp each field individually
        validated = {"_source": "gemini"}
        try:
            validated["voice_energy_score"] = max(1, min(10, int(result.get("voice_energy_score", 5))))
        except (ValueError, TypeError):
            validated["voice_energy_score"] = 5
        try:
            validated["speech_pace_score"] = max(1, min(10, int(result.get("speech_pace_score", 5))))
        except (ValueError, TypeError):
            validated["speech_pace_score"] = 5
        try:
            validated["audio_hook_timing"] = max(0.0, float(result.get("audio_hook_timing", 0.0)))
        except (ValueError, TypeError):
            validated["audio_hook_timing"] = 0.0
        baby_val = result.get("baby_audio_cues", False)
        if isinstance(baby_val, str):
            baby_val = baby_val.lower() in ("true", "1", "yes")
        validated["baby_audio_cues"] = bool(baby_val)
        mood = result.get("audio_mood", "neutral")
        validated["audio_mood"] = mood if mood in ("bright", "calm", "excited", "neutral") else "neutral"

        return validated

    except json.JSONDecodeError as e:
        print(f"  [audio_analyzer] JSON parse error: {e}")
        return _default_audio_result()
    except Exception as e:
        print(f"  [audio_analyzer] Gemini API error: {e}")
        return _default_audio_result()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CI Audio Analyzer — Gemini audio tone analysis")
    parser.add_argument("--audio", required=True, help="Path to MP3 file")
    parser.add_argument("--duration", type=float, default=0.0, help="Video duration in seconds")
    args = parser.parse_args()

    result = analyze_audio(Path(args.audio), args.duration)
    print(json.dumps(result, indent=2, ensure_ascii=False))
