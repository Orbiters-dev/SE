# Workflow: Gorgias 대화 분석 (Top 5 고활동 티켓)

## Objective

Gorgias에서 3회 이상 이메일을 주고받은 티켓 중 상위 5개를 자동 선별하여,
**고객명 / 오더넘버 / 날짜별 기록 / 대화 내용 / 주요 컴플레인 키워드**를 Excel로 정리합니다.

---

## Prerequisites

- `.env`에 아래 4개 키가 설정되어 있어야 합니다:
  - `GORGIAS_DOMAIN` — Gorgias 서브도메인 (예: `zzbb`)
  - `GORGIAS_EMAIL` — Gorgias 계정 이메일
  - `GORGIAS_API_KEY` — Gorgias API 토큰
  - `ANTHROPIC_API_KEY` — Claude AI 키워드 추출용
- 의존성 설치: `pip install -r requirements.txt`

---

## Inputs

| Input | CLI 인수 | 기본값 | 설명 |
|-------|----------|--------|------|
| 최소 메시지 수 | `--min-messages` | `3` | 이 수 이상 메시지가 있는 티켓만 분석 |
| 분석 티켓 수 | `--top` | `5` | 메시지 수 기준 상위 N개 선택 |
| 티켓 상태 | `--status` | `all` | `all` / `open` / `closed` |

---

## How to Run

```bash
# 기본 실행 (메시지 3개 이상, 상위 5개, 전체 상태)
python workflows/gorgias_analyze/gorgias_analyze.py

# 메시지 5개 이상, 상위 3개만, closed 티켓
python workflows/gorgias_analyze/gorgias_analyze.py --min-messages 5 --top 3 --status closed
```

---

## What It Does

### Step 1 — 전체 티켓 수집 + 필터링
- `GET /api/tickets?status=all&limit=100` 페이지네이션으로 전체 티켓 수집
- `messages_count >= --min-messages` 필터 적용
- `messages_count` 내림차순 정렬 → 상위 `--top`개 선택

### Step 2 — 각 티켓 상세 분석
각 선정 티켓에 대해:
1. `GET /api/tickets/{id}` → `custom_fields` 배열에서 오더넘버 탐색
2. `GET /api/tickets/{id}/messages` → 전체 메시지 스레드 수집
3. **오더넘버 추출** (이중 탐색):
   - `custom_fields`에서 name에 'order' 포함 필드 우선 확인
   - 없으면 메시지 본문에서 regex: `#1234`, `Order: 5678`, `ORD-9012` 패턴 검색
4. **대화 포맷팅**: `[날짜 시간] 고객/상담원: 내용` 형태로 정리
5. **Claude AI 키워드 추출**: 대화 내용을 Claude Haiku에 전송하여 컴플레인 키워드 5개 이내 추출

### Step 3 — Excel 내보내기
- `.tmp/` 폴더에 타임스탬프 포함 파일명으로 저장
- 셀 wrap_text 적용, 고정 컬럼 너비

---

## Expected Output

**파일명:** `.tmp/gorgias_analysis_YYYY-MM-DD_HHMMSS.xlsx`

| 컬럼 | 내용 예시 |
|------|-----------|
| 상대 이름 | Kim Minsu |
| 계정 오더넘버 | 12345 |
| 이메일 회신 날짜별 기록 | `[2026-01-05 14:22] 고객: 주문이 안 왔어요...` |
| 대화 내용 | 전체 스레드 텍스트 |
| 주요 컴플레인 키워드 | 배송 지연, 환불 요청, 응답 없음 |

---

## Edge Cases & Notes

- **오더넘버 없음**: 빈칸 처리 (오류 아님) — custom_fields 구조가 다를 수 있음
- **Claude API 실패**: 키워드 빈칸 처리 후 계속 진행 (분석 중단 없음)
- **메시지 본문 없음**: body_text가 없으면 빈 문자열로 처리
- **대화 텍스트 길이 제한**: Claude 프롬프트 입력은 3000자로 자동 잘림 (토큰 비용 절감)
- **발신자 판별**: `from_agent=True` 또는 `sender.type == "agent"` → 상담원, 나머지 → 고객

---

## Lessons Learned

- **페이지네이션**: Gorgias tickets API는 `page` 파라미터 미지원, 커서 기반(`cursor`) 사용
- **order_by 형식**: `created_datetime:desc` 형태로 방향 포함 (별도 `order_direction` 없음)
- **messages API 한계**: 메시지도 최대 30건/페이지, 커서 페이지네이션 필요
- **최다 메시지 티켓**: 도매/협업 문의 이메일이 top에 올 수 있음 — 고객 컴플레인만 보려면 `--status closed` + subject/태그 필터 추가 고려
- **오더넘버**: custom_fields 구조 확인 필요, 기본 티켓에는 없을 수 있음
- **Python 경로 (Windows)**: `python` 명령이 MS Store stub이므로 전체 경로 사용:
  `C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe`
