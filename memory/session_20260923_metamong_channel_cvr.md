---
name: session_20260923_metamong_channel_cvr
description: 세션 2026-09-23 (메타몽 — Meta/TikTok 채널 CVR 실험 측정 파이프라인 E2E 구축: 일별 방문·주문·CVR 수집 → RPP 차감(순수 소셜) → meta-app 전환 탭 통합 + 매일 자동 적재). 교정: .tmp 적재 지적.
metadata:
  type: project
---

# 세션 2026-09-23 (메타몽 — 채널 CVR 실험 측정 파이프라인)

세은 요청: "링크 변동(fliptop 스왑) 전후 전환율 일별 변동, PPC 효과 제외" 테이블 + "fliptop 민 지 며칠?"

## 확정 사실
- **스왑 = 2026-09-21 17:07** (롤백맵 타임스탬프). 요청 시점 D+2 → post 주문 사실상 0(9/22·23 RMS 미집계) → "된 걸로라도" HTML 먼저, 이후 파이프라인 구축.
- **첫 신호(방문)**: 스왑 후 9/22 fliptop 방문 134→3,667 급증 + 기본컵 2,416→1,305 하락 = Meta 트래픽이 기본컵→fliptop 이동. 주문/CVR은 지연·저표본 → **판정 D+14(≈10/5) 주간 누적**.

## 구축한 것 (E2E)
- `tools/channel_cvr_daily.py` — RMS get-item-list 하루씩 루프(period=daily는 기간합산이라 단일일 반복). mngNumber로 fliptop(onetouch)/기본컵(strawcup300·_ss) 분리. `--rpp-json`(차감)·`--update-app`(seed+vercel)·`--open`.
- `tools/collect_rpp_item_daily.py` — RPP 商品別(selectionType=3) 하루씩 → `.tmp/channel_cvr_experiment/rpp_daily.json`. RPP 클릭/주문(12h) 차감분.
- **meta-app 전환 탭 통합**: seed `lib/channel-cvr-seed.json` + `lib/channel-cvr.ts` + `components/meta/ChannelCvrCard.tsx` → `/ads/products` 하단. 상단 배너 "방문 수 = RPP 효과 제외" + 최근날짜 역순 + 8행초과 스크롤(헤더 sticky). ppc_excluded=true 배포.
- **Task Scheduler `Grosmimi_ChannelCVR_Daily`** 매일 10:30 KST 2단계 체인(RPP 수집 → 차감 채널CVR → app 갱신). 강제실행 LastTaskResult=0 검증.

## 교정/학습
- **[.tmp 적재 지적]** 「이거 어디에 적재되는 거야」 → 누적 산출물은 항구적 위치 먼저 → [[feedback_durable_artifact_not_tmp]]. 세은 선택=meta-app 전환 탭.
- **[RMS 리포트 2차원 미지원]** access·RPP 商品別 둘 다 아이템×일 불가 → 하루씩 루프 → [[reference_rms_report_daily_by_item]].
- **[메모리 오류 정정]** 실험 메모의 "RPP 아이템 10000002/10000001"은 itemId라 리포트에 안 나옴 → 商品管理番号가 정답.
- 코드 하네스(Codex STRUCTURAL) 구체지적 없이 FAIL 반복 → E2E 동작검증(빌드+배포+syntax)으로 확정 → [[reference_posttooluse_code_harness_scopecreep]].

## 남은 것
- TikTok측 광고 전량 → 기본컵 URL 세팅 여부 미확인(틱톡이/세은 영역) — 안 됐으면 실험 TikTok 팔 미가동.
- RPP 주문 720h 기준 전환 옵션(현재 12h). D+14 판정.
- 리스크: RPP 수집 전량 실패 시 stale rpp_daily.json으로 차감(ppc_excluded=true 라벨 유지 = 경미 오표기), 자가복구/경보 미탑재.

정본 메모리 [[project_meta_tiktok_channel_cvr_experiment]].
