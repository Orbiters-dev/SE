# Mistakes Memory — 행동 규칙 (압축본)

일회성 코드 버그는 git history에 있으므로 여기서 삭제.
CLAUDE.md에 이미 있는 규칙(cp949, curl -sk, n8n active)도 삭제.
**반복될 수 있는 행동 패턴만** 남김. (2026-04-10 정리)

---

## 1. "없다" 단언 금지

데이터든 워크플로우든, 없다고 하기 전에 반드시 확인.

- SKU 데이터 "없다" → 실제로는 stale data가 원인 (M-041)
- n8n 워크플로우 "없다" → 실제로 이미 active (M-043)
- **규칙**: 3곳 이상 확인(API 검색, 파일 grep, 세은에게 질문) 후에만 "없다" 결론

---

## 2. API 응답은 겉과 속이 다를 수 있음

- HTTP 200이지만 개별 항목은 거부됨 — body의 각 item `code` 필드 반드시 검증 (M-027)
- API `count` = 반환된 행 수 ≠ 전체 행 수 — total vs returned 항상 비교 (M-046, M-052)
- 페이지네이션 누락 시 일부만 처리됨 — 불일치 시 추가 페이지 요청

---

## 3. Amazon Ads API 고유 규칙

- ID 필드(campaignId, adGroupId)는 반드시 **string**으로 전송 (M-023)
- 브랜드 판별은 campaignName이 아니라 **명시적 brand_key** 사용 (M-030)
- state filter는 대문자: `ENABLED`, `PAUSED`, `ARCHIVED` (M-025)

---

## 4. 대량 작업 전 범위 확인

- 이메일 27K 전체 인덱싱 시작 → 세은: "읽을 필요 없음" (M-017)
- 33K 전체 인덱싱 → 세은: "collab 키워드만" (M-018)
- **규칙**: 대량 작업(1000건+) 전 세은에게 범위 확인. 필터 조건 먼저 설정

---

## 5. GitHub Actions 환경 = 매번 백지

- `.tmp/`는 ephemeral — Actions에서 매번 사라짐. 히스토리는 git-committed 파일 또는 DB에서 로드 (M-028)
- 누적 데이터는 기존 output에서 merge 필수 — 새 데이터만 쓰면 이전 데이터 소실 (M-029)
- org repo workflow dispatch는 **Classic PAT** 필수 — fine-grained PAT은 403 (M-031)

---

## 6. 데이터 정합성

- PG upsert ≠ full replace — 분류 로직 변경 후 stale rows 수동 정리 필요 (M-020)
- 브랜드 분류: 캡션/해시태그 > 주문 데이터. 주문은 폴백으로만 (M-050)
- Onzenna = 스토어프론트, 브랜드 아님. 브랜드 regex에 넣지 않기 (M-051)

---

## 7. 콘텐츠 처리 규칙

- 콘텐츠 텍스트 **절대 자르지 않기** — 긴 내용은 expandable UI로 (M-047)
- 표시 우선순위: **Transcript > Text > Caption** (M-048)

---

## 8. 파일 저장 위치

- 팀/멀티컴터 공유 파일 → 프로젝트 폴더 (SynologyDrive) 안 `memory/` (M-005)
- `~/.claude/`는 로컬 전용 — 다른 컴퓨터에서 안 보임
