"""
WAT Tool: Daily Twitter/X Agent for Grosmimi Japan.
Runs at 7 time slots (9,11,13,15,17,19,21 JST) with slot-appropriate activities.
Follows 中の人 (nakanohito) strategy — "a mom who works at a straw cup company."

Slot activities:
  09: Morning tweet (empathy) + check mentions
  11: Community engage (like/reply parenting tweets)
  13: Lunch content (tips/question) + reply to morning engagement
  15: Afternoon engage + quote RT + follow accounts
  17: Evening content (trend/あるある)
  19: Prime engagement (moms' active hour)
  21: Night tweet (emotional) + daily analytics + plan tomorrow

Usage:
    py -3 tools/twitter_agent.py --slot 9           # run morning slot
    py -3 tools/twitter_agent.py --slot 21           # run night slot
    py -3 tools/twitter_agent.py --slot auto         # auto-detect JST hour
    py -3 tools/twitter_agent.py --slot 9 --dry-run  # preview only
    py -3 tools/twitter_agent.py --status            # show daily status
    py -3 tools/twitter_agent.py --full-day          # run all 7 slots sequentially

Output: .tmp/twitter_agent_log.json
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from twitter_utils import (
    BudgetTracker,
    create_twitter_clients,
    append_to_log,
    validate_tweet_text,
    count_weighted_chars,
    TWITTER_LOG_PATH,
    TWITTER_PLAN_PATH,
    TWITTER_TRENDS_PATH,
    TMP_DIR,
    PROJECT_ROOT,
)

# ── Constants ────────────────────────────────────────────────────────────

JST = timezone(timedelta(hours=9))
VALID_SLOTS = [10, 13, 17, 19, 21]
AGENT_LOG_PATH = TMP_DIR / "twitter_agent_log.json"

# Claude model for content generation
MODEL = "claude-sonnet-4-20250514"

# ── 中の人 Persona System Prompt ─────────────────────────────────────────

NAKANOHITO_SYSTEM_PROMPT = """You are a social media strategist and content planner for the Japanese X (Twitter) account of the Korean baby brand "Grosmimi".

Your role is NOT to create viral meme content.
Your role is to help build a refined, emotionally resonant, trustworthy Japanese parenting brand account.

# Brand Identity

Grosmimi is:
- A Korean baby brand
- Stylish and emotionally aware
- Warm, thoughtful, observant
- Understands real parenting moments
- Calm and refined, not loud or chaotic

The account should feel like:
"a brand that truly understands parenting life"

NOT:
- a meme account
- a loud viral brand
- an overly casual Gen Z account
- a sales-heavy shopping account

We want to benchmark the feeling and positioning of the Japanese X account of Konny Baby Japan.

# VERY IMPORTANT TONE GUIDELINES

The tone must:
- Feel emotionally observant
- Feel human, but still premium
- Feel calm and tasteful
- Feel relatable without becoming unserious
- Preserve brand dignity and trust

Avoid:
- Excessive slang
- Overly childish language
- Overreaction
- Internet meme culture
- "trying too hard to be funny"
- Loud humor
- Aggressive engagement bait

The brand should sound like:
"A tasteful parenting brand editor"
NOT:
"A funny internet admin"

# Content Philosophy

The content should focus on:
- Parenting moments
- Emotional truth
- Small daily parenting struggles
- Parenting observations
- Warm everyday scenes
- Situations before products

Do NOT center the content around product selling.

Instead:
show parenting situations first,
then naturally place the product as part of the lifestyle.

# GOOD CONTENT EXAMPLES

GOOD:
- "The real morning starts 5 minutes before leaving."
- "Somehow, it always spills right after changing clothes."
- "Quiet toddlers are usually the scariest."
- "Today too, the floor is soaking wet."

BAD:
- "Check out our new product!"
- "Buy now!"
- "Limited sale!"
- "This product is amazing!"

# JAPANESE X PLATFORM STRATEGY

This is a Japanese X account.
Understand Japanese parenting culture and Japanese Twitter behavior.

The account should:
- Feel emotionally close
- Feel culturally natural in Japan
- Participate in parenting conversations
- Maintain refined emotional tone

Do NOT make the account overly casual.

# QUOTE POST (引用ポスト) STRATEGY

Quote posts are important.

But the tone should remain elegant and brand-safe.

GOOD quote post tone:
- "These little moments really become part of every morning."
- "Parenting somehow turns tiny things into big events."
- "This feeling is a daily occurrence, isn't it?"

BAD:
- "LOL"
- "so true 😂"
- overly casual reactions
- meme reactions

# KOREAN BRAND ADVANTAGE

Use the "Korean parenting/lifestyle" angle carefully and elegantly.

Potential themes:
- Korean parenting culture
- Korean baby lifestyle
- Korean parenting habits
- Stylish Korean parenting items
- Differences between Korean and Japanese parenting culture

But do NOT make it feel forced or trend-chasing.

# CONTENT MIX

Target ratio:
- 40% parenting emotional/relatable moments
- 30% lifestyle + product naturally integrated
- 20% Korean parenting culture/lifestyle
- 10% campaign/event/announcement

# WRITING STYLE

Writing can be short OR long.
The key is:
- emotional density
- naturalness
- warmth
- observation
- elegance

Do not force short writing.

Avoid:
- excessive explanations
- corporate PR wording
- hard selling
- robotic structure

# FINAL GOAL

The account should make Japanese parents feel:

"This brand really understands parenting life."

NOT:

"This brand is trying to go viral."
"""

# ── Slot Definitions ─────────────────────────────────────────────────────

SLOT_CONFIG = {
    10: {
        "name": "朝 Morning",
        "name_ko": "아침",
        "activities": ["post", "reply_to_mentions"],
        "post_type": "empathy",
        "post_prompt": """朝の投稿を1つ作成してください。

朝の育児のなかにある小さな観察・気づきを、落ち着いた目線で書いてください。
保育園準備・着替え・朝の家事・季節の空気感（今月の感覚: {season_keywords}）など、毎日のリアル。

トーン:
- 温かく、観察的、品のある日本語
- 派手なネットスラング・絵文字連発・誇張したオチは避ける
- 「ぼやき」より「気づき」の感覚

避けるもの:
- 商品宣伝・カタログ調（「グロミミ」「マグ」「ストロー」「PPSU」「+CUT」など本文に出さない）
- 「娘（1歳10ヶ月）」「むすめ」など毎回の自己紹介
- 韓国ネタ・韓国語の混入（このスロットは普通の朝の一コマ）

1ツイート、日本語のみ。ハッシュタグは控えめに（3〜6個）、本文と合わせて280加重文字以内。""",
        "engage_count": 0,
    },
    11: {
        "name": "午前 Late Morning",
        "name_ko": "오전",
        "activities": ["post", "engage_reply"],
        "post_type": "k_parenting",
        "post_prompt": """午前の投稿を1つ作成してください。

「韓国出身のママだから気づく小さな違い」を、押し付けず自然に書いてください。
食卓・育児習慣・季節の過ごし方など、ライフスタイル寄りの観察。

避けるもの:
- 「韓国ママの〇〇シリーズ」のような反復フォーマット
- 「韓国ママはみんな〜」「韓国では〜」と冒頭から打ち出す書き方
- 講義口調・トレンド狙いの煽り
- 商品宣伝・カタログ調

書き方の例:
- 日本での朝ごはん作りのなかに、韓国の実家での記憶がふっと混ざる
- ふだんの食卓で、なんとなく取り分け文化が出てしまう
- 韓国側はそうとは限らないけど、うちはこうしてる、という個人の話に留める

1ツイート、日本語のみ（韓国語は固有名詞のみ可）。ハッシュタグ3〜6個、合計280加重文字以内。""",
        "engage_count": 3,
        "engage_hashtags": ["#育児", "#育児あるある", "#幼児食", "#イヤイヤ期", "#育児垢さんと繋がりたい"],
    },
    13: {
        "name": "昼 Lunch",
        "name_ko": "점심",
        "activities": ["post", "engage_reply"],
        "post_type": "tips_or_question_or_kquota",
        "post_prompt": """昼の投稿を1つ作成してください。

育児の小さな疑問・気づき・観察を、落ち着いた目線で書く。
質問形・つぶやき形どちらでもOK。

避けるもの:
- エンゲージメント狙いの煽り（「みんなどうしてる？」の連発も控えめに）
- 派手な書き出し・誇張オチ
- 商品宣伝・カタログ調
- 韓国ネタを毎日のように繰り返す（自然な滲ませ方ならOK、シリーズ化はNG）

1ツイート、日本語のみ。ハッシュタグ3〜6個、合計280加重文字以内。""",
        "engage_count": 3,
        "engage_hashtags": ["#育児", "#ストローマグ", "#赤ちゃん", "#育児あるある"],
    },
    15: {
        "name": "午後 Afternoon",
        "name_ko": "오후",
        "activities": ["post", "engage_reply"],
        "post_type": "k_toddlerfood",
        "post_prompt": """午後の投稿を1つ作成してください。

お昼寝・午後の散歩・家での過ごし方など、午後の育児の一場面を観察的に書く。
韓国の食卓・育児習慣を背景として自然に織り込むのはOK。

避けるもの:
- 「K-幼児食紹介」「韓国式◯◯」のような講義口調
- レシピ羅列・「日本にも来てくれ」式の煽り
- 商品宣伝・カタログ調

書き方の例:
- 午後の台所の風景の中に、韓国の家庭の習慣がそっと混ざる
- 子どもの昼寝のあとの静かな時間の観察

1ツイート、日本語のみ。ハッシュタグ3〜6個、合計280加重文字以内。""",
        "engage_count": 3,
        "engage_hashtags": ["#育児グッズ", "#ママ垢さんと繋がりたい", "#幼児食"],
    },
    17: {
        "name": "夕 Evening",
        "name_ko": "저녁",
        "activities": ["post", "engage_reply"],
        "post_type": "daily_life",
        "post_prompt": """夕方の投稿を1つ作成してください。

お迎え・帰り道・夕飯支度など、夕方の育児の小さな一コマを観察的に書く。
季節の空気感（今月の感覚: {season_keywords}）は無理に入れず、自然に滲ませる。

避けるもの:
- 商品宣伝・カタログ調（このスロットは普通の夕方の一コマ）
- 韓国ネタの混入（このスロットは普通の日本の育児日常）
- 「娘（1歳10ヶ月）」を毎回入れる

1ツイート、日本語のみ。ハッシュタグ3〜6個、合計280加重文字以内。""",
        "engage_count": 3,
        "engage_hashtags": ["#ワンオペ育児", "#育児あるある", "#ママ垢さんと繋がりたい"],
    },
    19: {
        "name": "夜 Prime Time",
        "name_ko": "저녁 (프라임타임)",
        "activities": ["post", "engage_reply"],
        "post_type": "empathy_or_product",
        "post_prompt": """夜の投稿を1つ作成してください。

お風呂・夕飯・寝かしつけなど、夜の育児の場面を温かく観察的に書く。
本音・しんどさを書く時も、品を保ち、煽り・自虐の連発は避ける。

製品は日常の一部としてさりげなく現れる程度はOK。ただし宣伝口調・カタログ調は禁止。

避けるもの:
- 「グロミミ」「+CUT」「漏れない」などの直接的なプロダクト表現
- 「娘（1歳10ヶ月）」の繰り返し
- 韓国ネタの混入（このスロットは普通の日本の育児日常）
- 派手なオチ・ネットスラング連発

1ツイート、日本語のみ。ハッシュタグ3〜6個、合計280加重文字以内。""",
        "engage_count": 3,
        "engage_hashtags": [
            "#育児垢さんと繋がりたい",
            "#ママさんと繋がりたい",
            "#育児あるある",
        ],
    },
    21: {
        "name": "夜 Night",
        "name_ko": "밤",
        "activities": ["post", "engage_reply"],
        "post_type": "emotional",
        "post_prompt": """夜遅めの投稿を1つ作成してください。

子どもが寝たあとの静かな時間、一日の振り返り、ママへの労いなど、落ち着いた情緒のある一文。
ポエム調になりすぎず、観察と感情の密度で書く。

避けるもの:
- 過度な感傷・キャッチコピー的な締め
- 商品宣伝・カタログ調
- 韓国ネタの混入

1ツイート、日本語のみ。ハッシュタグ3〜6個、合計280加重文字以内。""",
        "engage_count": 3,
        "engage_hashtags": ["#育児", "#子育て", "#寝かしつけ", "#育児垢さんと繋がりたい"],
    },
    23: {
        "name": "深夜 Late Night",
        "name_ko": "심야",
        "activities": ["post", "analytics"],
        "post_type": "night_study",
        "post_prompt": """深夜の投稿を1つ作成してください。

子どもが寝たあとの調べもの・読書・ひとり時間など、ママの内面的な時間を観察的に書く。
品のある夜の独白として。

避けるもの:
- 「夜中まで研究する職業病キャラ」のような誇張
- 商品宣伝・素材スペックの羅列
- 韓国ネタの強調

1ツイート、日本語のみ。ハッシュタグ3〜6個、合計280加重文字以内。""",
        "engage_count": 0,
    },
}

# ── Season Keywords ──────────────────────────────────────────────────────

# NOTE: seasonal cues = その時期の体感・空気感のつぶやき.
#       自然物の羅列でもイベント列挙でもない。ママが感じる「今日の天気・気温・空気」の感覚。
#       例: 「あ〜なんか暑くなってきたな」「朝晩まだ寒いんだけど」「雨続きすぎない？」
SEASON_MAP = {
    1: "寒すぎて外出る気力ない, まだ正月ボケ抜けない, 朝布団から出られない, 乾燥やばい",
    2: "まだ寒い…春どこ, 花粉来た気がする, たまに暖かい日あると嬉しい, 朝と昼の気温差なに",
    3: "暖かくなってきた？と思ったらまた寒い, 春っぽい日が増えてきた, 花粉つらい, 上着いる？いらない？",
    4: "やっと暖かくなってきた, 朝はまだひんやり, 昼は暑いくらい, 春の雨多くない？, 気温差で体調崩しがち",
    5: "もう暑い日ある, 半袖でいける, 日差し強くなってきた, エアコンつけるか悩む, いい天気の日は外出たい",
    6: "雨ばっかり, じめじめ, 洗濯物乾かない, 蒸し暑い, 晴れた日が貴重, 梅雨いつ終わるの",
    7: "暑い暑い暑い, 外出ると溶ける, 冷房なしでは無理, 夕方のゲリラ豪雨, 夏本番って感じ",
    8: "暑すぎて外無理, まだ暑い…, エアコン24時間, 夕立の後ちょっと涼しい, 早く秋来て",
    9: "まだ暑いけどちょっと涼しくなった？, 夜は過ごしやすい, 秋っぽい風吹いてきた, でも昼は暑い",
    10: "急に涼しくなった, 朝寒い, 上着出した, 秋晴れ気持ちいい, 日が短くなってきた",
    11: "寒くなってきた, 冬っぽい, 朝の冷え込みやばい, でも昼は暖かい日もある, そろそろ冬支度",
    12: "寒い, 冬本番, 朝起きるのつらい, 乾燥する, 年末感ある, あっという間に1年終わる",
}

# Day-of-week content types (from strategy: weekly rhythm)
DOW_CONTENT = {
    0: "育児あるある (共感)",      # Monday
    1: "Tips/教育",              # Tuesday
    2: "質問/アンケート",          # Wednesday
    3: "中の人日記 (ビハインド)",   # Thursday
    4: "あるある or トレンド参加",  # Friday
    5: "UGC紹介/ユーザー交流",     # Saturday
    6: "ライトコンテンツ",         # Sunday
}


# ── Helper Functions ─────────────────────────────────────────────────────

def get_jst_now() -> datetime:
    """Get current time in JST."""
    return datetime.now(JST)


def get_season_keywords() -> str:
    """Get current month's season keywords."""
    return SEASON_MAP.get(get_jst_now().month, "")


def get_dow_content_type() -> str:
    """Get today's content type based on day of week."""
    return DOW_CONTENT.get(get_jst_now().weekday(), "フリー")


def load_agent_log() -> dict:
    """Load agent activity log."""
    if AGENT_LOG_PATH.exists():
        with open(AGENT_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"activities": []}


def save_agent_log(log: dict) -> None:
    """Save agent activity log."""
    AGENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def log_activity(slot: int, activity_type: str, details: dict) -> None:
    """Log an agent activity."""
    log = load_agent_log()
    entry = {
        "timestamp": get_jst_now().isoformat(),
        "slot": slot,
        "activity": activity_type,
        **details,
    }
    log["activities"].append(entry)
    save_agent_log(log)


def get_today_activities() -> list[dict]:
    """Get all activities logged today."""
    log = load_agent_log()
    today_str = get_jst_now().strftime("%Y-%m-%d")
    return [
        a for a in log.get("activities", [])
        if a.get("timestamp", "").startswith(today_str)
    ]


def get_recent_tweets() -> list[str]:
    """Get recent tweet texts from log to avoid duplicates."""
    if not TWITTER_LOG_PATH.exists():
        return []
    with open(TWITTER_LOG_PATH, "r", encoding="utf-8") as f:
        log = json.load(f)
    return [t.get("text_preview", "") for t in log.get("tweets", [])[-10:]]


# ── Content Generation ───────────────────────────────────────────────────

def generate_tweet(slot: int, dry_run: bool = False) -> dict | None:
    """Generate a tweet for the given slot using Claude API."""
    config = SLOT_CONFIG[slot]
    if "post" not in config["activities"]:
        return None

    prompt = config["post_prompt"]

    # Inject season keywords
    if "{season_keywords}" in prompt:
        prompt = prompt.replace("{season_keywords}", get_season_keywords())

    # Add context
    now = get_jst_now()
    dow_type = get_dow_content_type()
    recent = get_recent_tweets()

    context = f"""
今日: {now.strftime('%Y年%m月%d日 %A')}
今日のコンテンツテーマ（曜日別）: {dow_type}
今月の季節モチーフ（参考・週1〜2回だけ使う）: {get_season_keywords()}
"""
    if recent:
        context += "\n最近の投稿（重複避ける）:\n"
        for r in recent[-5:]:
            context += f"- {r}\n"

    full_prompt = context + "\n" + prompt

    if dry_run:
        print(f"\n[DRY RUN] Would generate tweet with prompt:")
        print(f"  Slot: {slot} ({config['name']})")
        print(f"  Type: {config.get('post_type', 'N/A')}")
        print(f"  DOW theme: {dow_type}")
        return {"status": "dry_run", "prompt_preview": full_prompt[:200]}

    try:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not found in .env")
            return {"status": "failed", "error": "No API key"}

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=NAKANOHITO_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": full_prompt}],
        )
        tweet_text = response.content[0].text.strip()

        # Clean up: remove quotes if Claude wrapped it
        if tweet_text.startswith('"') and tweet_text.endswith('"'):
            tweet_text = tweet_text[1:-1]
        if tweet_text.startswith("「") and tweet_text.endswith("」"):
            tweet_text = tweet_text[1:-1]

        # Validate weighted length
        is_valid, msg = validate_tweet_text(tweet_text)
        if not is_valid:
            logger.warning(f"Generated tweet too long: {msg}")
            # Try to get a shorter version
            retry_prompt = full_prompt + f"\n\n注意: 前回の出力が長すぎました({msg})。もっと短く、280加重文字以内に収めてください。日本語1文字=2加重文字です。実質140文字以内にしてください。"
            response = client.messages.create(
                model=MODEL,
                max_tokens=500,
                system=NAKANOHITO_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": retry_prompt}],
            )
            tweet_text = response.content[0].text.strip()
            if tweet_text.startswith('"') and tweet_text.endswith('"'):
                tweet_text = tweet_text[1:-1]

        weighted = count_weighted_chars(tweet_text)
        return {
            "status": "generated",
            "text": tweet_text,
            "weighted_chars": weighted,
            "raw_chars": len(tweet_text),
            "slot": slot,
            "post_type": config.get("post_type", ""),
        }

    except Exception as e:
        logger.error(f"Content generation failed: {e}")
        return {"status": "failed", "error": str(e)}


def translate_to_korean(text: str) -> str:
    """Translate Japanese text to Korean for the operator."""
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return "(번역 불가: API 키 없음)"

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"다음 일본어를 한국어로 자연스럽게 번역해줘. 번역만 출력:\n\n{text}"
            }],
        )
        return response.content[0].text.strip()
    except Exception:
        return "(번역 실패)"


# ── Activity Executors ───────────────────────────────────────────────────

def execute_post(slot: int, dry_run: bool = False) -> dict:
    """Generate and post a tweet for this slot."""
    tracker = BudgetTracker()
    if not dry_run and not tracker.can_post():
        return {"status": "budget_exceeded", "message": "Daily budget exceeded"}

    # Generate content
    result = generate_tweet(slot, dry_run=dry_run)
    if not result or result["status"] != "generated":
        return result or {"status": "failed", "error": "No content generated"}

    tweet_text = result["text"]
    weighted = result["weighted_chars"]

    # Korean translation for operator
    ko_translation = translate_to_korean(tweet_text) if not dry_run else "(dry run)"

    print(f"\n{'='*60}")
    print(f"  SLOT {slot} — {SLOT_CONFIG[slot]['name']}")
    print(f"{'='*60}")
    print(f"  JP: {tweet_text}")
    print(f"  KO: {ko_translation}")
    print(f"  Weighted: {weighted}/280")
    print(f"{'='*60}")

    if dry_run:
        return {"status": "dry_run", "text": tweet_text, "ko": ko_translation}

    # Post
    try:
        client, api_v1 = create_twitter_clients()
        response = client.create_tweet(text=tweet_text)
        tweet_id = response.data["id"]
        tweet_url = f"https://x.com/grosmimi_jp/status/{tweet_id}"

        print(f"  Posted! {tweet_url}")

        # Log to both agent log and twitter log
        log_activity(slot, "post", {
            "tweet_id": tweet_id,
            "text": tweet_text,
            "ko_translation": ko_translation,
            "weighted_chars": weighted,
            "url": tweet_url,
        })

        append_to_log(TWITTER_LOG_PATH, {
            "post_id": f"agent_{get_jst_now().strftime('%Y%m%d')}_{slot:02d}00",
            "posted_at": get_jst_now().isoformat(),
            "platform": "twitter",
            "type": "single",
            "tweet_id": tweet_id,
            "text_preview": tweet_text[:80],
            "status": "published",
            "source": "agent",
            "slot": slot,
        })

        return {
            "status": "published",
            "tweet_id": tweet_id,
            "url": tweet_url,
            "text": tweet_text,
            "ko": ko_translation,
        }

    except Exception as e:
        logger.error(f"Posting failed: {e}")
        return {"status": "failed", "error": str(e)}


def execute_check_mentions(slot: int, dry_run: bool = False) -> dict:
    """Check and respond to mentions."""
    print(f"\n  Checking mentions...")

    if dry_run:
        print("  [DRY RUN] Would check mentions via twitter_reply.py")
        return {"status": "dry_run", "activity": "check_mentions"}

    try:
        client, _ = create_twitter_clients()

        # Get authenticated user ID
        me = client.get_me()
        user_id = me.data.id

        # Get recent mentions
        mentions = client.get_users_mentions(
            id=user_id,
            max_results=10,
            tweet_fields=["created_at", "text", "author_id"],
        )

        mention_count = 0
        if mentions.data:
            mention_count = len(mentions.data)
            print(f"  Found {mention_count} recent mentions")
            for m in mentions.data[:5]:
                print(f"    - @{m.author_id}: {m.text[:60]}...")
        else:
            print("  No new mentions")

        log_activity(slot, "check_mentions", {"mention_count": mention_count})
        return {"status": "ok", "mention_count": mention_count}

    except Exception as e:
        logger.warning(f"Mention check failed (may be API tier limit): {e}")
        log_activity(slot, "check_mentions", {"error": str(e)})
        return {"status": "limited", "error": str(e)}


def execute_engage(slot: int, dry_run: bool = False) -> dict:
    """Like and engage with parenting community tweets."""
    config = SLOT_CONFIG[slot]
    target_count = config.get("engage_count", 5)
    hashtags = config.get("engage_hashtags", ["#育児", "#ストローマグ"])

    print(f"\n  Community engagement (target: {target_count} interactions)")
    print(f"  Hashtags: {', '.join(hashtags)}")

    if dry_run:
        print(f"  [DRY RUN] Would search & like {target_count} tweets")
        return {"status": "dry_run", "target": target_count}

    try:
        client, _ = create_twitter_clients()
        liked_count = 0

        for tag in hashtags[:2]:  # Limit to 2 hashtags per session
            query = f"{tag} lang:ja -is:retweet"
            try:
                tweets = client.search_recent_tweets(
                    query=query,
                    max_results=10,
                    tweet_fields=["created_at", "public_metrics"],
                )
                if tweets.data:
                    for tweet in tweets.data[:target_count // 2]:
                        try:
                            client.like(tweet.id)
                            liked_count += 1
                            print(f"    Liked: {tweet.text[:50]}...")
                            time.sleep(2)  # Rate limit courtesy
                        except Exception as e:
                            logger.debug(f"Like failed: {e}")
                            break

                time.sleep(3)  # Between searches

            except Exception as e:
                logger.warning(f"Search for {tag} failed: {e}")

            if liked_count >= target_count:
                break

        print(f"  Engaged with {liked_count} tweets")
        log_activity(slot, "engage", {"liked": liked_count, "hashtags": hashtags})
        return {"status": "ok", "liked": liked_count}

    except Exception as e:
        logger.warning(f"Engagement failed: {e}")
        return {"status": "limited", "error": str(e)}


def execute_heavy_engage(slot: int, dry_run: bool = False) -> dict:
    """Heavy engagement session (prime time)."""
    print(f"\n  PRIME TIME engagement session (19:00)")
    result = execute_engage(slot, dry_run=dry_run)
    result["type"] = "heavy_engage"
    return result


def execute_follow(slot: int, dry_run: bool = False) -> dict:
    """Follow new parenting accounts."""
    config = SLOT_CONFIG[slot]
    target = config.get("follow_count", 3)

    print(f"\n  Follow new accounts (target: {target})")

    if dry_run:
        print(f"  [DRY RUN] Would follow {target} parenting accounts")
        return {"status": "dry_run", "target": target}

    # Following is limited on free tier — log intent
    print(f"  Note: Follow is manual on free tier. Recommended accounts to follow:")
    print(f"    Search: #育児垢さんと繋がりたい")
    print(f"    Search: #ママさんと繋がりたい")

    log_activity(slot, "follow_reminder", {"target": target})
    return {"status": "reminder", "target": target}


def execute_quote_rt(slot: int, dry_run: bool = False) -> dict:
    """Quote retweet a relevant trending tweet (max 1/day)."""
    # Check if we already did a quote RT today
    today_activities = get_today_activities()
    if any(a["activity"] == "quote_rt" for a in today_activities):
        print("  Already did a quote RT today (limit: 1/day)")
        return {"status": "skipped", "reason": "daily_limit"}

    print(f"\n  Quote RT check (max 1/day)")

    if dry_run:
        print("  [DRY RUN] Would search for quotable trending content")
        return {"status": "dry_run"}

    # For free tier, this is mostly a manual activity
    print("  Recommended: Search Twitter for trending parenting content to quote RT")
    print("  Template: わかります！✨ [your comment] #育児 #ストローマグ")

    log_activity(slot, "quote_rt_reminder", {})
    return {"status": "reminder"}


def execute_analytics(slot: int, dry_run: bool = False) -> dict:
    """Collect daily analytics."""
    print(f"\n  Daily analytics collection")

    if dry_run:
        print("  [DRY RUN] Would collect analytics")
        return {"status": "dry_run"}

    try:
        client, _ = create_twitter_clients()
        me = client.get_me(user_fields=["public_metrics"])

        if me.data:
            metrics = me.data.public_metrics if hasattr(me.data, 'public_metrics') else {}
            print(f"  Followers: {metrics.get('followers_count', 'N/A')}")
            print(f"  Following: {metrics.get('following_count', 'N/A')}")
            print(f"  Tweets: {metrics.get('tweet_count', 'N/A')}")

            log_activity(slot, "analytics", {
                "followers": metrics.get("followers_count"),
                "following": metrics.get("following_count"),
                "tweets": metrics.get("tweet_count"),
            })
            return {"status": "ok", "metrics": metrics}

    except Exception as e:
        logger.warning(f"Analytics failed: {e}")

    return {"status": "limited"}


def execute_plan_tomorrow(slot: int, dry_run: bool = False) -> dict:
    """Check if tomorrow's content is planned."""
    print(f"\n  Tomorrow's content check")

    today_posts = [
        a for a in get_today_activities()
        if a["activity"] == "post" and a.get("tweet_id")
    ]
    print(f"  Today's posts: {len(today_posts)}")

    tracker = BudgetTracker()
    counts = tracker.get_counts()
    print(f"  Budget remaining: {counts['remaining_today']} today / {counts['remaining_month']} month")

    log_activity(slot, "plan_check", {
        "today_posts": len(today_posts),
        "budget_today": counts["remaining_today"],
        "budget_month": counts["remaining_month"],
    })
    return {"status": "ok", "today_posts": len(today_posts)}


def execute_reply_to_engagement(slot: int, dry_run: bool = False) -> dict:
    """Reply to engagement on our recent tweets."""
    print(f"\n  Checking engagement on our tweets...")

    if dry_run:
        print("  [DRY RUN] Would check replies on recent tweets")
        return {"status": "dry_run"}

    # This is limited on free tier
    print("  Note: Reply monitoring is limited on current API tier")
    print("  Recommended: Manually check notifications on x.com")

    log_activity(slot, "reply_check", {})
    return {"status": "reminder"}


# ── Activity Router ──────────────────────────────────────────────────────

ACTIVITY_MAP = {
    "post": execute_post,
    "check_mentions": execute_check_mentions,
    "engage": execute_engage,
    "heavy_engage": execute_heavy_engage,
    "follow": execute_follow,
    "quote_rt": execute_quote_rt,
    "analytics": execute_analytics,
    "plan_tomorrow": execute_plan_tomorrow,
    "reply_to_engagement": execute_reply_to_engagement,
}


def run_slot(slot: int, dry_run: bool = False) -> dict:
    """Execute all activities for a time slot."""
    if slot not in VALID_SLOTS:
        print(f"Invalid slot: {slot}. Valid: {VALID_SLOTS}")
        return {"status": "invalid_slot"}

    config = SLOT_CONFIG[slot]
    now = get_jst_now()

    print(f"\n{'#'*60}")
    print(f"  Twitter Agent — Slot {slot}:00 JST")
    print(f"  {config['name']} / {config['name_ko']}")
    print(f"  {now.strftime('%Y-%m-%d %H:%M JST')}")
    print(f"  Today's theme: {get_dow_content_type()}")
    print(f"  Activities: {', '.join(config['activities'])}")
    print(f"{'#'*60}")

    results = {}
    for activity in config["activities"]:
        executor = ACTIVITY_MAP.get(activity)
        if executor:
            try:
                results[activity] = executor(slot, dry_run=dry_run)
            except Exception as e:
                logger.error(f"Activity {activity} failed: {e}")
                results[activity] = {"status": "error", "error": str(e)}
        else:
            logger.warning(f"Unknown activity: {activity}")

    # Summary
    print(f"\n{'─'*60}")
    print(f"  Slot {slot} Summary:")
    for act, res in results.items():
        status = res.get("status", "unknown")
        print(f"    {act}: {status}")
    print(f"{'─'*60}\n")

    return {"slot": slot, "results": results}


def show_status():
    """Show today's agent activity status."""
    now = get_jst_now()
    today = get_today_activities()

    print(f"\n{'='*60}")
    print(f"  Twitter Agent Status")
    print(f"  {now.strftime('%Y-%m-%d %H:%M JST')}")
    print(f"  Today's theme: {get_dow_content_type()}")
    print(f"{'='*60}")

    # Budget
    tracker = BudgetTracker()
    counts = tracker.get_counts()
    print(f"\n  Budget:")
    print(f"    Today: {counts['today']}/{50} (remaining: {counts['remaining_today']})")
    print(f"    Month: {counts['month']}/{1500} (remaining: {counts['remaining_month']})")

    # Today's activities by slot
    print(f"\n  Today's Activities ({len(today)} total):")
    for slot in VALID_SLOTS:
        slot_acts = [a for a in today if a.get("slot") == slot]
        if slot_acts:
            acts_str = ", ".join(a["activity"] for a in slot_acts)
            print(f"    {slot}:00 ✓ {acts_str}")
        else:
            config = SLOT_CONFIG[slot]
            if now.hour >= slot:
                print(f"    {slot}:00 ✗ (missed) — {config['name_ko']}")
            else:
                print(f"    {slot}:00 ○ (upcoming) — {config['name_ko']}")

    # Recent posts
    posts = [a for a in today if a["activity"] == "post" and a.get("tweet_id")]
    if posts:
        print(f"\n  Today's Posts:")
        for p in posts:
            print(f"    [{p['slot']}:00] {p.get('text', '')[:50]}...")
            if p.get("ko_translation"):
                print(f"           KO: {p['ko_translation'][:50]}...")

    print()


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Grosmimi Japan Twitter Agent (中の人 strategy)"
    )
    parser.add_argument(
        "--slot", type=str,
        help="Time slot to run (9,11,13,15,17,19,21 or 'auto')"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview activities without executing"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show today's activity status"
    )
    parser.add_argument(
        "--full-day", action="store_true",
        help="Run all 7 slots sequentially (for testing)"
    )
    parser.add_argument(
        "--post-only", action="store_true",
        help="Only run the posting activity for the slot"
    )
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.full_day:
        print("Running full day simulation...")
        for slot in VALID_SLOTS:
            run_slot(slot, dry_run=args.dry_run)
            if not args.dry_run:
                time.sleep(5)
        return

    if not args.slot:
        parser.print_help()
        print(f"\nValid slots: {VALID_SLOTS}")
        print(f"Current JST: {get_jst_now().strftime('%H:%M')}")
        return

    # Determine slot
    if args.slot == "auto":
        current_hour = get_jst_now().hour
        # Find the closest slot at or before current time
        slot = max((s for s in VALID_SLOTS if s <= current_hour), default=VALID_SLOTS[0])
        print(f"Auto-detected slot: {slot} (current JST: {current_hour}:xx)")
    else:
        slot = int(args.slot)

    if args.post_only:
        # Override: only run post activity
        execute_post(slot, dry_run=args.dry_run)
    else:
        run_slot(slot, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
