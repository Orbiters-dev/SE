---
name: jp-weekly-deck
description: JP Meta 주간 발표 덱 (Weekly Performance Read) 생성 — build_jp_meta_deck.py 1커맨드 + 확정 형식 룰. Trigger: 주간 덱, JP 주간 덱, 주간 발표 덱, weekly deck, performance read, 주간 리뷰 덱
---

# JP Meta — Weekly Performance Read 덱 (주간)

매주 발표용 JP Meta 덱을 만드는 스킬. **2026-07-20 세은 확정 형식** — 임의 변경 금지, 형식 바꾸려면 세은 지시로만.

## 실행 (1커맨드)

```bash
PYTHONIOENCODING=utf-8 python tools/build_jp_meta_deck.py            # 수집 + 렌더 (기본)
PYTHONIOENCODING=utf-8 python tools/build_jp_meta_deck.py --render   # ssot.json 재사용 렌더만
```

- 산출: `operations\NN_jp_meta_weekly_deck_YYYYMMDD.html` — **주차별 새 번호 자동 채번** (폴더 최대 NN+1, 날짜=그 주 월요일). 같은 주 재실행 = 같은 파일 덮어쓰기. ⛔ 고정 파일명으로 저번 주 덱 덮어쓰기 금지 (7/27 세은 — 11번 덱 소실 사고)
- ⛔ 구 `Desktop\s\메타` 폴더 **재생성 절대 금지** (7/20 세은 — 도구 mkdir 사고 주의)
- ⛔ HTML 직접 수정 금지 — 반드시 빌더 수정 → 재렌더 (7/14 룰)
- **발표 아침에 재실행** (성과·status 갱신). 렌더 후 Playwright 스크린샷 실측 의무 (배포≠완료, 7/7 룰)

## 덱 구성 (12장, 확정 — 7/27 상관 해부 슬라이드 추가)

1. 표지 — "JP Meta — Weekly Performance Read" (방법론: LPV 천장·3S율 정의·게이트)
2. 이번 주 한눈 — 최근 1달 런칭 풀 4색 분포 카드 + 7d 총괄 + 3S율×판정 인사이트
3. 최근 1달 런칭 전수 디스포지션 표 (판정색→CPLPV순, 행마다 판정+사유)
4. 이번 주 신규 런칭 — **광고(콘텐츠) 단위** 감지 (크리에이터 단위로 하면 기존 크리에이터의 신규 릴 누락)
5-6. **BEST 4 / WORST 4** — 7d CPLPV 기준 (풀 = 7d spend ₩3,000↑), 카드 = 잘/안 된 이유 **데이터만**
7. 왜의 근거 — 시청 잔존 오버레이(BEST 파랑 vs WORST 빨강, 범례 필수) + **우측 = 같은 8개 콘텐츠의 클릭 실측 표**(클릭 수·CTR·CPC·클릭→LP·CPLPV·75% 잔존 — 7/27 세은 「클릭 해설이면 옆엔 KM/훅이 아니라 클릭 수」, KM/훅 표 제거). 해설 박스는 **데이터 분기**(7/27): BEST가 CTR 우위(×1.15↑)인데 75% 잔존 열위면 = 클릭 이탈(링크 탭=재생 중단) 해설, 아니면 기존 훅/전개 해설
7b. 무엇이 성과를 가르나 — **반으로 갈라 비교** (7/27b 「너만 알아듣는 말」 강한 교정 후 재작성): 생애 풀(₩20K↑)을 클릭율/3초 시청률/클릭→랜딩/오가닉 조회수 기준 상·하위 절반으로 나눠 **CPLPV 실측 비교**. ⛔ r·상관·사다리 등 통계 용어 금지 — 쉬운 말+실제 원화 수치만. 카드·판정 문구 전부 렌더 시 재계산
8. 성과가 변하는 방식 — Proven 승격군(전 이력, 편입 전2주·후N주 **동적**: 군 40%↑ 관측 최대 주차, 최소 8주 — 매주 자연 확장, 7/27 세은) vs Testing 잔류군(CT 단위 전수) + 핵심 3카드 + 분포 밴드
9. 성과 변동 선별 — |Δ CPLPV|≥15% + 앞장 경향 일치만
10. 졸업→증액 효율 유지 / 11. 운영 성과 — **최근 7일 vs 직전 7일 · 최근 30일 vs 직전 30일 두 갈래 비교 표**(광고비/LPV/CPLPV/CTR/CPC/3S율 + Δ색: 좋아진 방향 파랑·나빠진 방향 빨강, **|Δ|<5% = 색·수치 없이 「유지」** — 7/27 세은) + 「효과적으로 돌고 있나」 정리 3불릿. ⛔ 캠페인/Ad Set 개별 나열 금지 (7/27 세은 「asset 별로 하나하나 넣을 필요 없다」). 직전 30일 = ssot totals_prev30 (수집 필요 — --render만으론 구 ssot에 없음)

## 확정 형식 룰 (세은 7/20)

- **판정 4색**: 파랑=좋음 / **초록=중간**(통상 신호등과 다름!) / 빨강=안 좋음(D+5 유예) / 검정=즉시 OFF. 기존 게이트 로직 재사용 — 새 임계값 발명 X
- **creator type**: WL-P 유상 / WL-G 무상 (ad_name 토큰)
- **3S율** 표기 (3초율 X): `actions[video_view]` = 3초 재생 (전용 필드 `video_3_sec_watched_actions`는 400 죽음). KM·3S율 = 볼륨 칩 2개 (KM 네이비 / 3S율 파랑)
- **KM 라벨**: 코드만 표기 금지 — 항상 내용 라벨 병기 (코드만 저장된 행은 택소노미 폴백)
- ⛔ **수동 태깅 훅(HV/HC) 표시 전면 제거** (8/24 세은 「이 스킬에서 훅 넣는 건 다 빼」) — 훅 칩·훅별 Top 표·HV/HC 라벨 없음. 3S율(자동 지표)·3S율 기반 해설(「첫 3초에서 갈린다」류)은 **유지** (훅 태깅과 무관). tag_jp_content.py의 훅 자동태깅은 앱용으로 남지만 덱엔 미표시.
- **이유**: "지표 높음/부족 (수치, 풀 대비 ±pt) → ~가능성" 형식. BEST=잘 된 축만, WORST=부족한 축만 (상대편차 상위 2). 강조 박스 14px
- 3S율 판정 기준(계정 실측): <40% 약 / 40~50% 중간 / ≥50% 강. 3S 정상 + p50 풀(≈18%) 미달 = 전개(Promise) 문제
- ⛔ OFF 내부 임계값 수치 노출 금지 (졸업 기준 수치는 OK)
- 덱 = PPT 테마 (네이비→블루 그라데이션 h2 밴드·다크 표지·풋터 스트립)

## 태그 (KM) — 메타몽 앱 등록값이 진실

조인 우선순위 (빌더 내장): ① 광고 permalink sc → ② **광고명 CT ↔ 시트 ct_pk** → ③ CT ↔ DK content_posts→원본 sc → ④ 콜라보 시트 원본 릴 sc → ⑤ 크리에이터 union.
- 세은이 메타몽 앱에서 태깅 → 같은 시트 `Content Tags (JP)`(km_manual) → **재수집 1커맨드로 반영**
- 미태깅 발견 시: 시트 원본이 아니라 **앱 콘텐츠 키(CT/원본 shortcode)** 기준으로 원인 조사 (7/20 강한 교정)
- **KM 값 = km_manual(수동, 앱) 우선 → 없으면 km_primary(자동)** (build_jp_meta_deck.py:227). 자동 KM 생성 = `tools/tag_jp_content.py` (DK content_posts 캡션 → Claude LLM constrained-label 분류 → 시트). 정답 코드 목록 = Inhouse Content Tracker 시트 `KM SSOT_GR` 탭(gid 44578416). 자동값 틀리면 앱에서 km_manual 교정(즉시 덱 반영) → 그 교정은 다음 자동태깅 few-shot 학습됨(build_corrections_block).
- `review_note` 컬럼 = Promise/Proof/CTA human 리뷰 기록용 (현재 카드 비표시 — 세은 지시 시 병기)

## 함정 (전부 실측으로 밟은 것)

- 광고 on/off = **Graph 실시간만** (live_ad_statuses + 계정 전체 /ads 목록·CT 단위 — 방금 승격된 새 Proven ad는 insights에 없음)
- 6/19 명명 변경 이전 daily는 stage 왜곡 (Graph가 현 캠페인 소속명 반환 — 구 광고가 전부 proven으로 잡힘). 경향성 정렬은 "현 Proven 캠페인 첫 지출일" 기준
- 레이트리밋 403·시트 503 → 빌더에 재시도+fallback 내장돼 있음. 실패 로그 확인
- CTR = clicks(all) 기준 (링크 클릭만 아님). 진짜 LP 도달 = CTR × 클릭→LP
- Codex 하네스는 이 빌더 만성 FAIL(전체파일 일반론) — 저위험 변경만 반영, FAIL 명기 후 진행 (7/14 확립)

## 발표 전 체크리스트

1. 아침 재실행 → KM 미태깅 0 확인 (`미태깅` 문자열 grep — 훅 미태깅은 8/24부터 표시 안 함)
2. 신규 런칭 수 = ad 단위 실측과 일치 확인
3. Playwright 캡처로 표지·한눈·BEST/WORST·경향성 슬라이드 실측
4. 세은이 새로 승격/OFF 했다고 하면 → 재수집이 실시간 반영하는지 검증 후 보고
