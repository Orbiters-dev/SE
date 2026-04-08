"""
CI LT Screener — Light Touch 자동 스크리닝

Apify JSON 캐시(프로필 + 포스트)에서 로컬 필터링. API 비용 $0.

필터:
  1. 팔로워 범위: 1K~500K
  2. ER: micro(<100K) >= 3%, mid(100K+) >= 1%
  3. 카테고리 적합도: 육아 키워드 40%+ (캡션+해시태그+바이오)
  4. 포스팅 빈도: 30일 내 4개+
  5. 영상 비율: 최근 포스트 중 30%+ 영상
  6. 봇 의심: ER > 20% 탈락

Usage:
    from tools.ci.lt_screener import LTScreener
    screener = LTScreener(region="us")
    result = screener.screen(profile, posts)
"""
from datetime import datetime, timedelta


# ── 카테고리 키워드 ──

CATEGORY_KEYWORDS = {
    "us": {
        # 핵심 (가중치 2x)
        "core": {
            "baby", "toddler", "infant", "newborn", "momlife", "motherhood",
            "parenting", "mama", "mommy", "dadlife", "babyfood", "babyfeeding",
            "breastfeeding", "sippy cup", "straw cup", "training cup",
            "baby bottle", "baby led weaning", "blw", "nursery",
        },
        # 관련 (가중치 1x)
        "related": {
            "family", "kid", "kids", "child", "children", "pregnant",
            "pregnancy", "maternity", "nap", "sleep training", "teething",
            "diaper", "formula", "puree", "milestone", "firstfood",
            "toddlerfood", "toddlerlife", "momhack", "parentingtips",
            "sahm", "workingmom", "boymom", "girlmom", "twinmom",
            "montessori", "sensory play", "daycare", "preschool",
        },
    },
    "jp": {
        "core": {
            "育児", "赤ちゃん", "離乳食", "ママ", "子育て", "ベビー",
            "新米ママ", "育児ママ", "ストローマグ", "ベビーマグ",
            "マグデビュー", "ストロー練習", "ベビー用品", "育児グッズ",
            "離乳食初期", "離乳食中期", "離乳食後期", "完了期",
            "母乳", "ミルク", "哺乳瓶",
        },
        "related": {
            "家族", "子供", "キッズ", "妊娠", "妊婦", "マタニティ",
            "ねんトレ", "歯固め", "おむつ", "保育園", "幼稚園",
            "赤ちゃんのいる生活", "ワーママ", "専業主婦",
            "男の子ママ", "女の子ママ", "双子ママ",
            "モンテッソーリ", "知育", "食育",
        },
    },
}

# 제외 키워드 (이게 있으면 감점)
EXCLUDE_KEYWORDS = {
    "casino", "crypto", "forex", "mlm", "dropship", "onlyfans",
    "カジノ", "仮想通貨", "投資", "副業",
}


class LTScreener:
    """LT 자동 스크리닝 필터."""

    # 기본 임계값
    MIN_FOLLOWER = 1_000
    MAX_FOLLOWER = 500_000
    MIN_ER_MICRO = 0.03       # 3% for < 100K
    MIN_ER_MID = 0.01         # 1% for 100K+
    MAX_ER = 0.20             # 20% 초과 = 봇 의심
    MIN_CATEGORY_SCORE = 0.40  # 40% 카테고리 매치
    MIN_POSTS_30D = 4          # 30일 내 최소 4개
    MIN_VIDEO_RATIO = 0.30     # 영상 30% 이상

    def __init__(self, region: str = "us", **overrides):
        self.region = region.lower()
        # 임계값 오버라이드
        for k, v in overrides.items():
            if hasattr(self, k.upper()):
                setattr(self, k.upper(), v)

    def screen(self, profile: dict, posts: list[dict]) -> dict:
        """
        단일 크리에이터 스크리닝.

        Args:
            profile: {"username", "followers", "bio", ...}
            posts: [{"caption", "hashtags", "likes", "comments", "views",
                     "post_date", "media_type", ...}, ...]

        Returns:
            {
                "passed": bool,
                "score": float (0-100),
                "reasons": [str],       # 탈락 사유
                "metrics": {
                    "followers", "er", "category_score",
                    "posts_30d", "video_ratio", "follower_band"
                }
            }
        """
        reasons = []
        followers = profile.get("followers", 0)
        bio = profile.get("bio", "")

        # 1. 팔로워 범위
        if followers < self.MIN_FOLLOWER:
            reasons.append(f"followers_low: {followers} < {self.MIN_FOLLOWER}")
        if followers > self.MAX_FOLLOWER:
            reasons.append(f"followers_high: {followers} > {self.MAX_FOLLOWER}")

        # 2. ER 계산
        er = self._calc_er(posts)
        follower_band = "micro" if followers < 100_000 else "mid"
        min_er = self.MIN_ER_MICRO if follower_band == "micro" else self.MIN_ER_MID
        if er < min_er:
            reasons.append(f"er_low: {er:.3f} < {min_er} ({follower_band})")
        if er > self.MAX_ER:
            reasons.append(f"er_suspicious: {er:.3f} > {self.MAX_ER}")

        # 3. 카테고리 적합도
        category_score = self._calc_category_score(bio, posts)
        if category_score < self.MIN_CATEGORY_SCORE:
            reasons.append(f"category_low: {category_score:.2f} < {self.MIN_CATEGORY_SCORE}")

        # 4. 포스팅 빈도 (최근 30일)
        posts_30d = self._count_recent_posts(posts, days=30)
        if posts_30d < self.MIN_POSTS_30D:
            reasons.append(f"posts_low: {posts_30d} < {self.MIN_POSTS_30D}")

        # 5. 영상 비율
        video_ratio = self._calc_video_ratio(posts)
        if video_ratio < self.MIN_VIDEO_RATIO:
            reasons.append(f"video_ratio_low: {video_ratio:.2f} < {self.MIN_VIDEO_RATIO}")

        # 6. 제외 키워드 체크
        if self._has_exclude_keywords(bio, posts):
            reasons.append("exclude_keywords_found")

        passed = len(reasons) == 0
        score = self._calc_composite_score(followers, er, category_score, posts_30d, video_ratio)

        return {
            "passed": passed,
            "score": round(score, 1),
            "reasons": reasons,
            "metrics": {
                "followers": followers,
                "er": round(er, 4),
                "category_score": round(category_score, 3),
                "posts_30d": posts_30d,
                "video_ratio": round(video_ratio, 3),
                "follower_band": follower_band,
            },
        }

    def screen_batch(self, creators: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        배치 스크리닝.

        Args:
            creators: [{"profile": {...}, "posts": [...]}, ...]

        Returns:
            (passed_list, failed_list) 각각 screen() 결과 + username 포함
        """
        passed, failed = [], []
        for c in creators:
            profile = c.get("profile", {})
            posts = c.get("posts", [])
            result = self.screen(profile, posts)
            result["username"] = profile.get("username", "")
            if result["passed"]:
                passed.append(result)
            else:
                failed.append(result)

        # 통과자는 score 내림차순
        passed.sort(key=lambda x: x["score"], reverse=True)
        return passed, failed

    # ── 내부 메트릭 계산 ──

    def _calc_er(self, posts: list[dict]) -> float:
        """평균 ER 계산."""
        if not posts:
            return 0.0
        ers = []
        for p in posts:
            views = p.get("views", 0)
            likes = p.get("likes", 0)
            comments = p.get("comments", 0)
            if views > 0:
                ers.append((likes + comments) / views)
            elif likes > 0:
                # views 없으면 followers 기반 (deep_crawler 패턴)
                pass
        return sum(ers) / len(ers) if ers else 0.0

    def _calc_category_score(self, bio: str, posts: list[dict]) -> float:
        """육아 카테고리 적합도 (0-1)."""
        keywords = CATEGORY_KEYWORDS.get(self.region, CATEGORY_KEYWORDS["us"])
        core = keywords["core"]
        related = keywords["related"]

        # 텍스트 수집
        texts = [bio.lower()]
        for p in posts:
            texts.append((p.get("caption", "") or "").lower())
            texts.append((p.get("hashtags", "") or "").lower())

        combined = " ".join(texts)

        # 매치 카운트 (core 2점, related 1점)
        matches = 0
        total_possible = len(core) * 2 + len(related)
        for kw in core:
            if kw.lower() in combined:
                matches += 2
        for kw in related:
            if kw.lower() in combined:
                matches += 1

        # 정규화 (최대 1.0)
        # 실전에서 10개+ 매치면 충분히 육아 계정
        score = min(matches / 15.0, 1.0)
        return score

    def _count_recent_posts(self, posts: list[dict], days: int = 30) -> int:
        """최근 N일 이내 포스트 수."""
        cutoff = datetime.now() - timedelta(days=days)
        count = 0
        for p in posts:
            date_str = p.get("post_date", "")
            if not date_str:
                continue
            try:
                if isinstance(date_str, str):
                    post_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                else:
                    post_date = date_str
                if post_date >= cutoff:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count

    def _calc_video_ratio(self, posts: list[dict]) -> float:
        """영상 포스트 비율."""
        if not posts:
            return 0.0
        video_types = {"video", "reel", "Video", "Reel", "GraphVideo", "clips"}
        video_count = sum(
            1 for p in posts
            if p.get("media_type", "") in video_types
            or "video" in str(p.get("media_type", "")).lower()
        )
        return video_count / len(posts)

    def _has_exclude_keywords(self, bio: str, posts: list[dict]) -> bool:
        """제외 키워드 포함 여부."""
        texts = [bio.lower()]
        for p in posts[:5]:  # 상위 5개만 체크
            texts.append((p.get("caption", "") or "").lower())
        combined = " ".join(texts)
        return any(kw in combined for kw in EXCLUDE_KEYWORDS)

    def _calc_composite_score(
        self, followers: int, er: float, category: float,
        posts_30d: int, video_ratio: float
    ) -> float:
        """LT 스크리닝 종합 점수 (0-100)."""
        score = 0.0

        # ER (30점)
        if er >= 0.08:
            score += 30
        elif er >= 0.05:
            score += 25
        elif er >= 0.03:
            score += 20
        elif er >= 0.01:
            score += 10

        # 카테고리 (30점)
        score += category * 30

        # 팔로워 밴드 (15점) — nano/micro 선호
        if 5_000 <= followers <= 50_000:
            score += 15
        elif 1_000 <= followers < 5_000:
            score += 12
        elif 50_000 < followers <= 100_000:
            score += 10
        elif 100_000 < followers <= 500_000:
            score += 5

        # 포스팅 빈도 (15점)
        if posts_30d >= 12:       # 주 3+
            score += 15
        elif posts_30d >= 8:      # 주 2
            score += 12
        elif posts_30d >= 4:      # 주 1
            score += 8

        # 영상 비율 (10점)
        score += min(video_ratio / 0.50, 1.0) * 10

        return min(score, 100.0)


if __name__ == "__main__":
    # Quick test with dummy data
    screener = LTScreener(region="us")
    profile = {"username": "test_mom", "followers": 15000, "bio": "Mom of 2 | Baby food | Toddler life"}
    posts = [
        {"caption": "My baby loves this straw cup! #momlife #baby", "hashtags": "momlife,baby",
         "likes": 500, "comments": 30, "views": 8000, "post_date": "2026-04-01", "media_type": "Reel"},
        {"caption": "Toddler meal prep tips", "hashtags": "toddlerfood,babyfood",
         "likes": 300, "comments": 20, "views": 5000, "post_date": "2026-03-25", "media_type": "Reel"},
        {"caption": "Park day!", "hashtags": "family,kids",
         "likes": 200, "comments": 15, "views": 3000, "post_date": "2026-03-20", "media_type": "GraphImage"},
        {"caption": "Baby led weaning journey", "hashtags": "blw,babyfood",
         "likes": 800, "comments": 50, "views": 12000, "post_date": "2026-03-15", "media_type": "Reel"},
    ]
    result = screener.screen(profile, posts)
    print(f"Passed: {result['passed']}")
    print(f"Score: {result['score']}")
    print(f"Metrics: {result['metrics']}")
    if result['reasons']:
        print(f"Reasons: {result['reasons']}")
