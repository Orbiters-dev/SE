---
name: 인플루언서 조회는 seeun RAG도 확인
description: 인플루언서 정보 검색 시 SE/memory 비어 있어도 Desktop/seeun/tools/influencer_rag.py로 lookup 실행 필수.
type: feedback
---

## 규칙

SE 폴더 `memory/influencers/` 에 없다고 "메모리에 없습니다" 단정하지 말 것. Desktop/seeun/ 에 RAG 시스템 있음.

**Why:** 2026-04-21 ゆきな様 팔로우업 DM 요청 시 SE/memory/ grep만 하고 "없다" 답변 → 세은 화남 "없긴 왜 없어 이색히야". 실제로 `seeun/tools/influencer_rag.py --lookup ゆきな` 로 조회하니 STEP 10.5, ワンタッチ 300ml, 투고 예정일 등 전체 정보 나옴.

**How to apply:**

인플루언서 조회 순서 (수정판):
1. `memory/influencers/influencer_{handle}.md` Read
2. `grep -ri "{name}" memory/` (한자·히라가나·로마자·카타카나 전부)
3. **필수**: `cd c:/Users/orbit/Desktop/seeun && PYTHONIOENCODING=utf-8 python tools/influencer_rag.py --lookup {name}`
4. `grep -ri "{name}" .tmp/` `grep -ri "{name}" c:/Users/orbit/Desktop/seeun/`
5. 그래도 없으면 세은에게 확인

RAG lookup 결과로 나오는 정보(스테이지·제품·투고일·DM 로그)를 받아 본 후에는 SE 쪽에도 `memory/influencers/influencer_{handle}.md` 생성해서 다음 세션에 재검색 비용 줄이기.
