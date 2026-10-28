---
name: Proven 졸업 ad 7d 판정 데이터 lookup은 Testing ad ID로
description: Testing→Proven 졸업 시 Proven adset에 새 ad가 복제 생성됨. 그 새 ad ID로 7d insights fetch하면 NO DATA. 졸업 판정 7d 누적은 같은 name pattern의 Testing ad ID로 lookup.
type: reference
---

# Proven 졸업 ad 7d 판정 데이터 lookup

## 룰

Meta JP에서 Testing → Proven 졸업 시 Proven adset 안에 **새 ad가 복제 생성**된다 (기존 Testing ad가 adset만 옮겨지는 게 아님).

→ 졸업 직후 새 ad ID로 `/{ad_id}/insights?time_range=직전 7d` 호출하면 **NO DATA**. 그 ad는 어제까지 존재하지 않았기 때문.

→ 졸업 판정의 7d 누적 (spend/clicks/LPV) 은 **직전 Testing 풀의 같은 ad name pattern** ad ID로 lookup해야 함.

## Why

5/21 노션 daily report 「부가 작업」에 졸업 3건 (kina/monyuru/komugiko) spend/click/LPV 추가 시, 오늘 ON된 Proven ad ID로 5/14~5/20 insights 호출 → 전부 NO DATA. created_time이 2026-05-21이라 7d 윈도우에 존재 X. 같은 이름의 Testing ad를 찾아 재호출 → 정상 데이터.

## How to apply

1. Proven ad의 name pattern 추출: `AD {코드} | {SKU} | {인플루언서} | {PAID/GIFT} | {게시일 yyyymmdd}` + adset SKU.
2. `/act_{id}/ads?fields=id,name,status,adset{name}` 전체 fetch.
3. `adset.name`에 「Testing」 포함 + ad name에 동일 인플루언서·SKU·게시일 매칭되는 ad ID 추출. (1 인플루언서가 같은 SKU Testing 풀에 여러 ad — 모두 합산).
4. 그 Testing ad ID로 7d insights fetch.

## 추적 ID 예 (5/21 kina/monyuru/komugiko)

| Proven (5/21 신규) | 매칭 Testing ad ID | 7d (5/14~5/20) |
|---|---|---|
| AD M kina Stainless GIFT | 120243048123520223 | ₩32,422 / 294 / 240 |
| AD E monyuru PPSU PAID | 120243047220520223 + 120243046908570223 | ₩151,789 / 1,417 / 1,218 |
| AD N komugiko Stainless PAID | 120243850558330223 | ₩146,497 / 1,458 / 960 |

## 관련

- [reference_meta_jp_testing_proven_system.md](reference_meta_jp_testing_proven_system.md) — Testing/Proven 2-stage 시스템 기본
- [reference_meta_graduation_criteria.md](reference_meta_graduation_criteria.md) — triple share 졸업 게이트 (7d spend/clicks/LPV share ≥50%)
