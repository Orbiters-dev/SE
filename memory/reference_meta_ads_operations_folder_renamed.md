---
name: META ADS operations 폴더 리네임 (관리용 삭제) — 구 경로 하드코딩 도구 FATAL
description: Desktop\s\performance marketing 하위 폴더가 "META ADS 관리용" → "META ADS" 로 리네임됨. operations 경로를 구 이름으로 하드코딩한 도구는 실행 즉시 FATAL/실패. 새 산출물·덱은 META ADS\operations 에 저장.
metadata:
  type: reference
---

# META ADS operations 폴더 리네임

2026-09-18 발견 — JP 위클리 덱 수집 시 `build_jp_meta_deck.py` 가 즉시 FATAL(수집 로그 0줄)으로 죽음.

**원인:** 부모 폴더가 리네임됨.
- 구: `C:\Users\orbit\Desktop\s\performance marketing\META ADS 관리용\operations`
- 신(실제): `C:\Users\orbit\Desktop\s\performance marketing\META ADS\operations`

`_OPS_DIR.is_dir()` 가드가 폴더 부재 → `sys.exit("[FATAL] operations 폴더 없음")`. `DEFAULT_DECK = _weekly_deck_path()` 가 **모듈 로드 시점**에 평가돼서 수집 함수 진입 전에 즉사(그래서 로그 0줄 = 도구 실패 신호). ⛔ 폴더 재생성(mkdir) 금지 룰과 무관 — 폴더는 `META ADS\operations` 에 정상 존재, 경로만 stale.

**조치:** `build_jp_meta_deck.py:73` `_OPS_DIR` 경로를 `META ADS` 로 수정(이번 세션 완료). ls 로 실제 폴더 실증 후 수정 — 폴더 재생성 아님.

**⚠️ 아직 구 경로 하드코딩 남은 도구 (실행 시 동일 FATAL/실패):**
- `tools/build_meta_ads_full_standards_pdf.py`
- `tools/build_meta_ads_showoff_pptx.py`
- `tools/build_meta_ads_standards_v2_pptx.py`
- `tools/build_meta_jp_standards_pdf.py`

이들 실행 전 `META ADS 관리용` → `META ADS` 로 경로 수정 필요. 신규 도구는 처음부터 `META ADS\operations`.

**PostToolUse 코드 하네스:** `build_jp_meta_deck.py` 는 만성 FAIL(전체파일 일반론) — 1줄 경로 수정도 무관한 전면 지적으로 FAIL. 실동작(수집·렌더) 검증 후 FAIL 명기하고 진행. [[reference-posttooluse-code-harness-scopecreep]] · 스킬 자체에도 명기.
