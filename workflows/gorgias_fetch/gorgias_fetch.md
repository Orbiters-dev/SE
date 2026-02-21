# Workflow: Fetch Gorgias Tickets and Customer Info

## Objective

Gorgias 헬프데스크 REST API에서 **티켓 목록** 또는 **고객 정보**를 조회하여 로컬 Excel 파일로 내보냅니다.

---

## Prerequisites

- `.env`에 아래 3개 키가 설정되어 있어야 합니다:
  - `GORGIAS_DOMAIN` — Gorgias 서브도메인 (예: `zzbb`)
  - `GORGIAS_EMAIL` — Gorgias 계정 이메일
  - `GORGIAS_API_KEY` — Gorgias API 토큰
- 의존성 설치: `pip install -r requirements.txt`

---

## Inputs

| Input | CLI 인수 | 기본값 | 설명 |
|-------|----------|--------|------|
| 모드 선택 | `--tickets` 또는 `--customer` | 필수 | 어떤 데이터를 가져올지 선택 |
| 티켓 상태 | `--status` | `open` | `open` / `closed` / `all` |
| 최대 건수 | `--limit` | `100` | 가져올 최대 티켓 수 |
| 고객 ID | `--customer-id` | - | 티켓 모드: 특정 고객 티켓만 필터 |
| 고객 이메일 | `--email` | - | 고객 모드: 이메일로 검색 |
| 고객 숫자 ID | `--id` | - | 고객 모드: ID로 직접 조회 |

---

## How to Run

```bash
# 티켓 조회 (기본: open 상태, 최대 100건)
python workflows/gorgias_fetch/gorgias_fetch.py --tickets

# 티켓 조회 (closed, 최대 50건)
python workflows/gorgias_fetch/gorgias_fetch.py --tickets --status closed --limit 50

# 특정 고객의 모든 티켓 조회
python workflows/gorgias_fetch/gorgias_fetch.py --tickets --customer-id 12345

# 고객 정보 조회 (이메일)
python workflows/gorgias_fetch/gorgias_fetch.py --customer --email someone@example.com

# 고객 정보 조회 (숫자 ID)
python workflows/gorgias_fetch/gorgias_fetch.py --customer --id 12345
```

---

## What It Does

### Step 1 — API 인증 및 데이터 조회
- HTTP Basic Auth (`email:api_key`) 방식으로 Gorgias REST API에 인증
- 티켓 모드: `GET /api/tickets`를 페이지네이션하며 최대 `--limit`건 수집
- 고객 모드: `GET /api/customers/{id}` 또는 `GET /api/customers?email=...` 호출

### Step 2 — 중첩 필드 정규화
- Gorgias 응답의 중첩 객체(customer{}, assignee_user{}, channels[])를 평탄화
- 누락 필드는 빈 문자열로 처리

### Step 3 — Excel 내보내기
- `.tmp/` 폴더에 타임스탬프 포함 파일명으로 저장
- 헤더 Bold, 컬럼 자동 너비

---

## Expected Output

### 티켓 Excel (12 컬럼)
1. Ticket ID
2. Status
3. Subject
4. Channel
5. Created At
6. Updated At
7. Assignee
8. Customer Name
9. Customer Email
10. Tags
11. Message Count
12. Ticket URL

**파일명:** `.tmp/gorgias_tickets_{status}_YYYY-MM-DD_HHMMSS.xlsx`

### 고객 Excel (10 컬럼)
1. Customer ID
2. Name
3. Email
4. Phone
5. Created At
6. Updated At
7. External ID
8. Note
9. Tags
10. Channels

**파일명:** `.tmp/gorgias_customer_{email|id}_YYYY-MM-DD_HHMMSS.xlsx`

---

## Edge Cases & Notes

- **401 Unauthorized**: `GORGIAS_EMAIL`과 `GORGIAS_API_KEY`가 올바른지 확인
- **404 on customer ID**: 해당 ID가 존재하지 않음
- **이메일 검색 결과 없음**: 고객 미발견, Excel 파일 미생성 후 종료
- **페이지네이션**: Gorgias 최대 100건/페이지. `--limit`이 100 초과 시 자동으로 여러 페이지 조회
- **assignee 없는 티켓**: 정규화 함수에서 빈 문자열로 처리, 오류 없음
- **Rate limit**: 순차 조회 방식이라 위험 낮음. 429 에러 시 HTTPError로 포착 후 명확한 메시지 출력

---

## Lessons Learned

*(첫 실행 후 발견된 API 특이사항을 여기에 기록)*
