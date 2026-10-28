---
name: reference_kse_oms_quirks
description: KSE OMS Playwright 자동화 시 알아야 할 동작 특이점. 옵션코드 commit, 배송접수 신호, 중복 등록 차단.
type: reference
---

# KSE OMS 자동화 특이점

## 옵션코드 셀 — Tab만으로 commit 안 됨

AG Grid 셀 더블클릭 → input 입력 → Tab 으로 끝내면 cellValueChanged 이벤트가 다음 셀로 포커스 이동할 때만 발생함. **마지막 행/마지막 셀은 다음 포커스 대상이 없어 서버 저장 누락 가능.**

해결: 입력 후 다른 행/셀을 명시적으로 click() → ESC. AG Grid가 commit을 강제로 발화시킴.

검증: `gridOptions.api.forEachNode(node => node.data.optionCode)` 으로 raw 값 재조회. DOM 값과 다를 수 있음.

## 배송접수(국제) 성공 시그널 (3중)

confirm "배송 접수를 진행하시겠습니까?" → accept만으로는 성공 아님. **실제 성공 시그널 3가지 모두 확인:**

1. 두 번째 alert: `"Success! 배송관리 페이지로 이동합니다"` — accept 후 약 8~12초 뒤 비동기로 발생. wait 15초 권장.
2. URL: `https://kseoms.com/integration_api/getOrders` → `https://kseoms.com/shipping2` 로 변경.
3. 주문수집 페이지 AG Grid 행: 라쿠텐 0건 (모두 팩킹리스트로 이동).

→ 셋 다 통과해야 진짜 성공. confirm OK만 보고 성공 판정 금지.

## 처리 완료 주문 재수집 차단

이미 KSE에 등록된 주문을 다시 "주문서 가져오기" 호출 시 API 응답:

```json
{"code":"-1","msg":"등록에 실패하였습니다",
 "data":{"success":{"order_ids":[]},
         "fail_ord_no":{"dup":["435776-..."]},
         "order_data":[]}}
```

`fail_ord_no.dup` 배열에 packNo 들어있으면 중복으로 차단된 것 (정상 방지 동작). expected_count > 0 인데 success 0이면 NO_DATA exit 2 처리.

## 공지 팝업

KSE 메인페이지 진입 시 공지 모달이 뜰 수 있음. "모두닫기" 버튼만 클릭 (일반 "닫기" fallback은 다른 폼/탭 닫기 버튼을 잘못 누를 수 있어 위험).

## 환경

- 로그인 URL: `https://kseoms.com/login`
- 주문수집 URL: `https://kseoms.com/integration_api/getOrders`
- 팩킹리스트 URL: `https://kseoms.com/shipping2/packingList` (정확한 경로는 메뉴 클릭으로 진입)
- `KSEOMS_LOGIN_ID` / `KSEOMS_LOGIN_PASSWORD` (.env)
