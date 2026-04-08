"""
CI Score Calculator — Composite scoring for baby product creator fit
====================================================================
Raw CI signals (Vision + Whisper) → Content Quality Score + Creator-Brand Fit Score

Optimized for baby/toddler product brands (Grosmimi, Onzenna, zezebaebae).
Weight rationale: authenticity > hook (mom audience skips ad-like content),
demo & proof heavily weighted (functional products need usage scenes).

v1.0 — Original 2-score (content_quality + creator_fit)
v2.0 — Extended 4-tier framework with 7 new sub-scores:
        duration, comment_quality, posting_frequency, collab_history,
        bot_score, content_consistency, multi_platform
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


# ===========================================================================
# v2.0 — Extended 4-Tier Creator Quality Framework
# ===========================================================================

# Ideal video duration range (seconds)
DURATION_IDEAL_MIN = 20
DURATION_IDEAL_MAX = 60

# Comment quality: minimum meaningful ratio
COMMENT_MEANINGFUL_THRESHOLD = 0.50  # 50% of comments should be meaningful

# Posting frequency: ideal range (posts per week)
POSTING_FREQ_IDEAL_MIN = 2
POSTING_FREQ_IDEAL_MAX = 7

# Brand collab sweet spot
COLLAB_IDEAL_MIN = 1
COLLAB_IDEAL_MAX = 5  # 0 = no experience, 10+ = too ad-heavy

# Bot/fake follower ER thresholds
BOT_ER_SUSPICIOUS_LOW = 0.5   # ER < 0.5% with 10K+ followers = suspicious
BOT_ER_SUSPICIOUS_HIGH = 20.0  # ER > 20% = likely engagement pods


def calc_duration_score(duration_seconds: float) -> dict:
    """
    TIER 2: Video duration scoring.
    Ideal: 20-60 seconds for baby product reels.
    Returns 0-10 score + tier label.
    """
    if not duration_seconds or duration_seconds <= 0:
        return {"duration_score": 0, "duration_tier": "unknown"}

    d = duration_seconds
    if DURATION_IDEAL_MIN <= d <= DURATION_IDEAL_MAX:
        score = 10
        tier = "ideal"
    elif 15 <= d < DURATION_IDEAL_MIN:
        score = 7
        tier = "slightly_short"
    elif DURATION_IDEAL_MAX < d <= 90:
        score = 7
        tier = "slightly_long"
    elif 10 <= d < 15:
        score = 4
        tier = "too_short"
    elif 90 < d <= 180:
        score = 5
        tier = "long"
    elif d > 180:
        score = 2
        tier = "too_long"
    else:
        score = 1
        tier = "too_short"

    return {"duration_score": score, "duration_tier": tier}


def calc_comment_quality(total_comments: int, meaningful_comments: int,
                         bot_comments: int = 0) -> dict:
    """
    TIER 3A: Comment quality scoring.
    meaningful = non-emoji, non-tag-only, >3 words
    bot_comments = detected spam/bot comments
    Returns 0-10 score.
    """
    if not total_comments or total_comments == 0:
        return {"comment_quality_score": 0, "meaningful_ratio": 0.0,
                "bot_comment_ratio": 0.0}

    meaningful_ratio = round(meaningful_comments / total_comments, 2)
    bot_ratio = round(bot_comments / total_comments, 2) if bot_comments else 0.0

    # Score: meaningful ratio drives it, bot ratio penalizes
    base = min(meaningful_ratio * 10, 10)
    penalty = bot_ratio * 5  # up to -5 for 100% bot
    score = max(0, int(base - penalty))

    return {
        "comment_quality_score": score,
        "meaningful_ratio": meaningful_ratio,
        "bot_comment_ratio": bot_ratio,
    }


def calc_posting_frequency(posts_last_30d: int) -> dict:
    """
    TIER 4: Posting frequency scoring.
    Ideal: 2-7 posts/week = 8-28 posts/30d.
    """
    if posts_last_30d is None or posts_last_30d < 0:
        return {"frequency_score": 0, "posts_per_week": 0.0, "frequency_tier": "unknown"}

    ppw = round(posts_last_30d / 4.3, 1)  # posts per week

    if POSTING_FREQ_IDEAL_MIN <= ppw <= POSTING_FREQ_IDEAL_MAX:
        score = 10
        tier = "ideal"
    elif 1 <= ppw < POSTING_FREQ_IDEAL_MIN:
        score = 6
        tier = "low"
    elif POSTING_FREQ_IDEAL_MAX < ppw <= 14:
        score = 7
        tier = "high"
    elif ppw > 14:
        score = 4
        tier = "spam"
    else:  # ppw < 1
        score = 2
        tier = "dormant"

    return {"frequency_score": score, "posts_per_week": ppw, "frequency_tier": tier}


def calc_collab_history(sponsored_count: int, total_posts_checked: int = 30) -> dict:
    """
    TIER 4: Brand collaboration history.
    1-5 collabs per 30 posts = experienced but not oversaturated.
    0 = no experience (risky), 10+ = ad-heavy (audience fatigue).
    """
    if total_posts_checked <= 0:
        return {"collab_score": 0, "collab_ratio": 0.0, "collab_tier": "unknown"}

    ratio = round(sponsored_count / total_posts_checked, 2)

    if COLLAB_IDEAL_MIN <= sponsored_count <= COLLAB_IDEAL_MAX:
        score = 10
        tier = "experienced"
    elif sponsored_count == 0:
        score = 5
        tier = "no_experience"
    elif 6 <= sponsored_count <= 10:
        score = 6
        tier = "frequent"
    else:  # >10
        score = 3
        tier = "oversaturated"

    return {"collab_score": score, "collab_ratio": ratio, "collab_tier": tier}


def calc_bot_score(followers: int, avg_likes: float, avg_comments: float,
                   follower_growth_30d: float = None) -> dict:
    """
    TIER 3B: Bot/fake follower detection heuristic.
    Uses engagement rate anomalies + follower growth spikes.
    Returns 0-10 credibility score (10 = very credible, 0 = likely fake).
    """
    if not followers or followers <= 0:
        return {"credibility_score": 0, "bot_risk": "unknown",
                "er_check": "no_data"}

    er = round((avg_likes + avg_comments) / followers * 100, 2) if followers > 0 else 0

    # Start at 10, deduct for red flags
    score = 10

    # ER anomaly checks
    if followers >= 10000 and er < BOT_ER_SUSPICIOUS_LOW:
        score -= 4  # very low ER for follower count = bought followers
        er_check = "suspiciously_low"
    elif er > BOT_ER_SUSPICIOUS_HIGH:
        score -= 3  # engagement pods or bot likes
        er_check = "suspiciously_high"
    elif followers >= 50000 and er < 1.0:
        score -= 2
        er_check = "low_for_size"
    else:
        er_check = "normal"

    # Follower growth spike
    if follower_growth_30d is not None:
        if follower_growth_30d > 50:  # >50% growth in 30d = suspicious
            score -= 3
        elif follower_growth_30d > 20:
            score -= 1

    score = max(0, min(10, score))
    risk = "high" if score <= 3 else ("medium" if score <= 6 else "low")

    return {
        "credibility_score": score,
        "bot_risk": risk,
        "er_check": er_check,
        "effective_er": er,
    }


def calc_content_consistency(quality_scores: list) -> dict:
    """
    TIER 4: Content consistency across recent posts.
    Input: list of content_quality_scores from recent N posts.
    Low variance = consistent quality. High variance = unreliable.
    """
    if not quality_scores or len(quality_scores) < 2:
        return {"consistency_score": 0, "quality_std": 0.0,
                "quality_mean": 0.0, "consistency_tier": "insufficient_data"}

    n = len(quality_scores)
    mean = sum(quality_scores) / n
    variance = sum((x - mean) ** 2 for x in quality_scores) / n
    std = variance ** 0.5

    # Low std = high consistency score
    if std <= 5:
        score = 10
        tier = "very_consistent"
    elif std <= 10:
        score = 8
        tier = "consistent"
    elif std <= 15:
        score = 6
        tier = "moderate"
    elif std <= 20:
        score = 4
        tier = "inconsistent"
    else:
        score = 2
        tier = "very_inconsistent"

    return {
        "consistency_score": score,
        "quality_std": round(std, 1),
        "quality_mean": round(mean, 1),
        "consistency_tier": tier,
    }


def calc_multi_platform(platforms: list) -> dict:
    """
    TIER 4: Multi-platform presence.
    Input: list of platforms where creator is active (e.g., ["instagram", "tiktok"])
    """
    if not platforms:
        return {"platform_score": 0, "platform_count": 0}

    unique = list(set(p.lower().strip() for p in platforms if p))
    count = len(unique)

    if count >= 3:
        score = 10
    elif count == 2:
        score = 8
    else:
        score = 4

    return {"platform_score": score, "platform_count": count, "platforms": unique}


def calculate_scores_v2(ci_results: dict, followers: int = 0,
                        views: int = 0, likes: int = 0, comments: int = 0,
                        enrichment: dict = None) -> dict:
    """
    v2 Main entry point: raw CI signals + enrichment data → full framework scores.

    Args:
        ci_results: merged dict from vision_tagger + whisper_transcriber
        followers: creator's follower count
        views/likes/comments: post engagement metrics
        enrichment: dict with optional keys:
            - duration_seconds: float
            - total_comments: int, meaningful_comments: int, bot_comments: int
            - posts_last_30d: int
            - sponsored_count: int, total_posts_checked: int
            - avg_likes: float, avg_comments: float
            - follower_growth_30d: float
            - quality_scores_history: list[int]
            - platforms: list[str]

    Returns:
        Full scoring dict with v1 scores + all v2 sub-scores + composite
    """
    enrichment = enrichment or {}

    # v1 scores (backward compatible)
    v1 = calculate_scores(ci_results, followers, views, likes, comments)

    # --- TIER 2: Content Specs ---
    duration = calc_duration_score(enrichment.get("duration_seconds", 0))

    # --- TIER 3A: Engagement Quality ---
    comment_q = calc_comment_quality(
        enrichment.get("total_comments", comments),
        enrichment.get("meaningful_comments", 0),
        enrichment.get("bot_comments", 0),
    )

    # --- TIER 3B: Audience Quality ---
    bot = calc_bot_score(
        followers,
        enrichment.get("avg_likes", likes),
        enrichment.get("avg_comments", comments),
        enrichment.get("follower_growth_30d"),
    )

    # --- TIER 4: Performance ---
    frequency = calc_posting_frequency(enrichment.get("posts_last_30d", 0))
    collab = calc_collab_history(
        enrichment.get("sponsored_count", 0),
        enrichment.get("total_posts_checked", 30),
    )
    consistency = calc_content_consistency(
        enrichment.get("quality_scores_history", []),
    )
    multi_plat = calc_multi_platform(enrichment.get("platforms", []))

    # --- Composite v2 score ---
    # Weighted blend: Content (40%) + Creator Fit (30%) + Audience (15%) + Performance (15%)
    tier_scores = {
        "content": v1["content_quality_score"],  # 0-100
        "fit": v1["creator_fit_score"],           # 0-100
        "audience": _clamp(
            bot["credibility_score"] * 10,  # 0-100
        ),
        "performance": _clamp(
            (frequency["frequency_score"] * 3 +
             collab["collab_score"] * 2 +
             consistency["consistency_score"] * 3 +
             multi_plat["platform_score"] * 2) ,  # max 10*3+10*2+10*3+10*2 = 100
        ),
    }

    composite_v2 = _clamp(
        tier_scores["content"] * 0.40 +
        tier_scores["fit"] * 0.30 +
        tier_scores["audience"] * 0.15 +
        tier_scores["performance"] * 0.15
    )

    return {
        # v1 backward compatible
        **v1,
        # v2 sub-scores
        "duration": duration,
        "comment_quality": comment_q,
        "bot_detection": bot,
        "posting_frequency": frequency,
        "collab_history": collab,
        "content_consistency": consistency,
        "multi_platform": multi_plat,
        # v2 tier scores (0-100 each)
        "tier_scores": tier_scores,
        # v2 composite
        "composite_v2_score": composite_v2,
        "scoring_version": "v2.0",
    }


# ---------------------------------------------------------------------------
# Creator Quality Evaluation Framework (Tier 1-4)
# Maps to the spreadsheet-based evaluation framework
# ---------------------------------------------------------------------------

def calculate_tier_framework(
    ci_results: dict,
    screening: dict = None,
    enrichment: dict = None,
    v2_scores: dict = None,
) -> dict:
    """
    크리에이터 품질 평가 프레임워크 4-Tier 종합 판정.

    Args:
        ci_results: vision_tagger + whisper output
        screening: lt_screener.screen() 결과 {"metrics": {...}}
        enrichment: enricher.py 출력
        v2_scores: calculate_scores_v2() 결과 (있으면 재활용)

    Returns:
        {
            "tier1_pass": bool,
            "tier1_details": {...},
            "tier2_score": int (0-100),
            "tier3a_score": int (0-100),
            "tier3b_score": int (0-100),
            "tier4_score": int (0-100),
            "framework_composite": int (0-100),
        }
    """
    screening = screening or {}
    enrichment = enrichment or {}
    metrics = screening.get("metrics", {})

    # === TIER 1: Pass/Fail (필수조건) ===
    # 아기 등장 여부
    baby_present = ci_results.get("subject_age", "none") in ("infant", "toddler")
    # 카테고리 적합도 60%+
    category_ok = metrics.get("category_score", 0) >= 0.60
    # 제품 경험 (오가닉 콘텐츠)
    product_exp = bool(ci_results.get("product_mention", False) or ci_results.get("demo_present", False))

    tier1_pass = baby_present and category_ok
    # product_exp는 soft fail (감점만)

    tier1_details = {
        "baby_present": baby_present,
        "category_fit": category_ok,
        "product_experience": product_exp,
    }

    # === TIER 2: 콘텐츠 기준 (0-100) ===
    t2 = 0
    # 영상 길이 20-30초 이상 (20점)
    dur = enrichment.get("duration_seconds", 0)
    if 20 <= dur <= 60:
        t2 += 20
    elif 15 <= dur < 20 or 60 < dur <= 90:
        t2 += 15
    elif dur > 0:
        t2 += 5

    # Hook 유형 — 브랜드 미등장의 매력적인 Hook (20점)
    hook_score = ci_results.get("hook_score", 0)
    t2 += min(hook_score * 2, 20)

    # 자막 필수 (20점)
    if ci_results.get("has_subtitles", False):
        t2 += 20

    # 음악/오디오 (20점) — Whisper transcript 존재 = 음성 있음
    has_audio = bool(ci_results.get("transcript") or ci_results.get("persuasion_type"))
    if has_audio:
        t2 += 20

    # 제품 등장 (20점)
    if ci_results.get("demo_present", False):
        t2 += 20

    tier2_score = _clamp(t2)

    # === TIER 3A: 엔게이지먼트 품질 (0-100) ===
    t3a = 0
    # ER 기준 (50점)
    er = metrics.get("er", 0)
    followers = metrics.get("followers", enrichment.get("followers", 0))
    if followers < 100_000:
        # micro: 3-8%
        if er >= 0.08:
            t3a += 50
        elif er >= 0.05:
            t3a += 40
        elif er >= 0.03:
            t3a += 30
        elif er >= 0.01:
            t3a += 15
    else:
        # mid: 1-3%
        if er >= 0.03:
            t3a += 50
        elif er >= 0.02:
            t3a += 40
        elif er >= 0.01:
            t3a += 30

    # 댓글 품질 50%+ 유의미 (50점)
    meaningful = enrichment.get("meaningful_comments", 0)
    total_comments = enrichment.get("total_comments", 0)
    if total_comments > 0:
        meaningful_ratio = meaningful / total_comments
        t3a += _clamp(int(meaningful_ratio * 50), 0, 50)
    else:
        t3a += 25  # 데이터 없으면 중립

    tier3a_score = _clamp(t3a)

    # === TIER 3B: 오디언스 구성 (0-100) ===
    t3b = 0
    # 팔로워 위치 (25점) — 현재 자동화 불가, 중립값
    t3b += 15

    # 연령대 (25점) — 현재 자동화 불가, 중립값
    t3b += 15

    # 봇/비활성 15% 미만 (25점)
    if v2_scores:
        bot_info = v2_scores.get("bot_detection", {})
        bot_risk = bot_info.get("bot_risk", "medium")
        if bot_risk == "low":
            t3b += 25
        elif bot_risk == "medium":
            t3b += 15
        # high = 0

    # 성장 패턴 (25점) — 급증 없는 오가닉 성장
    growth = enrichment.get("follower_growth_30d")
    if growth is not None:
        if 0 < growth <= 0.10:  # 10% 이하 자연 성장
            t3b += 25
        elif 0.10 < growth <= 0.20:
            t3b += 15
        elif growth > 0.50:  # 급증 = 의심
            t3b += 0
        else:
            t3b += 10
    else:
        t3b += 12  # 데이터 없으면 중립

    tier3b_score = _clamp(t3b)

    # === TIER 4: 성과지표 (0-100) ===
    t4 = 0
    # 포스팅 빈도 주 3회+ (20점)
    posts_30d = metrics.get("posts_30d", enrichment.get("posts_last_30d", 0))
    if posts_30d >= 12:
        t4 += 20
    elif posts_30d >= 8:
        t4 += 15
    elif posts_30d >= 4:
        t4 += 10

    # UGC 품질 — 밝고 깔끔 (20점)
    auth = ci_results.get("authenticity_score", 0)
    t4 += min(auth * 2, 20)

    # 브랜드 협업 이력 1-3회 (20점)
    sponsored = enrichment.get("sponsored_count", 0)
    if 1 <= sponsored <= 3:
        t4 += 20
    elif 4 <= sponsored <= 6:
        t4 += 15
    elif sponsored == 0:
        t4 += 5  # 미검증
    # 10+ = 피로, 0점

    # 멀티플랫폼 IG + TikTok (20점)
    platforms = enrichment.get("platforms", [])
    if len(platforms) >= 2:
        t4 += 20
    elif len(platforms) == 1:
        t4 += 10

    # 콘텐츠 일관성 (20점)
    if v2_scores:
        cons = v2_scores.get("content_consistency", {})
        cons_score = cons.get("consistency_score", 5)
        t4 += min(cons_score * 2, 20)
    else:
        t4 += 10  # 중립

    tier4_score = _clamp(t4)

    # === Composite ===
    # T1은 pass/fail, T2-T4는 가중 합산
    if tier1_pass:
        framework_composite = _clamp(
            tier2_score * 0.30 +
            tier3a_score * 0.25 +
            tier3b_score * 0.20 +
            tier4_score * 0.25
        )
    else:
        framework_composite = 0  # T1 탈락이면 0

    return {
        "tier1_pass": tier1_pass,
        "tier1_details": tier1_details,
        "tier2_score": tier2_score,
        "tier3a_score": tier3a_score,
        "tier3b_score": tier3b_score,
        "tier4_score": tier4_score,
        "framework_composite": framework_composite,
    }
