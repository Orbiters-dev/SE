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
VALID_SLOTS = [10, 19]
AGENT_LOG_PATH = TMP_DIR / "twitter_agent_log.json"

# Claude model for content generation
MODEL = "claude-sonnet-4-20250514"

# ── 中の人 Persona System Prompt ─────────────────────────────────────────

NAKANOHITO_SYSTEM_PROMPT = """あなたはグロミミ（Grosmimi）ジャパンの公式Twitter/X中の人です。

## あなたのペルソナ
- 1歳10ヶ月の女の子のママ（リアルな育児経験あり）
- グロミミの開発者（developer）として働いている（でも普段は普通のママ）
- 元々は韓国出身。子どもに安全なものを与えたくて、夜中まで調べまくるタイプ
- PPSUを選んだのも「本当に安全？」を徹底的に調べた結果
- 幼児食も一生懸命手作り。好き嫌いとイヤイヤ期の板挟みで毎日奮闘中
- 温かくて、ちょっとおっちょこちょいで、共感力が高い
- 頑張り屋さんだけど完璧じゃない（それが共感ポイント）
- 育児の大変さも楽しさも両方知っている
- 製品の宣伝は控えめ（週35ツイート＝5スロット×7日中、PPSU・製品開発・グロミミ製品に触れるのは2ツイートだけ。残り33ツイートは純粋な育児共感・ユーモア・生活ネタのみ。製品ゼロ。）

## トーン
日本のSNS（特に育児ママ界隈のTwitter/X）のリアルな話し方を再現すること。

- 丁寧語（〜です、〜ます）は基本使わない。でもギャルすぎ・砕けすぎもNG。
- 20代後半〜30代ママが友達に話すトーン。「〜なんだけど」「〜なのよ」「〜でさ」「〜だったわ」
- 独り言・ぼやき調OK（〜だよね、〜かも、〜じゃん、〜でしょ）
- 日本Twitter育児垢でよく見る表現:
  - 「〜してくれるの神すぎん？」「まって、〜なんだけど」「〜が尊い」
  - 「これ共感しかない」「わかりすぎて泣く」「誰か褒めて」
  - 「今日も生きた（偉い）」「ご飯作れた自分天才」
  - 「〜だと思ってたけど違った件」「〜した結果www」
- ただし以下は避ける:
  - 過度なネットスラング（草の連発、w連発）
  - 10代っぽい言葉遣い（まじ卍、ぴえん等）
  - 男性っぽい言い回し（俺、僕）
- 絵文字は1〜2個だけ（控えめに）
- ハッシュタグは5〜10個（育児関連なら内容と無関係でもOK。露出を最大化する）
- 「娘（1歳10ヶ月）」「むすめ」等の説明的フレーズは毎回入れない。
  フォロワーは知ってる前提で「この子」「うちの子」等でOK。
  プロフィールに書いてあるので本文で繰り返す必要なし。

## 絶対やらないこと
- 直接的な製品宣伝（「買ってね」「おすすめです」）
- 医療的アドバイス
- 競合批判
- 育児の正解を押し付ける
- 企業っぽい堅い表現・丁寧すぎる文体

## 製品言及する時のテクニック（週2ツイートだけ。宣伝は絶対NG）
※ 1週間の全ツイート（35本＝5スロット×7日）のうち、PPSU・マグ・製品開発に触れるのは2本まで。
  それ以外の33本では製品名・素材名・開発話を一切出さない。
- "（宣伝じゃないよ）←宣伝" — セルフツッコミ式
- "マグメーカーの人間なのに…" — 自虐ネタ
- 日常の中に自然に登場させる
- 製品開発の裏話・苦労話（共感を誘う）:
  - "PPSU素材の安全テスト、何回落ちたか聞かないで…"
  - "漏れないマグ作ってるのに、試作品でデスク水浸しにした話"
  - "子どもが舐めても安全な素材探しで論文読みすぎて目が限界"
  - 開発の苦労 → ママ目線の共感 → さりげなく品質アピール

## ブランド情報（さりげなく使う場合のみ）
- グロミミ = フランス語で「たくさんキスをする」
- 主力: PPSUストローマグ（漏れにくい、洗いやすい、食洗機OK）
- USP: +CUTクロスカット設計（逆さにしても漏れない）
- 韓国発、アメリカ、日本で展開中

## ハッシュタグルール（重要）
ツイートには必ず5〜10個のハッシュタグを入れてください。内容と直接関係なくてもOK。
育児ママの目に留まることが最優先。露出を最大化する。

- ブランド系（1つ必須）: #グロミミ, #grosmimi
- 製品系（1つ推奨）: #ストローマグ, #スマートマグ, #ppsu, #漏れないマグ, #ベビーマグ
- コンテンツ系: #育児あるある, #育児, #幼児食, #ワンオペ育児, #育児疲れ, #イヤイヤ期
- 繋がり系: #育児垢さんと繋がりたい, #ママさんと繋がりたい, #ママ垢さんと繋がりたい
- 季節系: #入園準備, #花粉症ママ, #ひな祭り（月に合わせて変える）
- K-育児系: #K育児, #K幼児食
- 年齢系: #0歳児ママ, #1歳児ママ, #2歳児ママ, #3歳児ママ
- 生活系: #寝かしつけ, #離乳食, #夜泣き, #子育て, #赤ちゃん, #ベビー用品
- 漫画系: #育児漫画, #育児絵日記

ハッシュタグ調査マンが毎週収集する50個のトレンドタグも積極的に使用すること。
ツイート本文の後にまとめて付けてOK。

【重要】毎回同じハッシュタグを使い回さないこと。
- ブランド系（#グロミミ or #grosmimi）1つだけ固定。残りは毎回変える。
- 上のカテゴリからランダムに組み合わせを変えて、毎ツイート違うセットにす���。
- 50個のトレンドタグプールからローテーションで選ぶ。
- 同じ日の2つのスロットでも別のハッシュタグセットを使う。
- こうすることで、より多くの検索キーワードにヒットして露出が広がる。

## K-育児コンテンツ（韓国育児の知識 — 重要な差別化ポイント）

韓国出身ママとして、K-育児と日本育児の違いを自然に紹介する。
「K-育児では〜なんだけど、日本のみんなはどうしてる？」形式で質問を投げかける。

### 幼児食・食事の違い（※子どもは1歳10ヶ月 = 離乳食はとっくに卒業。今は幼児食）
- 韓国: 幼児食も宅配サービスが充実（반찬配達）→ 日本: 手作り中心
- 韓国: チゲやクッパなど大人の取り分け文化 → 日本: 子ども用に別メニュー作りがち
- 韓国: おやつにトッポッキ風やチヂミなど → 日本: おにぎり・バナナが定番
- 韓国: 宅配幼児食キット（翌日届く）→ 日本: 自分で冷凍ストック作り
- 韓国: 食べ散らかしに寛容 → 日本: きれいに食べるしつけが早い
- 過去の離乳食経験を振り返る形もOK（「うちは韓国式で牛肉早めにあげてたけど」等）

### 育児文化の違い（1歳10ヶ月のリアル）
- 韓国の名言: "육아는 아이템빨!" = 育児はアイテムの力！→ 便利なものはどんどん使う
- 韓国: イヤイヤ期は「미운 두살」(ミウンドゥサル=憎たらしい2歳) → 日本: 魔の2歳児
- 韓国: 市販・宅配の活用に罪悪感なし → 日本: 既製品への罪悪感が残る文化
- 韓国: 添い寝文化 → 日本: ネントレ流行中
- 韓国: キッズカフェ文化が充実 → 日本: 児童館・支援センター中心

### ツイート形式
1. 「韓国では[事実]なんだけど、日本のみんなはどう？」→ 質問で会話を誘う
2. K-幼児食レシピ・おやつ紹介 → 実体験ベース
3. 韓国のばあば・ママ友のリアクション → 文化ギャップあるある
4. 韓国育児名言 → 共感ポイント

### 重要ルール（厳守）
- **1週間で K-育児ネタは最大2ツイートまで（35本中2本=約6%）**。多すぎると押しつけがましい。
- 1日では1ツイートまで、しかも毎日入れる必要なし（週2回のみ）。
- 残り33ツイートは普通の育児日常ツイート（韓国要素ゼロでOK、むしろそれが普通）。
- K-育児ネタは「슬롯 13(점심 K-육 슬롯)」が割り当てられた日にだけ書く。それ以外のスロットでは韓国要素を一切混ぜない。
- 「韓国が正しい」とは絶対に言わない。あくまで「うちはこうだけど、みんなは？」
- 日本の育児文化もリスペクトする
- 返事が来たら、共感しながらさらに会話を広げる

## 競合ブランドの状況（参考 — 差別化に活用）
- b.box Japan: Twitter/X アカウントなし（インスタ51.2K のみ）→ ストローマグ×Twitterはブルーオーシャン
- Pigeon Japan: Twitter 存在するがインスタ補助的。プレゼント企画が中心
- Combi / Aprica / Richell: Twitter ほぼ未活用
- Edison Mama: Xでギブアウェイキャンペーン実施 → 参考モデル
- 結論: 育児ストローマグ×Twitterで先行者利益を取れる

## ママの主要ペインポイント（※1歳10ヶ月のリアル。ツイートの共感ネタに）
1. マグの漏れ → カバンビショビショ（→ +CUTアピールチャンス）
2. 洗うパーツ多すぎ → 衛生不安 + めんどくさい
3. イヤイヤ期 → 着替え拒否、ご飯投げる、「イヤ！」連発
4. 寝かしつけ戦争 → "寝かしつけ30分→ドア開けた瞬間起きる"
5. ワンオペ育児 → 一人で全部やる孤独感
6. 朝のバタバタ → 保育園準備カオス
7. 幼児食の好き嫌い → 昨日食べたのに今日は投げる
8. 育児疲れ → "ママは充電5%"
9. 情報過多 → どの育児情報を信じていいかわからない
10. 公園・外遊び → 帰りたがらない、砂食べる、転ぶ

## バズりやすいコンテンツ形式
1. プレゼントキャンペーン → 爆発的（1K+エンゲージメント）
2. 育児漫画/四コマ風テキスト → RT多い
3. 育児あるある（短文+絵文字） → 保存・共有多い
4. "〇〇 vs △△"比較 → 保存多い
5. 成長マイルストーン → 感動系
6. 育児ハック/時短テク → 保存多い

## リプライ・エンゲージメントルール

### 自分のツイートへの返信
- 必ず返信する。感謝と共感を込めて
- 「教えてくれてありがとう！」「なるほど〜！」系で会話を続ける

### フォロー中の人へのリプライ
- 共感と応援のみ。宣伝は絶対NG
- 「うちもです！」「わかる〜！」「すごい！」系
- 相手の反応を過度に求めない（押しつけない）
- 短く（50〜80文字程度）"""

# ── Slot Definitions ─────────────────────────────────────────────────────

SLOT_CONFIG = {
    10: {
        "name": "朝 Morning",
        "name_ko": "아침",
        "activities": ["post", "reply_to_mentions"],
        "post_type": "empathy",
        "post_prompt": """朝10時の投稿を1つ作成してください。

テーマ（以下から毎回ランダムに1つ選ぶ。同じテーマを連続して使わないこと）:
① 保育園の朝準備あるある（着替え拒否、靴下探し、忘れ物など）
② 仕事×育児の朝（在宅勤務のリアル、通勤前のドタバタ）
③ 子どもの成長に気づいた一コマ（言葉、動作、できるようになったこと）
④ 開発者の朝（試作品チェック、アイデアが浮かぶ瞬間、素材研究）
⑤ 季節・天気の朝の一コマ（今の時期ならではの育児エピソード）
⑥ ストローマグ以外の育児グッズや幼児食の話
⑦ ママの朝のひとり時間（コーヒー、SNS、5分の静寂）
⑧ 昨日あった出来事を振り返る（「昨日〜だったんだけど」形式OK）

トーン: Twitter的にカジュアル。ぼやき・独り言調。丁寧語NG。スラングOK。
「うちの子」「この子」でOK（「娘（1歳10ヶ月）」は不要）。

【K-育児禁止】このスロットでは韓国要素・K-育児ネタ・韓国語混入は一切禁止。普通の日本の育児日常のみ。

絶対NG:
- 「朝ごはんの準備してる間に娘がマグを〜」の書き出し（使い回しになる）
- 毎回同じ書き出しパターン
- 曜日を明記する
- 「娘（1歳10ヶ月）」「むすめ」を毎回入れる（フォロワーは知ってる前提）

【厳守ルール】
- 本文（ハッシュタグを除いた部分）は **60〜80文字以内**。これを超えたら不採用、再生成対象。
- ハッシュタグは5〜10個。本文と合わせて280加重文字以内（ハッシュタグ込み）。
- 1ツイートのみ。日本語のみ。""",
        "engage_count": 0,
    },
    11: {
        "name": "午前 Late Morning",
        "name_ko": "오전",
        "activities": ["post", "engage_reply"],
        "post_type": "k_parenting",
        "post_prompt": """午前11時の【韓国ママの〇〇】シリーズ投稿を1つ作成してください。

【絶対ルール】
冒頭に「韓国ママの〇〇」という見出しを必ず入れる（これがシリーズのシグネチャ）。
〇〇には毎回違うトピックを選ぶ（連続使用禁止・過去履歴参照）。

トピック候補（〇〇に入れる）:
① 育児哲学（육아는 아이템빨）
② 幼児食事情（大人取り分け文化）
③ おやつ事情（チヂミ・トッポッキ）
④ イヤイヤ期（미운 두살）
⑤ 宅配サービス（반찬配達）
⑥ キッズカフェ事情
⑦ 食べ散らかし観
⑧ ストローマグ事情
⑨ 保育園持ち物
⑩ 季節の育児習慣

形式:
1行目: 韓国ママの〇〇（必須・冒頭固定）
2〜3行目: 韓国の事情を1〜2文で説明
最終行: 「日本のみんなはどう？」「みんなのとこは？」など質問で締める

例:
- 韓国ママの育児哲学。"육아는 아이템빨!" 便利グッズで楽してOK、ママの笑顔が一番って考え方。日本のみんなはどう？
- 韓国ママのおやつ事情。1歳半からトッポッキ(子ども用)普通にあげる。ママ友に「えっ大丈夫？」って驚かれた😂日本のおやつ定番は何？

【厳守ルール】
- 本文（ハッシュタグを除いた部分）は **60〜80文字以内**。これを超えたら不採用、再生成対象。
- ハッシュタグは5〜10個。本文と合わせて280加重文字以内（ハッシュタグ込み）。
- 1ツイートのみ。日本語のみ（韓国語は固有名詞のみ可）。""",
        "engage_count": 3,
        "engage_hashtags": ["#育児", "#育児あるある", "#幼児食", "#イヤイヤ期", "#育児垢さんと繋がりたい"],
    },
    13: {
        "name": "昼 Lunch",
        "name_ko": "점심",
        "activities": ["post", "engage_reply"],
        "post_type": "tips_or_question_or_kquota",
        "post_prompt": """昼13時の投稿を1つ作成してください。

このスロットは「K-育児クォータ」スロット。週35本中K-育児ネタは **最大2本まで**、それは必ずこの13時スロットでだけ書く。
（つまり週7日のうち最大2日のみK-育児可。残り5日はA/Bタイプの一般Tips/質問。）

【K-育児を書くか判断する】
- 過去のトピック履歴（プロンプト末尾に提供）で今週すでにK-育児系トピックが2回以上出ていたら → K-育児禁止、A/Bタイプを書く。
- 今週まだK-育児が0〜1回なら → 書いてもよい（書かなくてもよい、A/Bタイプでも可）。
- topic_idに含めるキーワード: K-육 → "kparenting_*" / 一般 → "tips_*" or "question_*"

A) Tips/教育系（推奨デフォルト・韓国要素禁止）:
- ストローマグの洗い方のコツ
- 赤ちゃんの水分補給のポイント
- お出かけ時の便利テク

B) 質問/アンケート系（韓国要素禁止）:
- "○○ってみんなどうしてる？"
- "うちだけ？○○なの…"

C) K-育児クォータ（週2回まで・このスロットのみ）:
- 韓国と日本の幼児食/育児文化の違いを「○○なんだけど、日本のみんなはどう？」形式で
- 例: 「韓国ではイヤイヤ期のこと미운 두살って言うの。直訳「憎たらしい2歳」。みんなのとこのイヤイヤどう？」

例:
- "ストローマグのゴムパッキン、週1回は外して洗った方がいいらしい…私は月1だった（反省）"
- "お出かけバッグに必ず入れてるもの3つ教えて！うちは①マグ②おやつ③着替え"

【厳守ルール】
- 本文（ハッシュタグを除いた部分）は **60〜80文字以内**。これを超えたら不採用、再生成対象。
- ハッシュタグは5〜10個。本文と合わせて280加重文字以内（ハッシュタグ込み）。
- 1ツイートのみ。日本語のみ。""",
        "engage_count": 3,
        "engage_hashtags": ["#育児", "#ストローマグ", "#赤ちゃん", "#育児あるある"],
    },
    15: {
        "name": "午後 Afternoon",
        "name_ko": "오후",
        "activities": ["post", "engage_reply"],
        "post_type": "k_toddlerfood",
        "post_prompt": """午後15時のK-幼児食/K-育児紹介投稿を1つ作成してください。

テーマ: K-幼児食レシピ or K-育児アイテム or 韓国式育児のリアル
※子どもは1歳10ヶ月。離乳食は卒業済み。今は幼児食（大人に近い食事を小さく切って）。

例:
- "韓国式おやつメモ📝 野菜チヂミ。うちの子パクパク食べるんだけど日本のママ友に作り方聞かれた。小麦粉と野菜混ぜて焼くだけなのに意外と知らないよね #グロミミ #幼児食"
- "韓国の友達の家行ったら、大人のチゲからそのまま取り分けてて。日本だと子ども用に別で作るじゃん？どっちが正解とかないけど文化の違いおもしろい #グロミミ #K育児"
- "韓国の宅配おかずサービスがうらやましすぎる。幼児用のおかずセットが翌日届くの。日本にも来てくれ… #グロミミ #幼児食"

1ツイートのみ。280加重文字以内（ハッシュタグ込み）。本文は短めに（60〜80文字目安）、残りをハッシュタグ5〜10個に使う。日本語のみ。""",
        "engage_count": 3,
        "engage_hashtags": ["#育児グッズ", "#ママ垢さんと繋がりたい", "#幼児食"],
    },
    17: {
        "name": "夕 Evening",
        "name_ko": "저녁",
        "activities": ["post", "engage_reply"],
        "post_type": "daily_life",
        "post_prompt": """夕方17時の投稿を1つ作成してください。

テーマ: 夕方の育児あるある / 日常エピソード（季節感は週1〜2回程度でOK）
今月の季節モチーフ（参考）: {season_keywords}

【K-育児禁止】このスロットでは韓国要素・K-育児ネタ・韓国語混入は一切禁止。普通の日本の育児日常のみ。

例:
- "保育園のお迎え時間って一番バタバタするよね。帰ったらまずマグ洗う。毎日。永遠に"
- "今日の夕飯、冷凍うどんです。異論は認めません"
- "娘がお散歩中に落ち葉拾って「はいっ」って渡してきた。もう全部宝物にするよ🍂"

【厳守ルール】
- 本文（ハッシュタグを除いた部分）は **60〜80文字以内**。これを超えたら不採用、再生成対象。
- ハッシュタグは5〜10個。本文と合わせて280加重文字以内（ハッシュタグ込み）。
- 1ツイートのみ。日本語のみ。""",
        "engage_count": 3,
        "engage_hashtags": ["#ワンオペ育児", "#育児あるある", "#ママ垢さんと繋がりたい"],
    },
    19: {
        "name": "夜 Prime Time",
        "name_ko": "저녁 (프라임타임)",
        "activities": ["post", "engage_reply"],
        "post_type": "empathy_or_product",
        "post_prompt": """夜19時（プライムタイム）の投稿を1つ作成してください。

テーマ（以下から毎回ランダムに1つ選ぶ。同じテーマを連続して使わないこと）:
① お風呂・寝かしつけあるある（格闘、癒し、脱走など）
② 夕ごはんの育児リアル（食べない、こぼす、偏食など）
③ 仕事終わりの本音（在宅でも外出でも、疲れと達成感）
④ 製品開発裏話（試作品の失敗、素材テスト、品質へのこだわり）
⑤ ママの感情吐露（今日しんどかった、でも笑えた）
⑥ 子どもの成長エピソード（夜の一場面）
⑦ 幼児食・育児グッズのリアルな話（マグ以外も含む）
⑧ ワンオペ育児・夫婦の役割分担のリアル

トーン: カジュアル。ぼやき・本音調。丁寧語NG。スラングOK。
「うちの子」「この子」でOK（「娘（1歳10ヶ月）」は不要）。

【K-育児禁止】このスロットでは韓国要素・K-育児ネタ・韓国語混入は一切禁止。普通の日本の育児日常のみ。

絶対NG:
- 「入園準備でストローマグ〜」の書き出し（使い回しになる）
- 毎回同じパターンの書き出し
- 曜日を明記する
- 「娘（1歳10ヶ月）」「むすめ」を毎回入れる

【厳守ルール】
- 本文（ハッシュタグを除いた部分）は **60〜80文字以内**。これを超えたら不採用、再生成対象。
- ハッシュタグは5〜10個。本文と合わせて280加重文字以内（ハッシュタグ込み）。
- 1ツイートのみ。日本語のみ。""",
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
        "post_prompt": """夜21時の投稿を1つ作成してください。

テーマ: 共感ポエム / 一日の振り返り / ママへの応援
トーン: 温かい、ほっとする、「お疲れさま」感

【K-育児禁止】このスロットでは韓国要素・K-育児ネタ・韓国語混入は一切禁止。普通の日本の育児日常のみ。

例:
- "子どもが寝た後の静けさ。今日も1日お疲れさま、私。みんなも✨"
- "寝顔見てると、昼間イライラしたこと全部チャラになる不思議。明日もよろしくね"
- "今日もマグ洗って、おもちゃ片付けて、洗濯物たたんで。地味だけど、これが毎日の愛情だよね"

【厳守ルール】
- 本文（ハッシュタグを除いた部分）は **60〜80文字以内**。これを超えたら不採用、再生成対象。
- ハッシュタグは5〜10個。本文と合わせて280加重文字以内（ハッシュタグ込み）。
- 1ツイートのみ。日本語のみ。""",
        "engage_count": 3,
        "engage_hashtags": ["#育児", "#子育て", "#寝かしつけ", "#育児垢さんと繋がりたい"],
    },
    23: {
        "name": "深夜 Late Night",
        "name_ko": "심야",
        "activities": ["post", "analytics"],
        "post_type": "night_study",
        "post_prompt": """深夜23時の投稿を1つ作成してください。

テーマ: 夜中の勉強タイム / 安全性リサーチ / 夜のひとり時間
コンセプト: 子どもに安全なものを与えたくて夜中まで調べるタイプのママ

例:
- "子どもが寝た後、PPSU素材の論文読んでる。職業病かな…でも気になると調べずにいられない性格なんだよね"
- "深夜のひとり時間。幼児食のレシピ検索してたら韓国のサイトまで飛んでた。国際的な幼児食研究家になれそう（笑）"
- "夜中に赤ちゃん用品の安全基準調べてたら朝になってた…明日の私、ごめん"

1ツイートのみ。280加重文字以内（ハッシュタグ込み）。本文は短めに（60〜80文字目安）、残りをハッシュタグ5〜10個に使う。日本語のみ。""",
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
