# 연차 자동 추적 시스템 워크플로우

## 개요

Outlook COM을 통해 받은편지함을 자동 스캔하고, 휴가 신청/취소 이메일을 감지하여
Excel에 기록 + Outlook 임시저장함에 초안 저장하는 시스템.

- Azure AD / OAuth 불필요
- Claude API 선택 사항 (없으면 키워드+정규식 폴백 파서로 동작)
- Windows Task Scheduler 미사용 (삭제됨) — 수동 실행 또는 필요 시 재등록

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `tools/outlook_com_leave_tracker.py` | 메인 실행 도구 |
| `tools/employee_data.json` | 직원 입사일 + 이메일 |
| `tools/env_loader.py` | `.wat_secrets` 환경변수 로더 |
| `\\Orbiters\경영지원\연차관리\연차관리_{year}.xlsx` | 연차 기록 Excel (네트워크 공유) |
| `.tmp/leave_com_processed.json` | 처리 완료된 이메일 ID 기록 |

---

## 자동화 흐름

```
[직원] 휴가 신청/취소 이메일 발송
        ↓
[수동 실행] python tools/outlook_com_leave_tracker.py --sync
        ↓
[fetch_leave_emails] 받은편지함 스캔
  - 연차 키워드 포함 이메일 필터
  - Exchange DN → SMTP 자동 변환
  - 미처리 이메일만 선별
        ↓
[parse_leave_request] 이메일 파싱
  - Claude API 있으면 우선 사용 (정확도 높음)
  - 없으면 키워드+정규식 폴백 파서
        ↓
action == "add" ?
  ├── YES: Excel 개인 시트에 기록 → Summary 재계산
  │         → Outlook 임시저장함에 신청 확인 초안 저장
  └── NO (cancel): 해당 행 취소 처리(핑크) → Summary 재계산
                    → Outlook 임시저장함에 취소 확인 초안 저장
        ↓
[dk.shin] Outlook 임시저장함에서 초안 확인 후 직접 발송
```

---

## 이메일 발송 규칙

| 항목 | 내용 |
|------|------|
| 발신자 (From) | `dk.shin@orbiters.co.kr` 고정, 변경 불가 |
| 수신자 (To) | 해당 직원 본인 (`@orbiters.co.kr` 내부만) |
| 참조 (CC) | `wj.choi@orbiters.co.kr`, `mj.lee@orbiters.co.kr` |
| 자동 발송 | **전면 금지** — 모든 메일은 임시저장함 경유 후 수동 발송 |
| 외부 주소 | 자동 차단 (To/CC 모두) |

---

## 이메일 템플릿 구성

**신청 확인 메일 (연차/반차)**
- 신청자 / 휴가 유형 / 일자·기간 / 총 사용일수 / 비고(있을 때)
- 잔여 현황 테이블:

  | 현재 잔여 연차 | 사용 연차 | 최종 잔여 연차 |
  |:---:|:---:|:---:|
  | 이번 신청 전 잔여 | 이번 신청 일수 | 이번 신청 후 잔여 |

- ※ '발생(alloc)' 항목은 표시하지 않는다

**신청 확인 메일 (비연차 휴가)**
- 날짜 정보 + 휴가 구분만 표시 (잔여 테이블 없음)

**취소 확인 메일**
- 취소 대상 날짜 목록
- 현재 잔여 연차 (취소분 복구 반영)
- 마무리 문구: "해당 일정이 정상적으로 복구되었음을 알려드립니다."

---

## 연차 계산 기준

**회계연도 기준** — `date(ref_year, 12, 31)` 기준으로 연간 고정값 산출

| 근속 기간 | 발생 일수 |
|-----------|-----------|
| 1년 미만 | 완성 근속 월 수 (최대 11일) |
| 1년 이상 | 15일 |
| 3년 이상 | 16일 |
| 5년 이상 | 17일 |
| (2년마다 +1일, 최대 25일) | |

**연차 차감 대상**: 연차, 반차만 차감. 나머지는 별도 집계.

---

## 휴가 유형 및 정책 (취업규칙 기준)

| 유형 | 연차 차감 | 연간 한도 | 유급 |
|------|-----------|-----------|------|
| 연차 | O | 개인별 발생 | 전부 |
| 반차 | O (0.5일) | 동일 | 전부 |
| 본인 결혼 | X | 5일 | 전부 |
| 배우자 출산 | X | 10일 | 전부 |
| 배우자/부모 사망 | X | 5일 | 전부 |
| 조부모/외조부모 사망 | X | 3일 | 전부 |
| 자녀/자녀배우자 사망 | X | 3일 | 전부 |
| 형제자매 사망 | X | 1일 | 전부 |
| 난임치료 | X | 6일 | 최초 2일만 |
| 병가 | X | 30일 | 무급 |
| 생리휴가 | X | 월 1일 | 무급 |
| 공가 | X | 없음 | - |
| 예비군/민방위 | X | 없음 | - |

---

## 직원 데이터 (`tools/employee_data.json`)

입사일 및 이메일 등록. 변경 시 JSON 직접 수정.

```json
{
  "hire_dates": { "이름": "YYYY-MM-DD", ... },
  "emails":     { "이름": "email@orbiters.co.kr", ... }
}
```

현재 등록 인원: 유희찬, 전지후, 현지선, 심원기, 김은빈, 카즈키, Calvin, 서소연, 허세은, 신동균

---

## 환경 변수 (`.wat_secrets`)

```
OUTLOOK_EMAIL=dk.shin@orbiters.co.kr
LEAVE_TEAM_EMAILS=wj.choi@orbiters.co.kr,mj.lee@orbiters.co.kr
ANTHROPIC_API_KEY=sk-ant-...  (선택, 없어도 동작 — 단 오파싱 위험 증가)
```

---

## 수동 실행 명령어

```bash
# Excel 초기 생성
uv run --with openpyxl --with pywin32 --with holidays python tools/outlook_com_leave_tracker.py --setup

# 이메일 스캔 + 처리 + 임시저장 초안 생성
uv run --with openpyxl --with pywin32 --with holidays python tools/outlook_com_leave_tracker.py --sync
```

---

## Excel 구조

**Summary 시트**
- 열: 이름 / 이메일 / 1월~12월 / 총사용 / 잔여

**개인 시트 (이름별)**
- 열: 신청일 / 이메일 제목 / 휴가 시작 / 휴가 종료 / 사용일수 / 유형 / 비고 / 상태
- 취소 행: 핑크 배경 + 상태="취소"

---

## 키워드 파서 인식 패턴

날짜 포맷: `2026-03-12`, `2026.03.12`, `3월 12일`, `3/12`

취소 키워드: `취소`, `철회`

휴가 유형 키워드 (우선순위 순):
배우자 출산 → 난임 → 조부모/외조부모 → 자녀 → 형제/자매 → 신혼/결혼 → 사망/장례 → 반차 → 병가 → 공가 → 민방위 → 예비군 → 생리휴가 → 연차 → 휴가

---

## 알려진 제약사항 및 주의사항

- Outlook 데스크탑 앱이 실행 중이어야 동작
- Exchange 내부 주소는 자동으로 SMTP 변환 처리
- 이름 기반 매칭 — 이메일 발신자명으로 직원 식별
- C-level (대표/이사) 제외 — `employee_data.json` 미등록 시 자동 제외
- **Claude API 크레딧 소진 시**: regex 폴백 파서로 동작하나 오파싱 위험 있음
  - 특히 외부 업체 메일에 내부 직원이 회신한 경우 오인식 가능
  - 파싱 결과 이상 시 `.tmp/leave_com_processed.json` 초기화 후 재실행
  - Excel 잘못 기록된 행은 직접 삭제 후 `rebuild_summary` 재실행 필요