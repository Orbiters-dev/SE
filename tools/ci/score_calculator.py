"""
CI Score Calculator — Composite scoring for baby product creator fit
====================================================================
Raw CI signals (Vision + Whisper) → Content Quality Score + Creator-Brand Fit Score

Optimized for baby/toddler product brands (Grosmimi, Onzenna, zezebaebae).
Weight rationale: authenticity > hook (mom audience skips ad-like content),
demo & proof heavily weighted (functional products need usage scenes).

Scoring version: v1.0
"""

# ---------------------------------------------------------------------------
# Emotional tone bonuses (baby niche calibrated)
# ---------------------------------------------------------------------------
TONE_BONUS = {
    "warm": 15,
    "funny": 15,
    "emotional": 12,
    "educational": 10,
    "casual": 8,
    "dramatic": 5,
    "aspirational": 5,
}

# Script structure bonuses
STRUCTURE_BONUS = {
    "hook_value_cta": 5,
    "story_arc": 3,
    "demo_narration": 4,
    "list_tips": 2,
    "vlog_casual": 1,
    "no_speech": 0,
}

# Follower band scoring (nano/micro preferred for seeding)
FOLLOWER_BANDS = [
    (10_000, 25),       # nano: 1-10K → 25pt
    (100_000, 20),      # micro: 10-100K → 20pt
    (500_000, 15),      # mid: 100-500K → 15pt
    (float("inf"), 10), # macro: 500K+ → 10pt
]


def _clamp(val, lo=0, hi=100):
    return max(lo, min(hi, int(val)))


def calc_content_quality(signals: dict) -> int:
    """
    Content Quality Score (0-100)

    Weights (baby niche optimized):
      Authenticity & Tone  35%  — mom audience trusts real > polished
      Storytelling          25%  — daily routine integration narrative
      Hook Power           20%  — cute baby moments = natural hook
      Delivery             20%  — vocal + visual delivery
    """
    # Authenticity & Tone (35pt max)
    authenticity = min(signals.get("authenticity_score", 0) * 2.0, 20)
    tone = TONE_BONUS.get(signals.get("emotional_tone", ""), 0)
    auth_tone = authenticity + tone  # max 20 + 15 = 35

    # Storytelling (25pt max)
    story = min(signals.get("storytelling_score", 0) * 2.0, 20)
    structure = STRUCTURE_BONUS.get(signals.get("script_structure", ""), 0)
    storytelling = story + structure  # max 20 + 5 = 25

    # Hook Power (20pt max)
    hook = min(signals.get("hook_score", 0) * 1.5, 15)
    subtitle_bonus = 5 if signals.get("has_subtitles") else 0
    hook_power = hook + subtitle_bonus  # max 15 + 5 = 20

    # Delivery (20pt max)
    delivery_vis = min(signals.get("delivery_score", 0) * 1.0, 10)
    delivery_verb = min(signals.get("delivery_verbal_score", 0) * 1.0, 10)
    delivery = delivery_vis + delivery_verb  # max 10 + 10 = 20

    return _clamp(auth_tone + storytelling + hook_power + delivery)


def calc_creator_fit(signals: dict, followers: int = 0) -> int:
    """
    Creator-Brand Fit Score (0-100)

    Weights (baby product seeding optimized):
      Brand Relevance  30%  — brand_fit_score + product mention
      Demo & Proof     25%  — product usage scene + baby present
      Audience Match   25%  — follower band (nano/micro preferred)
      Content Virality 20%  — engagement rate + virality coefficient
    """
    # Brand Relevance (30pt max)
    brand_fit = min(signals.get("brand_fit_score", 0) * 2.0, 20)
    product_bonus = 10 if signals.get("product_mention") else 0
    brand_relevance = brand_fit + product_bonus  # max 20 + 10 = 30

    # Demo & Proof (25pt max)
    demo_bonus = 15 if signals.get("demo_present") else 0
    age = signals.get("subject_age", "none")
    age_bonus = 10 if age in ("infant", "toddler") else (5 if age == "child" else 0)
    demo_proof = demo_bonus + age_bonus  # max 15 + 10 = 25

    # Audience Match (25pt max)
    follower_score = 10  # default for unknown
    if followers and followers > 0:
        for threshold, score in FOLLOWER_BANDS:
            if followers <= threshold:
                follower_score = score
                break
    audience = follower_score  # max 25

    # Content Virality (20pt max)
    er = signals.get("engagement_rate", 0) or 0
    vc = signals.get("virality_coeff", 0) or 0
    watchability = signals.get("repeat_watchability", 0) or 0

    er_score = min(er * 4, 12)          # ER 3% → 12pt cap
    vc_score = min(vc * 2, 8)           # virality coeff 4x → 8pt cap
    virality = er_score + vc_score      # max 12 + 8 = 20

    # Bonus: repeat_watchability as tiebreaker (up to +5, doesn't exceed 100)
    watchability_bonus = min(watchability * 0.5, 5)

    return _clamp(brand_relevance + demo_proof + audience + virality + watchability_bonus)


def calc_engagement_metrics(views: int, likes: int, comments: int, followers: int) -> dict:
    """Calculate engagement rate and virality coefficient from raw metrics."""
    engagement_rate = 0.0
    virality_coeff = 0.0

    if views and views > 0:
        engagement_rate = round((likes + comments) / views * 100, 2)
    if followers and followers > 0:
        virality_coeff = round(views / followers, 2)

    return {
        "engagement_rate": engagement_rate,
        "virality_coeff": virality_coeff,
    }


def calculate_scores(ci_results: dict, followers: int = 0,
                     views: int = 0, likes: int = 0, comments: int = 0) -> dict:
    """
    Main entry point: raw CI signals → composite scores.

    Args:
        ci_results: merged dict from vision_tagger + whisper_transcriber
        followers: creator's follower count (for audience match)
        views/likes/comments: post engagement metrics

    Returns:
        dict with engagement_rate, virality_coeff,
        content_quality_score, creator_fit_score, scoring_version
    """
    # Engagement metrics
    eng = calc_engagement_metrics(views, likes, comments, followers)
    ci_results["engagement_rate"] = eng["engagement_rate"]
    ci_results["virality_coeff"] = eng["virality_coeff"]

    content_quality = calc_content_quality(ci_results)
    creator_fit = calc_creator_fit(ci_results, followers)

    return {
        "engagement_rate": eng["engagement_rate"],
        "virality_coeff": eng["virality_coeff"],
        "content_quality_score": content_quality,
        "creator_fit_score": creator_fit,
        "scoring_version": "v1.0",
    }
