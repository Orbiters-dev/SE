---
name: 메타몽 장기관찰 1 — 오가닉 vs WL 광고 효율 상관
description: 인스타 오가닉 효율과 메타 WL 광고 효율 간 상관도. 크리에이터 변수(팔로워/특징) × 컨텐츠 변수(메시지/촬영) 두 축으로 누적 관찰. 매월 말 스냅샷.
type: project
---

# 메타몽 장기관찰 1 — 오가닉 ↔ WL 광고 효율 상관

세은 지시일: 2026-06-01. 메타몽 능동 관찰 누적.

**Why:** 광고용 인플루언서 / 영상 picking 룰을 데이터로 굳히기 위함. "오가닉 잘 나오면 광고도 잘 나옴" 가설이 segment별로 깨지는지 확인.

**How to apply:** 매월 말 스냅샷 1회. 시사점 누적되면 picking 룰 (팔로워 tier × 영상 톤 매트릭스) 후보로 발전. 메타몽 컨설팅 시 인플루언서 추천 근거로 인용.

## 측정 지표
| 축 | 오가닉 | WL 광고 |
|----|--------|--------|
| 핵심 | views_30d / engagement_rate / virality_coeff | CTR / CPLPV / Freq |
| 보조 | likes_30d / comments_30d | impressions / spend / clicks |

## 분할 변수
- **크리에이터**: 팔로워 tier (<1만 / 1~5만 / 5만+) / 카테고리 (육아 vlog / 제품 후기 / 일상)
- **컨텐츠**: 영상 톤 (vlog / 데모·언박싱 / before-after) / hook 유형 / 메시지 (감성 vs 기능)

## 데이터 소스
- meta_ads_daily (brand=Grosmimi JP) — ad_name 핸들 추출
- content_posts — username·followers·engagement_rate·virality_coeff
- content_metrics_daily — 시계열 보조

## Path A (즉시 가능)
ad_name 핸들 ↔ content_posts.username 매칭. 인플루언서 단위 평균 비교. 한계: 영상-광고 1:1 매칭 X.

## Path B (도구 1개 추가 시)
Meta Graph API로 ad → creative.effective_object_story_id → IG post_id fetch. content_posts.post_id 1:1 매칭. 정확도 ↑.

## 초기 가설 (2026-06-01)
1. 전체 상관 낮을 것. 단 segment별로 다를 가능성.
2. 팔로워 5만+ × 후기형 → 둘 다 높음 (신뢰 효과).
3. <1만 micro × vlog → 오가닉 높음 / 광고 약함 (hook 약함).
4. 데모·언박싱 → 광고 높음 / 오가닉 평범.

## Cadence
- **매월 말** 1회 스냅샷.
- artifact: `.tmp/metamong_observations/YYYYMM_axis1_organic_vs_wl.json`

## 누적 로그
(스냅샷 발생 시 아래에 한 줄씩 append)

- _첫 스냅샷 대기 (2026-06 말 예정)_
