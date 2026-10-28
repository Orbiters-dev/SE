---
name: mistakes_20260921_us_data_in_jp_app_and_ads_shop_confusion
description: 오답노트 9/21 — JP 앱(메타몽)에 US(onzenna) TikTok 데이터를 붙임 + TikTok Ads와 Shop 혼동(크로스보더를 ads에 오적용). 세은 "미국 말고 JP" · "ads랑 shop 다르지 않아" · "크로스보더 왜 하나"
metadata:
  type: feedback
---

세은이 "JP TikTok ads(IHV) 성과를 메타몽 app에 반영하자"고 했는데, 두 갈래로 헛발질.

**오류 1 — US 데이터를 JP 앱에 반영.**
메타몽 app 은 **Grosmimi JP** 앱인데, 손에 잡히는 US `tt_spark_live.json`(us_board · onzenna.official · 브랜드 Onzenna)을 그대로 /tiktok 탭에 붙임. 세은 "미국 거 말고 jp 걸로 채워야지 장난하냐" · "여기다가 미국 데이터는 넣을 필요가 없을 거 같은데". → US 연결 제거, JP 데이터 준비 전까지 `ttReady()=false` "준비 중" 상태로 교체.

**오류 2 — TikTok Ads 와 Shop 혼동.**
초반에 틱톡샵 스킬로 진입해 Shop·크로스보더 맥락을 깔아놓고, 그걸 TikTok **Ads**(광고) 작업에 계속 오염. 광고계정을 "JP 크로스보더 광고계정"이라 명명. 세은 "tiktok ads랑 tiktokshop이 다르지 않아??" · "크로스보더 얘기를 왜 하나". → 크로스보더 = TikTok **Shop**(판매) 전용 개념(관세·소비세·물류). TikTok **Ads**(광고)는 크로스보더와 무관, 그냥 JP 광고계정.

**Why:** 레퍼런스(US 보드)의 형식과 데이터를 구분 못 했고, 스킬 진입 맥락(Shop)을 실제 작업 축(Ads)과 분리 못 함.

**How to apply:**
- 새 대시보드/파이프라인 구축 시 레퍼런스는 **형식(레이아웃·지표 체계)만 차용**, 데이터는 **대상 리전(JP)** 것만. 다른 리전 데이터를 "임시로" 붙이지 마 — 혼란만 준다.
- **TikTok Ads ≠ TikTok Shop.** 작업 착수 시 어느 축인지 먼저 확정. 크로스보더·GMV·어필리에이트·입점 = Shop. 지출·유료뷰·CTR·CPC·전환 = Ads. tt_spark_live = Ads(오가닉 증폭) 트래커지 Shop 아님.
- 관련: [[reference_metamong_app_5tab_ih_dashboard]] · [[reference_tiktok_korea_jp_crossborder]](Shop 전용) · [[session_20260921]]
