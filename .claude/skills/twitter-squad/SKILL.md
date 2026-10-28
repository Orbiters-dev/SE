---
name: twitter-squad
description: >
  ツイッター部隊 — @grosmimi_jp 계정 통합 운영 에이전트.
  기획→승인→투고→댓글→조사 6 부대(総監督/監督/企画マン/ツイート/コメンター/調査マン/ハッシュタグ調査マン)를 GitHub Actions로 자동화한다.
  주간 35개 트윗 플랜 생성 + Excel 승인 + 매일 2회 자동 투고 + 공감 댓글 + 경쟁 조사를 담당한다.

  트리거: "ツイッター部隊", "트위터 부대", "Twitter 부대", "총감독", "감독", "기획맨",
  "코멘터", "조사맨", "해시태그 조사", "twitter squad", "soukantoku", "kantoku",
  "kikaku", "commenter", "chousa".
---

# ツイッター部隊 — Grosmimi Japan Twitter Squad

@grosmimi_jp 계정 운영 전체(기획→승인→투고→댓글→조사) 자동화 에이전트.

---

## 부대 구성·서열

```
総監督 (soukantoku.py)
  └─ 監督 (twitter_supervisor.py)
       ├─ 企画マン (twitter_scheduler.py --generate-weekly)
       ├─ ツイート (twitter_scheduler.py --slot 10/19)
       ├─ コメンター (twitter_engage.py --limit 1)
       ├─ 調査マン (twitter_research.py)
       └─ ハッシュタグ調査マン (twitter_hashtag.py)
```

| 이름 | 역할 | 실행 시간 (JST) | 도구 | GitHub Actions |
|------|------|----------------|------|---------------|
| **総監督** | 어제 전 부대 실적 Teams 보고 | 매일 09:00 | `tools/soukantoku.py` | `soukantoku.yml` |
| **監督** | 오늘 투고 예정·승인 상태 Teams 보고 | 매일 09:00 | `tools/twitter_supervisor.py` | `kantoku.yml` |
| **企画マン** | 다음주 7일분 트윗 플랜 생성 → Excel → Teams | 매주 금 09:00 | `twitter_scheduler.py --generate-weekly` | `kikaku.yml` |
| **ツイート** | 승인된 트윗 자동 투고 | 매일 10:00 / 19:00 | `twitter_scheduler.py --slot` | `tweet.yml` |
| **コメンター** | 육아 트윗에 공감 댓글 (1회 1명) | 매일 12~16시 (5회) | `tools/twitter_engage.py --limit 1` | `commenter.yml` |
| **調査マン** | 경쟁 브랜드 트위터 운영 조사 → Teams | 매주 수·금 09:00 | `tools/twitter_research.py` | `chousa.yml` |
| **ハッシュタグ調査マン** | 인기 해시태그 전체·육아 조사 → Teams | 매주 금 09:00 | `tools/twitter_hashtag.py` | `hashtag.yml` |

---

## 주간 플로우

```
금요일 09:00 — 企画マン: 다음주 7일분 플랜 생성 + Excel + Teams
금~일 — 담당자: Excel F열 승인 (Confirmed/Declined+대안)
월~일 매일:
  09:00 総監督 + 監督 보고
  10:00 ツイート 아침 투고
  12~16시 コメンター 공감 댓글 5회
  19:00 ツイート 저녁 투고
  수·금 09:00 調査マン 경쟁 조사
  금 09:00 ハッシュタグ調査マン
```

---

## 콘텐츠 카테고리 (企画マン 자동 로테이션)

| 카테고리 | 내용 | 슬롯 |
|----------|------|------|
| `meme` | 이야이야기 あるある, 육아 유머 | 10:00 |
| `tips` | 유아식·컵 마시기·재우기 실용 팁 | 10:00 |
| `brand` | 그로미미 제품 1세 10개월 사용 장면 | 19:00 |
| `k_babyfood` | 한국식 유아식 트렌드 소개 | 19:00 |
| `lifestyle` | 1세 10개월과의 일상·성장 기록 | 19:00 |

---

## 승인 룰 (Excel F열)

| F열 | G열 (대안) | 동작 |
|-----|-----------|------|
| Confirmed | 불필요 | 플랜 그대로 투고 |
| Declined | 텍스트 있음 | G열 텍스트로 투고 |
| Declined | 빈칸 | 스킵 |
| 빈칸 | — | 투고 안 함 (승인 대기) |

---

## コメンター 필터 룰

- **BLOCKED_ACCOUNTS**: pigeon, combi, richell, nuk, boon, munchkin, thermos 등 경쟁·자사
- **BLOCKED_KEYWORDS**: 漫画, アニメ, 声優, コスプレ, VTuber, にじさんじ, ホロライブ 등
- 키워드 필터 → Claude 판정 순서. 남성·기업 계정 스킵

---

## 추가 도구

| 도구 | 역할 |
|------|------|
| `tools/apify_twitter_monitor.py` | Apify로 트위터 모니터링 |
| `tools/apify_twitter_trends.py` | Apify로 트위터 트렌드 수집 |
| `tools/twitter_agent.py` | 트위터 에이전트 코어 |
| `tools/twitter_analytics.py` | 트위터 분석 |
| `tools/twitter_post.py` | 트윗 투고 |
| `tools/twitter_reply.py` | 트윗 답글 |
| `tools/twitter_trends.py` | 트렌드 수집 |
| `tools/twitter_utils.py` | 유틸리티 |

---

## 워크플로우

- `workflows/twitter_daily_posting.md` — ツイッター部隊 전체 운영 SOP