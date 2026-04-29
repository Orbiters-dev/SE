---
name: 발견한 버그는 묻지 말고 즉시 수정
description: 진행 중 발견한 코드 버그는 "수정할까요?" 묻지 말고 바로 고치고 검증 후 보고
type: feedback
---

작업 중 발견한 명백한 버그·오탐·매핑 오류는 **세은 승인 받지 말고 즉시 수정 → dry-run 재검증 → 결과 보고**. 수정 여부를 묻는 건 시간 낭비이자 에이전트의 기본 책무 회피.

**Why:** 2026-04-23 옵션코드 매핑 버그(Amazon 리스팅 타이틀에 200ml/300ml 둘 다 있어 오탐) 발견 후 "수정할까요?" 물음 → 세은 "당연히 해야지 장난하나". 버그가 보이면 고치는 게 당연, 확인 절차는 불필요.

**How to apply:** 
- 코드 버그·로직 오류·오탐 발견 즉시 수정 → dry-run/테스트 → 결과 표로 보고
- 수정 범위가 외부 시스템(n8n 배포, DB 마이그레이션, 푸시)이면 그때만 승인 요청
- 같은 로직이 복사된 다른 파일(예: fill_kseoms_option_code.py ↔ kse_amazon_order.py)도 함께 수정
- 이미 있는 메모리: feedback_dont_ask_when_info_given.md, feedback_obvious_features.md와 같은 맥락
