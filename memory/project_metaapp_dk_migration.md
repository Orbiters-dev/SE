---
name: project-metaapp-dk-migration
description: 메타몽 app을 Graph 직접호출→DK 단일소스로 전환한 상태 + 원기님 대기 작업 + 임시 Graph union 제거 조건 (2026-07-02)
metadata:
  type: project
---

2026-07-02 세은 지시: 메타몽 app(meta-app, vercel)의 모든 광고 데이터를 **DK 단일소스**로. 내가 직접 긁는(Graph/Apify/Syncly) 경로 X. 흐름: 수집기→DK→app read only.

**완료(배포됨, vercel meta-app-one.vercel.app):**
- app 광고 데이터 import를 meta-api(Graph)→[dk-meta.ts](../meta-app/lib/dk-meta.ts)(DK read)로 전환. meta-aggregations·wl-attribution·product-metrics·ads/[adId]·daily-issues(permalink만). daily-issues "오늘 등록" 감지는 created_time 필요→Graph 유지(불가피).
- 콘텐츠 탭 통합 리스트: Organic등급/WL등급 2컬럼, 정렬=organic 기준, organic view=전체−paid(LPV), 전체 view, D+3 view(별도, 실측만), LPV/CPLPV/CTR(WL), Hook Type(시트 44번째 열), 가로 표내부 스크롤.
- 콘텐츠 상세(/influencers/[handle]): ContentCharts 일별(증가분)/누적 2섹션 — organic view(전체−누적LPV) + WL이면 paid spend/LPV/CPLPV/CTR.
- 수집기(SE main c0f51762): collect_meta_ads_jp에 LPV+effective_status+creative 추출 / push_metrics 무결성가드+재시도 / IG views fallback.
- content_metrics 과거 빵꾸 복구 스크립트(.tmp/repair_content_metrics.py) — 단 DK write 401로 미실행.

**⏳ 원기님 대기 (write/EC2 권한 = 내 손 밖, [[reference-datakeeper-access-policy]]):**
1. gk_meta_ads_daily 컬럼 4개 추가(landing_page_view/effective_status/creative_permalink/creative_media_id) — deploy_ec2.yml app=datakeeper (create_missing_tables.py에 ALTER 있음). 4/13 실행 11초 실패이력=EC2_SSH_KEY 확인 필요.
2. 전체 백필: `python tools/data_keeper.py --channel meta_jp --days 220` (계정 2025-12-11부터, DK엔 3/1부터+누락. lifetime ₩23.5M vs DK ₩7M).
순서: ①컬럼 → ②백필.

**임시 Graph union (원기 완료 후 제거):** dk-meta.fetchInsights/fetchAdDaily가 DK+Graph union(mergeWithGraph)으로 전 이력·LPV 보완 중. DK 백필+컬럼 되면 Graph 중복이라 무해 → 그때 union/fallback 코드 제거하고 순수 DK 검증.
