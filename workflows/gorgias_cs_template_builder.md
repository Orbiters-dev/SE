# Workflow: Gorgias CS Template Library 자동 생성

## Objective

Gorgias 최근 6개월 closed 티켓의 전체 대화를 분석하여, **고객 불만 유형별 표준 CS 답변 템플릿**을 자동으로 생성하고 Google Sheets에 저장합니다.

자동화/외주 담당자가 이 템플릿을 보고 대부분의 CS 이슈를 스스로 처리할 수 있도록 하는 것이 목표입니다.

---

## Prerequisites

### .env 필수 키

```
GORGIAS_DOMAIN=zzbb
GORGIAS_EMAIL=your@email.com
GORGIAS_API_KEY=your_api_key
ANTHROPIC_API_KEY=your_claude_key
GOOGLE_SERVICE_ACCOUNT_PATH=credentials/google_service_account.json
GORGIAS_CS_SHEET_ID=1Y1hrdqGZxe3KPlA0rT38B3Tc_q84sP4PumAq25j6zkg
```

### Google Service Account 설정 (최초 1회)

1. [Google Cloud Console](https://console.cloud.google.com/) → IAM & Admin → Service Accounts
2. 새 Service Account 생성 (이름 예: `cs-template-builder`)
3. 키 생성: Keys → Add Key → Create New Key → JSON → 다운로드
4. 다운받은 JSON을 `credentials/google_service_account.json`에 저장
5. JSON 파일 안의 `client_email` 값 복사
6. [Google Sheets](https://docs.google.com/spreadsheets/d/1Y1hrdqGZxe3KPlA0rT38B3Tc_q84sP4PumAq25j6zkg) → 공유 → 해당 이메일 편집자로 추가

### 의존성

```bash
pip install gspread google-auth anthropic requests openpyxl python-dotenv
```

---

## How to Run

```bash
# 1단계: 먼저 dry-run으로 결과 확인 (Google Sheets 기록 안 함)
python tools/gorgias_cs_template_builder.py --dry-run

# 2단계: 결과 검토 후 실제 Google Sheets에 기록
python tools/gorgias_cs_template_builder.py
```

### CLI 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--months` | `6` | 몇 개월 전부터 closed 티켓 수집 |
| `--min-messages` | `2` | 최소 메시지 수 (고객↔상담원 교환이 있는 티켓만) |
| `--dry-run` | false | Google Sheets 기록 생략, 로컬 Excel만 저장 |

---

## What It Does

### Step 1 — Closed 티켓 수집
- `GET /api/tickets?status=closed&limit=100` 커서 기반 페이지네이션
- `created_datetime`으로 N개월 이내 필터링
- 메시지 수 >= min-messages 티켓만 선별

### Step 2 & 3 — 대화 수집 + Claude Haiku 분류
각 티켓에 대해:
1. `GET /api/tickets/{id}/messages` — 전체 메시지 스레드 수집
2. customer/agent 레이블로 대화 포맷팅
3. **Claude Haiku**로 분류 (저비용):
   - `problem_category`: Shipping / Returns & Refunds / Product Issue / Order Change/Cancel / Payment & Billing / Account & Login / Wholesale/B2B / Generic / Other
   - `resolution_category`: Provide information / Process refund / Process replacement / Update order / Apologize / Escalate / Close
   - 고객 컴플레인 요약 + 상담원 해결 방법 요약

### Step 4 — 그룹핑 + Claude Sonnet 템플릿 합성
- `(problem_category, resolution_category)` 조합별 그룹핑
- 각 그룹에서 대표 사례 최대 5개 추출
- **Claude Sonnet**으로 합성 (고품질):
  - 고객 최초문의 요약 (영어)
  - 권장 첫 답변 템플릿 (`{{ticket.customer.firstname}}` 변수 포함, 영어)
  - 내부 체크리스트 (• 불릿 형식)
  - 금지/주의 표현

### Step 5 — Google Sheets 기록
- `gspread` + Service Account JSON 인증
- `CS_Template_Library` 시트에 헤더 + 데이터 기록
- 헤더 볼드체 적용

### Step 6 — 로컬 Excel 백업
- `.tmp/gorgias_cs_template_builder/cs_templates_YYYY-MM-DD.xlsx`

---

## 출력 컬럼 (CS_Template_Library_Readable 형식)

| 컬럼 | 설명 |
|------|------|
| `pattern_id` | CS-001, CS-002, ... |
| `problem_category` | Shipping / Returns & Refunds / Product Issue 등 |
| `resolution_category` | Provide information / Process refund 등 |
| `macro_name` | 짧은 이름 (예: "Shipping: Delayed Order") |
| `고객 최초문의 요약(영어)` | 이 유형의 고객 문의 상황 설명 |
| `권장 첫 답변(영어)` | 실제 사용 가능한 답변 템플릿 |
| `체크리스트(내부)` | 답변 전 내부 확인 사항 |
| `금지/주의 표현` | 쓰면 안 되거나 주의할 표현 |
| `업데이트 로그` | v1 YYYY-MM-DD: auto-generated from N tickets |

---

## Expected Output

**Google Sheets:**
https://docs.google.com/spreadsheets/d/1Y1hrdqGZxe3KPlA0rT38B3Tc_q84sP4PumAq25j6zkg

**로컬 Excel:**
`.tmp/gorgias_cs_template_builder/cs_templates_YYYY-MM-DD.xlsx`

---

## 비용 예상

- Claude Haiku (티켓 분류): 티켓 100개 기준 약 $0.03
- Claude Sonnet (템플릿 합성): 카테고리 20개 기준 약 $0.18
- **전체 약 $0.25 이내** (Gorgias API는 무료)

---

## Edge Cases & Notes

- **분류 실패 티켓**: JSON 파싱 실패 시 skip하고 계속 진행 (분석 중단 없음)
- **템플릿 합성 실패**: 최소 폴백 템플릿 자동 생성 (수동 작성 안내 포함)
- **Google Sheets 오류**: 로컬 Excel 백업은 항상 저장됨
- **도매/B2B 티켓**: Wholesale/B2B 카테고리로 분류되므로 CS vs 영업팀 구분 필요
- **커서 페이지네이션**: Gorgias tickets API는 page 파라미터 미지원, cursor 사용
- **Python 경로 (Windows)**: `C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe`

---

## Lessons Learned

- Gorgias 메시지 API: 최대 30건/페이지, 커서 기반 페이지네이션 필요
- 대화 텍스트 truncation 필수 (Claude 비용 절감): 메시지당 1200자, 분류 프롬프트 2500자
- `from_agent` 또는 `sender.type == "agent"` 로 상담원 판별
- Google Sheets API 속도 제한: `append_row` 호출 간 0.3초 딜레이 필요
- `gspread.WorksheetNotFound` 예외로 신규/기존 시트 분기 처리
