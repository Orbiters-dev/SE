---
name: 인플루언서 데이터 검색 — 항상 전체 소스 확인
description: 인플루언서 정보 확인 시 memory/ 뿐만 아니라 .tmp/docuseal_submissions, lightrag, scout_cache 등 모든 데이터 소스를 철저히 검색한 후 "없다"고 말할 것
type: feedback
---

인플루언서 정보를 찾을 때 memory/ 폴더만 보고 "없다"고 하지 마라. 반드시 아래 전체를 검색:

1. `memory/` — 메모리 파일
2. `.tmp/` 전체 (drafts, ambassador_discovery, docuseal_submissions, influencer_scout, crm_list.json, jp_pipeline_*.json)
3. `workflows/`, `tools/`
4. `lightrag/rag_storage/` — RAG 벡터 DB
5. 프로젝트 전체 grep (이름, IG 핸들)

**표기 변형 모두 시도**:
- 로마자 핸들: `monemama.life`
- 히라가나: `もねまま`
- 카타카나: `モネママ`
- 한자: 있을 경우 한자 표기
- 부분 매칭: `mone`, `もね`, `mama` 조합
- underscores/dots 변형: `monemama_life`, `mone_mama` 등

**Why:**
- 2026-04-13: DocuSeal submission에 계약 데이터 있었는데 memory/만 보고 "없다" 답변 → 세은 화남.
- 2026-04-21 (반복): monemama.life 받고 memory/에서 로마자/카타카나만 grep하고 "없다" 답변. 사실 .tmp/draft_monemama_20260420.txt에 어제 STEP 2 초안 있었음. 세은이 "있는데 없다 해 디질라고 몇 번을 처 말해야 말을 들을래?" 크게 화냄.

**How to apply:**
- 인플루언서 DM이 오면 로마자 핸들 + 일본어 표기(히라가나/카타카나) 변형 모두 `grep -ril` 또는 `grep -r` 패턴으로 프로젝트 전체(`memory/ .tmp/ workflows/ tools/`) 싹 훑기.
- "없다"는 마지막 수단. "없다"라고 할 때는 반드시 검색한 경로 + 검색 쿼리 모두 나열해서 증명.
- 한 번 훑어서 없어도 표기 변형 바꿔서 재검색. "로마자로 없다 = 일본어로도 없다"는 잘못된 가정.
- memory/influencers/ 목록에 없어도 .tmp/draft_*.txt에는 임시 작업물이 남아있을 수 있음 → 반드시 확인.
