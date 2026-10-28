---
name: Rakuten 매출 수치는 정가 기준
description: Rakuten 매출 fetch·보고 시 정가가 디폴트. 할인가/캠페인가 잘못 끌어오면 비교 윈도우 망가짐. RMS UI 「総売上」도 정가 기준.
type: feedback
---

Rakuten 매출 수치 fetch·보고는 **정가(list price) 기준**이 디폴트.

**Why:** 2026-05-18 Meta×Rakuten ROAS 분석에서 평균 일매출 2만엔으로 보고 → "rsl 전에 평균 일매출이 2만엔이나 된다고?? 확실함?" 의심 → 차이 확인 결과 할인가 기준이었음. → "정가로 해야지 당연히" 교정. 정가/할인가 혼동이면 Meta 광고비 대비 ROAS 계산이 통째로 어긋남.

**How to apply:**
- `search_order` / 매출 fetch 시 단가 필드 = **정가 컬럼** 우선 사용.
- 할인가·캠페인가는 별도 분석용으로만 (구분해서 보고).
- RMS UI 「総売上」 (정가 기준) 과 코드 fetch 결과가 일치해야 sanity check 통과.
- ROAS / 매출 평균 / 일매출 비교 — 모두 정가.
- 의심스러운 수치 ("RSL 전에 일매출 2만엔?") 가 보이면 자체 sanity check 한 번 더 (단가 필드 어디서 끌어왔는지 확인) 후 보고.
