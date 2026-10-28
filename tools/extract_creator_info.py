"""Extract JP creator display_name (honorific) + child age + recommended product.

Sprint 3 of JP CRM 자동 호칭/월령 추출 시스템 (2026-05-26, 세은 요청).

룰베이스 + LLM 혼합:
- 「○ヶ月」「○歳」 정규식 first (저렴)
- 없으면 Claude API 1 call (haiku 4.5, max 200 tokens)

Output JSON:
    display_name_jp        — DM 호칭 ("おたま様" / fallback "{handle}様")
    child_age_months       — 자녀 월령 (None=미상)
    recommended_product    — ppsu / onetouch / stainless / out_of_scope / unknown
    is_archive_candidate   — True if 24+개월 또는 out_of_scope
    extraction_source      — "llm" / "regex" / "fallback"

Usage:
    python tools/extract_creator_info.py --handle otama_mamalife --bio "おたま|2y boy mama" --captions "8ヶ月の息子"
    echo '{"handle":"x","bio":"y","captions":[]}' | python tools/extract_creator_info.py --stdin --json

워크플로우 룰 (workflows/grosmimi_japan_influencer_dm.md STEP 1):
    〜11ヶ月 → PPSU
    12~23ヶ月 → ワンタッチ
    24+ヶ月 → 対象外 (archive)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

PRODUCT_RULES = [
    (0, 11, "ppsu"),
    (12, 23, "onetouch"),
    (24, 999, "out_of_scope"),
]

AGE_PATTERNS: list[tuple[str, str]] = [
    (r"(\d+)\s*歳\s*(\d+)\s*ヶ月", "Y_M"),
    (r"(\d+)\s*歳\s*(\d+)\s*か月", "Y_M"),
    (r"(\d+)y(\d+)m", "Y_M"),
    (r"(\d+)\s*ヶ月", "M"),
    (r"(\d+)\s*か月", "M"),
    (r"(\d+)\s*month", "M"),
    (r"(\d+)\s*歳", "Y"),
    (r"(\d+)\s*才", "Y"),
    (r"(\d+)y\b", "Y"),
]


def extract_age_regex(text: str) -> int | None:
    for pat, kind in AGE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if not m:
            continue
        try:
            if kind == "M":
                return int(m.group(1))
            if kind == "Y":
                return int(m.group(1)) * 12
            if kind == "Y_M":
                return int(m.group(1)) * 12 + int(m.group(2))
        except (ValueError, IndexError):
            continue
    return None


def classify_product(age: int | None) -> tuple[str, bool]:
    if age is None:
        return ("unknown", False)
    for lo, hi, name in PRODUCT_RULES:
        if lo <= age <= hi:
            return (name, name == "out_of_scope")
    return ("unknown", False)


SYS_PROMPT = """日本のSNSインフルエンサー bio + caption から下記情報を抽出してください。
出力は **必ず 1つの JSON オブジェクト** のみ（説明文・前置きなし）:
{
    "display_name": "...",   // bio から推定された自己紹介の呼称（例: "おたま" / "ゆっち" / "ヒナタママ"）。フルネーム不要。bio に明確な候補がなければ "" を返す。
    "child_age_months": 8    // 子どもの月齢（数値）。複数子の場合は最年少。不明なら null。
}
情報源は bio_text + recent_captions のみ。推測しすぎない。"""


def call_claude(bio_text: str, captions: list[str]) -> dict:
    try:
        from anthropic import Anthropic
    except ImportError:
        return {"display_name": "", "child_age_months": None}
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {"display_name": "", "child_age_months": None}
    client = Anthropic()
    user_msg = json.dumps(
        {"bio_text": bio_text, "recent_captions": captions[:5]},
        ensure_ascii=False,
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=SYS_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*?\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"display_name": "", "child_age_months": None}


def extract(handle: str, bio_text: str, captions: list[str]) -> dict:
    all_text = "\n".join([bio_text] + captions[:5])
    age = extract_age_regex(all_text)
    src = "regex" if age is not None else "llm"

    llm = call_claude(bio_text, captions) if bio_text or captions else {}
    display_name = (llm.get("display_name") or "").strip()
    if age is None:
        age = llm.get("child_age_months")

    product, is_archive = classify_product(age)
    if display_name:
        display_name_jp = f"{display_name}様"
        src = src if src == "regex" else "llm"
    else:
        display_name_jp = f"{handle}様"
        src = "fallback" if src == "llm" else src

    return {
        "creator_handle": handle,
        "display_name_jp": display_name_jp,
        "child_age_months": age,
        "recommended_product": product,
        "is_archive_candidate": is_archive,
        "extraction_source": src,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle")
    ap.add_argument("--bio", default="")
    ap.add_argument("--captions", nargs="*", default=[])
    ap.add_argument("--stdin", action="store_true", help="read {handle,bio,captions} JSON from stdin")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    if args.stdin:
        payload = json.loads(sys.stdin.read())
        handle = payload["handle"]
        bio = payload.get("bio", "")
        captions = payload.get("captions", [])
    else:
        if not args.handle:
            ap.error("--handle 필수 (or --stdin)")
        handle = args.handle
        bio = args.bio
        captions = args.captions

    result = extract(handle, bio, captions)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
