---
name: session-20260918-metamong-ih
description: "세션 2026-09-18 (메타몽 — WL 3건 ON + IH 캠페인 첫 자동 생성 레시피 확립·Drive 영상 소스/네이밍 룰 + 9/21 심사확인 WL 2건 WITH_ISSUES 발견)"
metadata:
  type: project
---

# 세션 2026-09-18 (메타몽 — IH 광고 생성 + WL ON)

## 한 일
1. **IH vs WL 구분 정립** — @grosmimi_japan 자사 게시물=IH 캠페인(`Rakuten_IH_PPSU&Stainless_Testing` 120250841109750223), 크리에이터 게시물=WL. IH는 파트너십 resolve 불요.
2. **WL 3건 ON** (세은 "켜") — D16/D17/D18. `.tmp/wl_turn_on_0918.py` (ad+adset 동반 ACTIVE).
3. **IH 첫 자동 생성** — DdTREOfSPmw → `260915_PPSU_韓国製ストローマグ` (ad 120250958068310223). 기존 IH 크리에이티브 해부로 레시피 확립 → [[reference_ih_video_source_drive_naming]]. `.tmp/ih_create_0918.py`.
4. **IH 영상 소스·네이밍 룰 확립** — 영상=고정 Drive 폴더(1E5vKZ...), ad set=ad 이름=`{YYMMDD}_{제품}_{테마}`(영상 제목 매칭), 게시일 기준.

## 세은 지시/피드백
- "grosmimi japan 계정 애들은 IH 캠페인에 올려" — 자사 게시물 IH 라우팅 정립.
- "영상은 항상 [Drive 폴더]에 저장 → 매칭 영상 제목으로 ad set·ad 제목, 지금 만드는 형식 그대로. 앞으로 제목에 제품도 붙여줌."
- "지금은 올리기 전에 나한테 제품 뭔지 물어봐" — 현재 배치는 영상 제목에 제품 없어 세은 확인 후 업로드.
- 제품 확정: DdTREOfSPmw = PPSU 기본컵(strawcup300), 날짜=게시일 기준.

## 미완 / 후속 (9/21 심사확인)
- **WL D17 EMAA** = `3867026` 크리에이터 emaa_331 파트너십 권한 미부여 → 외부 승인 대기(게시 시 DM 발송됨). 리공이 루트.
- **WL D16 GAAAAAKU** = `3867111` 크리에이티브 dual identity 누락 → 재생성 필요(세은 결정 대기).
- WL D18·IH 260915 = ACTIVE 정상 게재.
- **학습**: WL ON 전 issues_info 선점검 의무 → [[reference_wl_ad_turnon_precheck_issues]].
- 나머지 Drive 영상 4개(話題のマグ·デザイン１·オススメマグ·グロミミ概要) = 제품 확인 후 IH 생성 대기.

관련: [[reference_ih_video_source_drive_naming]] · [[reference_wl_ad_turnon_precheck_issues]] · [[reference_metamong_app_5tab_ih_dashboard]]
