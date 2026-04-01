# 휴가 승인 워크플로우

## 목적

Outlook 메일 수신 시 휴가 신청을 자동 감지하고, 승인 회신 드래프트를 생성한 뒤,
실제 발송 완료 시 NAS 엑셀에 자동 반영하는 2-Phase 워크플로우.

## 아키텍처

```
Phase 1: 받은편지함 감시
  📧 @orbiters.co.kr 에서 메일 수신
    → 🔍 제목/본문에서 휴가/연차/반차 키워드 감지
    → 🤖 Claude AI로 자유형 본문 파싱 (이름, 날짜, 유형 추출)
    → 📊 NAS 엑셀에서 잔여 연차 조회
    → ✉️ Outlook 임시저장에 승인 회신 드래프트 생성

  [담당자(동균)가 드래프트 확인 → 필요시 수정 → 발송]

Phase 2: 보낸편지함 감시
  📤 "[휴가 승인]" 제목 메일 발송 감지
    → 📋 pending 목록에서 매칭
    → 📊 NAS 엑셀 업데이트
      - Confirm 시트: 승인 로그 추가
      - 개인 시트: 해당 직원 시트에 기록
      - Summary 시트: 월별 사용일수 + 잔여 업데이트
```

## 실행 방법

| 명령 | 설명 |
|------|------|
| `python tools/leave_workflow.py --run` | Phase 1 + 2 모두 실행 |
| `python tools/leave_workflow.py --draft-only` | Phase 1만 (드래프트 생성) |
| `python tools/leave_workflow.py --sync-only` | Phase 2만 (엑셀 업데이트) |
| `python tools/leave_workflow.py --dry-run` | 테스트 (변경 없음) |
| `python tools/leave_workflow.py --status` | 상태 확인 |
| `python tools/leave_workflow.py --run --hours 12` | 최근 12시간 범위 감시 |

## 메일 설정

| 항목 | 값 |
|------|-----|
| 수신 감시 | `*@orbiters.co.kr` 발신 메일만 |
| 발송 (드래프트) | `dk.shin@orbiters.co.kr` |
| 참조 (CC) | `wj.choi@orbiters.co.kr`, `mj.lee@orbiters.co.kr` |
| 승인 제목 패턴 | `[휴가 승인] {이름} 님 휴가 승인 안내` |

## 승인 회신 템플릿

```
안녕하세요, {이름} 님.
경영지원 담당자 신동균입니다.

신청하신 휴가 일정이 아래와 같이 승인되었음을 안내드립니다.

  시작일      {날짜} ({요일})
  사용 일수   {일수}
  휴가 구분   {연차/반차}

[ 연차 잔여 현황 ]
  기존 연차   사용 연차   잔여 연차
  {기존}      {사용}      {잔여}

휴가 기간 동안 재충전의 시간 되시길 바랍니다.

감사합니다.
경영지원 신동균 드림
```

## 엑셀 파일

- 경로: `\\Orbiters\경영지원\연차관리\연차관리_2026.xlsx`
- Confirm 시트: 전체 승인 로그
- 개인 시트: 직원별 사용 내역
- Summary 시트: 월별 사용량 + 잔여 연차

## 자동화

Task Scheduler: `Leave Workflow Auto` — 5분마다 `--run` 실행

## 파싱 지원 형식

자유형 본문 모두 지원 (Claude AI 파싱):
- "3월 31일 연차 사용하고 싶습니다"
- "신청일: 2026년 3월 26일 / 반차 시간: 오전"
- "3월 11일 오후 반차 사용하고자 합니다"

## 의존성

- msal (Microsoft Graph API 인증)
- anthropic (Claude AI 파싱)
- openpyxl (엑셀 읽기/쓰기)
- requests
- holidays (공휴일 계산, 선택)

## 데이터 파일

| 파일 | 용도 |
|------|------|
| `.tmp/leave_pending_drafts.json` | Phase 1 → Phase 2 연결용 대기 목록 |
| `.tmp/leave_inbox_processed.json` | 처리 완료된 수신 메일 ID |
| `.tmp/leave_sent_processed.json` | 처리 완료된 발송 메일 ID |
| `credentials/leave_tracker_token.json` | Graph API 토큰 캐시 |
| `tools/employee_data.json` | 직원 정보 (이름, 이메일, 입사일) |
