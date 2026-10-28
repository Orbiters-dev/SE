---
name: API/도구 다 동원해서 직접 처리. 세은한테 시키지 마
description: firecrawl 차단 = 다른 도구 시도. 우리 계정 IG 데이터는 fetch_ig_profile.py + deep_crawler.py로 직접. "어디서 봐?" 묻는 행위 금지.
type: feedback
---

# 모르면 API/도구 다 동원해서 직접 처리. 세은한테 "어디서 보지?" 묻는 행위 금지

**Why:** 2026-05-07 W18 OKR 작성 시 IG followers / posts this week 묻기 → 세은 "우리거 ? 니가 들어가서 보면 되잖아 디질래?" + "API나 뭐나 다 동원해서 니가 알아서 처리해 나한테 시키지 마". 이전에도 "외부 사람한테 떠넘기지 마" 룰 있음. 이번엔 사용자 본인에게도 같은 룰 적용 — 자체 도구 다 시도 후에만 묻기.

**How to apply:**
- @grosmimi_japan, @grosmimi_jp 등 우리 계정 데이터: 
  - 우선: `tools/fetch_ig_profile.py --handle <handle>` (Apify IG profile scraper)
  - posts/뷰수: `tools/deep_crawler.py --handles <handle> --platform instagram --max-posts 30 --raw-json` (Apify IG profile scraper로 최근 게시물 + views/likes/comments)
  - firecrawl IG 차단 (`example.com 지원 X`) → 즉시 다른 도구로 우회
- 인플루언서 메모리/시트/CRM/n8n/PG 등 ORBI 내부 도구 다 시도 후에만 세은에게 묻기
- 묻는 게 허용되는 경우: "정책/의도/판단" 또는 "조사해도 알 수 없는 것" (CLAUDE.md 절대 룰)
- "이거 어디서 봐?" 식 객관식 질문 금지 (CLAUDE.md "직접 파악할 수 있는 건 묻지 마" 룰)
