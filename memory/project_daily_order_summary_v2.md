---
name: 매일 13:30 주문 보고 v2 (라쿠텐 분리)
description: 2026-05-07 부터 라쿠텐은 KSE 분리하고 RMS 발송대기 페이지에서 직접 조회. 아마존만 KSE 팩킹리스트. Task Scheduler `KSE_Order_Summary_Daily` 매일 13:30 KST.
type: project
---

## 매일 13:30 주문 보고 v2

**Why:** 라쿠텐은 더 이상 KSE에 올리지 않기로 함 (2026-05-07 세은 결정). 따라서 KSE = 아마존만, 라쿠텐은 RMS 발송대기 페이지에서 직접.
**How to apply:** 매일 13:30 자동 발송. 코드 수정 시 `tools/kse_order_summary.py` 와 `tools/rakuten_pending_orders.py` 둘 다 검토.

### 데이터 흐름

| 채널 | 소스 | 도구 |
|---|---|---|
| 아마존 | KSE 팩킹리스트 `/shipping2` (Playwright) | `tools/kse_order_summary.py` `fetch_packing_data()` |
| 라쿠텐 | RMS 발송대기 `ORDER_PROGRESS=300` (Playwright) | `tools/rakuten_pending_orders.py` `fetch_pending_orders()` |
| 발송 | Teams Incoming Webhook (`TEAMS_WEBHOOK_URL_SEEUN`) | `kse_order_summary.send_to_teams()` `{"text":"..."}` |

### 라쿠텐 옵션 키 매핑

라쿠텐 상품마다 사이즈 옵션 키가 다름:
- ステンレス → `サイズ:NNNml`
- PPSU 마그 → `容量:NNNml`
- 카라 → `カラー:xxx` (공통)

`rakuten_pending_orders._normalize_title()` 정규식: `(?:サイズ|容量)\s*[:：]\s*(\d+)\s*ml`. 옵션 div 화이트리스트: `^(カラー|色|サイズ|容量|バリエーション)[:：]`.

### Task Scheduler

- 활성: `KSE_Order_Summary_Daily` (Ready) → `C:\Users\orbit\Desktop\SE\tools\kse_order_summary.py`
- Disabled: `KSE Daily Order Summary`, `KSEOrderSummary` (둘 다 Z 옛 경로 — 파일 없음)

### 라쿠텐 RMS API 401 메모

로컬 PC IP는 RMS API 화이트리스트 미등록 → API 직접 호출 시 401. 매일 13:30 작업은 **API 안 쓰고 Playwright 로그인** 으로 우회. (Data Keeper의 라쿠텐 수집은 다른 환경에서 도는 것으로 확인)
