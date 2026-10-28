---
name: 인플루언서 핸들만 받으면 firecrawl로 IG 직접 조회 (월령/호칭 떠넘김 X)
description: SNS 핸들만 받았을 때 호칭·월령·자녀 정보를 세은한테 묻기 X — firecrawl search로 IG 프로필 + 게시물 cache 조회해 월령·본명 자체 추정
type: feedback
---

# 핸들 받으면 firecrawl로 직접 조회 — 월령·호칭 떠넘김 X

**Why:** 2026-06-04 @natsu_8au 리치아웃 요청에 「호칭 + 월령 알려주시면 마무리할게요」 떠넘김 답변. CLAUDE.md 「직접 파악할 수 있는 건 묻지 마 — 무조건 직접 조사」 + 「검증 한 번 = 도구 한 개로 끝나면 안 됨」 룰 위반. 「ㅅㅂ 니가 체크한다매 아 씨발 또 시작이네」 강한 교정.

firecrawl scrape 는 인스타그램 직접 미지원(Error 회신). 하지만 firecrawl search 로 IG cache (Google 결과) 조회는 가능 — 프로필 description / 게시물 캡션에서 자녀 월령·본명 단서 충분히 추출.

**How to apply (핸들 받으면 첫 액션 시퀀스):**
1. `grep -rli "<handle>" memory/` — 기존 메모리 확인
2. `firecrawl search "<handle> instagram プロフィール" --limit 5 --json` — 프로필 + 최신 게시물 cache
3. 月齢 단서 없으면 `firecrawl search "<handle> 月齢 OR 歳 OR ヶ月 OR baby"` 2차
4. 결과에서 추출:
   - **본명** (Tomoya Nagata 같이 영문 표기 / 한자 性名) → 「{성}様」
   - **닉네임** (자녀 이름 / なつ 등) → 본명 없으면 「○○ママ様」 / 「○○様」
   - **자녀 생년월일 / 月齢** (「2024.11.04」 / 「1歳5ヶ月」 / 「baby」 + 시점) → 오늘 기준 산출
5. 산출 월령으로 워크플로우 분기 (PPSU / ワンタッチ / ステンレス / 대상 외)
6. 추정 근거 + 단정 가능 여부 같이 보고 — 단정 X면 「확인 못 함」 명시
7. 세은한테는 정책 영역만 (대상 외 진행할지 / 호칭 한자 추정 OK인지)

**금지 표현:** 「호칭(SNS 닉네임 또는 ○○様)과 자녀 월령 알려주시면 마무리할게요」 — 세은이 직접 IG 들여다보지 않아도 firecrawl search 한 번이면 단서 잡힘
