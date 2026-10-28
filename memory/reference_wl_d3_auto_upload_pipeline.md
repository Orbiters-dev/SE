---
name: WL D+3 자동 업로드 파이프라인 (2026-09-08 신설 — 매일 9시 무인)
description: 감시견이 감지한 D+3 미부착 파트너 콘텐츠 중 제품 확정분만 Meta WL 광고 PAUSED 자동생성. tools/wl_auto_upload.py + Task Scheduler JPDash_WL_AutoUpload(09:00 JST).
metadata:
  type: reference
---

# WL D+3 자동 업로드 (2026-09-08 세은 상시 위임 — "3일 지난 컨텐츠 알아서 업로드")

`tools/wl_auto_upload.py` — 매일 **JST 09:00** Task Scheduler **`JPDash_WL_AutoUpload`** 실행
(래퍼 `.tmp/ceo_ads_report/run_wl_auto_upload.ps1`·로그 `.tmp/ceo_ads_report/logs/wl_auto_upload_*.log`).
대시보드 체인(JPDash_Daily 10:00)과 **디커플** — 09:20 RPP 선행 때문에 그 체인은 9시로 못 옮김.

## 흐름
1. 원장(DK coauthor ∪ 폼 투고완료) vs Graph 광고 커버 대조 → D+3 미부착 추출 (감시견 `covered_sets`/`ledger_*`/`uncovered_d3` 재사용).
2. 각 건: **resolve**(SYS 영구토큰) → **제품확정**(폼 통합탭 희망제품 → ASIN/LP 매핑) → **크리에이티브**(LIVE) → **adset+광고 PAUSED**(₩8,000·LPV·Testing 캠페인 120248267687980223).
3. **업로드 안 하고 보류**: 제품미상(폼 매칭실패/모호)·저작권음악(subcode 2875030)·WL권한없음(advertisable 미반환)·API 일시장애(transient). 추측 업로드 절대 X.
4. 알림: **업로드 or 하드실패만** 세은 Teams+Gmail(정적 보류는 감시견이 매일 커버 → 중복 회피). 하드실패 시 exit 1.
   - 채널: **Teams 웹훅(TEAMS_WEBHOOK_URL_SEEUN) + Gmail(se.heo@orbiters.co.kr)**. Gmail 제목 = `[WL자동업로드] {날짜} — 업로드 N·실패 M` (감시견 notify에 subject 파라미터 추가·하위호환).

## ⛔ ON 정책 (2026-09-08 세은 지시)
**당분간 광고 ON 절대 X — 세은이 직접 수동 ON.** auto_upload는 `status=PAUSED`까지만 생성.
안정화 후 세은이 **명시적으로 "ON까지 하라"** 지시하면 그때 ON 자동화 검토. 그 전엔 PAUSED 고정.

## 제품 매핑 (product_color_size_options 기준)
- PPSU 스트로마그 300 = **B08TZY1TFY** / 200 = **B0B9GLVWYN**, LP grosmimi_ppsu_strawcup300 (사이즈 모호=보류)
- ステンレス(스마트마그) 200·300 = **B0G6CCJ24K**(동일 ASIN·사이즈 variant), LP stainless_steel_strawcup_300
- PPSU ワンタッチ = **B0DJNXD66N**, LP grosmimi_ppsu_onetouch_srawcup ("srawcup"=오타 아님·실제 슬러그)
- 계약형태: 폼 제출=WL-G 기본, 유상표기(¥/円/paid)만 WL-P.

## ⚠️ 알려진 한계 — 폼 희망제품 ≠ DM 변경 최종제품
폼 통합탭의 희망제품을 소스로 씀. 재고이슈 등으로 **DM에서 제품 변경**되면 폼은 stale → 오라벨 위험.
실측: piyomaru 폼=PPSU 200(B0B9GLVWYN)인데 실제 발송=PPSU 300 スカイブルー(B08TZY1TFY, 8/19 재고切れ DM 변경).
(piyomaru는 저작권 음악으로 어차피 광고 불가라 실해 없음.) → **업로드 알림에 제품 표기되니 세은이 대조 가능**. DM 변경분은 인플루언서 매니저가 폼/메모리 갱신해야 정확. [[feedback_track_product_decisions]]

## 토큰
resolve/business_discovery/advideos = **SYS**(META_JP_SYSUSER_TOKEN 만료없음) / 크리에이티브·광고·adset = **LIVE**. Graph v23.0.
[[reference_meta_jp_sysuser_permanent_token]] · [[reference_meta_wl_branded_ad_api_creation]] · [[reference_meta_wl_testing_gate_criteria]]

## 하네스 노트
빌드 시 Codex/Gemini 하네스가 임계 바로 아래(7~8/10)에서 비결정적 진동(일부 오판정: v21만료·srawcup오타 주장). 실동작=3건 라이브 업로드+dry-run 정상으로 기능 입증됨.
