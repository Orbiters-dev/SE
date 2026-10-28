# 02. 프론트엔드 라우트별 상세 (페이지 · API)

> 원본 소스: `meta-app/app/**`. 화면 구성·컬럼·조건식은 소스에서 그대로 옮겼다.
> 전역 스택·인증·데이터 소스 개요는 `01_ARCHITECTURE.md` 참조 (본 문서는 라우트 단위 상세).

## 0. 전역 사실 (라우트 공통 — 소스 검증값)

- **스택**: Next.js **16.2.7** App Router + React 19 (RSC 위주) / Tailwind v4 / shadcn(base-ui) / **Recharts**
- **언어**: `<html lang="ko">`, 폰트 Geist Sans/Mono
- **테마**: OKLCH 파스텔 브라운(원숭이 컨셉) — `--primary` oklch(0.55 0.08 52),
  긍정 `--good`(파스텔 민트)/부정 `--bad`(파스텔 핑크), 라이트/다크 모두 정의 (globals.css)
- **인증 게이트**: `proxy.ts` (Next16 의 middleware 대체) — `/login`·`/api/login`·정적 파일 제외
  전 라우트에서 세션 쿠키 검증, 실패 시 `/login?next=<path>` 리다이렉트
- **세션 쿠키**: 이름 `meta_app_session`, 값 `v1.<만료ms>.<HMAC-SHA256>`, **TTL 30일**,
  httpOnly + secure(prod) + sameSite=lax (`lib/auth.ts`)
- **LPV 정의**: Graph `actions[]` 의 `action_type === "landing_page_view"` / 구매 = `purchase`|`omni_purchase`
- **금액 표기**: Meta 계정 통화 = **KRW**. 개수(view·노출)만 K/M 축약, 금액은 풀 자릿수 (`lib/format.ts` 룰)
- **가로 스크롤 표**: `.no-native-sb` 로 shadcn Table 내부 `[data-slot=table-container]` overflow 를
  `visible !important` 로 무력화 + 하단 sticky `.hbar` 커스텀 스크롤바 (ScrollableTable)

---

## 1. `/login` — 로그인

- **렌더링**: Client Component
- **구성**: Monkey 마스코트(기본 happy → 입력 중 shy → 오류 angry) + 비밀번호 input(autoFocus)
  + "들어가기" 버튼 (로딩 중 "확인 중...", 공란/로딩 시 disabled)
- **흐름**: submit → `POST /api/login {password, next}` → 성공 시 `router.replace(next)` + `router.refresh()`
  / 실패 시 "비밀번호가 틀려요"
- **쿼리**: `?next=<path>` (기본 `/`)

### `POST /api/login`
- 요청 `{password: string, next?: string}` →
  성공 200 `{ok:true, next}` + Set-Cookie(`meta_app_session`, 30일) / 실패 401 `{ok:false, error:"invalid"}`
- 내부: `checkPassword()`(timingSafeEqual) → `makeSessionCookie()`

---

## 2. `/` — 홈 대시보드

- **렌더링**: 서버 컴포넌트, `revalidate = 60`
- **데이터** (Promise.all):
  - `fetchAccountSummary(어제)` / `(그저께)` / `(W-1: D-7~어제)` / `(W-2: D-14~D-8)` — dk-meta 경유 계정 합계
  - `fetchSupersaleCompare(today)` (기간 지나면 null/비활성)
  - `fetchJpyKrw()` 환율
  - RPP·매출 시드 (`rppRange`, `salesRange`)
- **Total ROAS** = `매출JPY × 환율 ÷ (Meta spend KRW + RPP spend JPY × 환율)` (분모 0 이면 0)
- **화면**:
  1. **어제 (vs 그저께)** — KpiCard 그리드: Spend / RPP / 총 광고비 / Total ROAS / CTR / CPC* / CPLPV* / Freq* / LPV
     (*표시는 `invertColor` — 낮을수록 좋음, 색 반전. |Δ|<0.1% 는 중립)
  2. **최근 7일 (W-1 vs W-2)** — 동일 KPI 세트
  3. **슈퍼세일 증액 모니터링** (`sale.active` 일 때만) — Spend/LPV/CPLPV*/CTR/Freq*/Reach 의
     증액후(6/4~) vs 증액전 동일 일수 창 Δ%. 표기: ▲/▼/▬ + 절대값 1자리
- 하단에 `AnnouncementStack`(팝업 체인)과 `DailyIssuesPopup` 이 레이아웃 경유로 뜬다 (03 문서 참조)

---

## 3. `/ads` — 광고 목록

- **렌더링**: 서버 컴포넌트, `revalidate = 60`, 기간 = 최근 7일(어제까지)
- **데이터**: `fetchAds(since, until)` (ad-level, **ACTIVE 만** — status 전체 실패 시 전체 유지 fail-open)
  + `buildAdGradeMap()` (ad_id → WL 콘텐츠 등급/핸들). `spend > 0` 필터.
- **화면**:
  1. 요약 3카드: 광고 수 / 총 지출 / 총 LPV
  2. **BEST/WORST (종합)**: 자격 노출≥200, 종합점수 = percentile 가중합 **CPLPV 50% + CTR 30% + CPC 20%**,
     BEST 3 → WORST 는 BEST 제외 후 3 (풀 작으면 축소). 각 행: 순위 배지, ad_name, adset, 등급 배지,
     CPLPV/CTR/CPC/Spend, 점수. 행 클릭 → `/ads/{adId}`
  3. **CTR / CPC / CPLPV 별 TOP·BOTTOM 5**: 자격 spend ≥ ₩1,000 (`bestWorst`)
  4. **전체 광고 표**: 컬럼 = 광고(ad_name+adset) / Spend(+SpendBar) / CTR / CPC(md↑) / CPLPV / Freq(md↑),
     spend 내림차순
- **셀 색상 규칙** (StatusPill):
  - CTR: ≥1.71% good / ≥1.0% neutral / <1.0% bad
  - CPC: ≤₩100 good / ≤₩150 neutral / >₩150 bad
  - Freq: ≥2.5 bad / ≥2.0 warn / 그 외 neutral

---

## 4. `/ads/[adId]` — 광고 상세

- **렌더링**: 서버 컴포넌트, `revalidate = 60`, params 는 Promise (Next16)
- **데이터**: `fetchAdInfo(adId)` (DK 최신행 + status 는 Graph live) / `fetchAdDaily(adId, 등록일, 오늘)`
  / `fetchAdCreatives([adId])` (permalink) / `buildAdGradeMap()`
- **화면**:
  - 헤더: 광고명 + 상태 배지(ACTIVE=default variant, 그 외 secondary), 캠페인·애드셋,
    WL 등급 칩 + Organic 등급 + `@handle 콘텐츠 상세 →` 링크, 등록일·집행일수·[게시물 보기 ↗]
  - 스탯 6카드: 총 Spend / 총 LPV / 총 노출 / 평균 CTR / 평균 CPLPV / 최근 Freq
  - `AdDailyCharts`: 일별 6종(Spend·LPV·CTR·CPLPV·Freq·노출) + 누적 3종(LPV·CTR·CPLPV).
    누적 CTR = 누적클릭/누적노출, 누적 CPLPV = 누적spend/누적LPV

---

## 5. `/alerts` — 알림

- **렌더링**: 서버 컴포넌트, `revalidate = 60`, 기간 = 최근 7일
- **데이터**: `fetchAds` → 각 후보 빌더 (조건식·상수는 01 문서 §7 그대로):
  - `budgetIncreaseCandidates(ads)` — Proven 만, spend≥₩30K, CPLPV≤평균×0.85 AND CTR≥평균×1.1, Freq≤2.5
  - `graduationCandidates(ads, 어제)` — Testing + 노출≥200 + D+3+ + CPC≤₩95 AND CTR≥8% AND CPLPV≤₩130
    (clicks/LPV 0 의 거짓통과 차단: cpc>0 && cplpv>0 필수)
  - `offRecommendations(adsRaw, 어제)` — candidates(강한 신호)/monitoring(D+5 유예) 분리,
    풀 자격 노출≥200 (단 delivery 실패 평가 대상 D+90+&spend<₩5K 는 노출 미달도 포함)
  - 피로도: `frequency ≥ 2.5` / 저성과 CTR: `노출≥1000 && 0<ctr<1.0%` / CPC 스파이크: `클릭≥5 && cpc > ₩200(KPI×2)`
- **화면**: 카드 7종 (증액 💰 / 졸업 🎓 / Off 권장 💔 / Off 모니터링 / 피로도 / 저CTR / CPC 스파이크).
  각 카드 헤더에 판정 기준 문구 명시, 빈 상태는 Monkey(tongue/dizzy) + 문구.
  Off 권장 행에는 트리거 사유 텍스트(빨강) — 예: `CPC ₩163 > ₩150 · CPLPV ₩212 ≥ ₩190`.
  졸업 카드 하단 노트: "승급 = Testing PAUSE → Proven 새 ad_id (learning 재진입 CPLPV +25~32%)"

---

## 6. `/budget` — 예산

- **렌더링**: 서버 컴포넌트, `revalidate = 60`
- **쿼리**: `?period=1d|7d|30d|mtd|lifetime|monthly` × `?view=campaign|adset|ad`
- **데이터**:
  - 기간 모드: `periodRange(period)` → `fetchAds` + `rppRange`(시드) + `salesRange`(시드) + 환율
    → 총광고비 = Meta KRW + RPP¥×환율, Total ROAS = 매출¥×환율 ÷ 총광고비
  - 월별 모드: `fetchMonthlySpend()`(계정 월별, ACCOUNT_START=2025-12-01) + `fetchMonthlyAdSpend()`(광고별)
    + `rppMonthly()` + `salesMonthly()`
- **화면**:
  1. 기간 탭 6개 (링크)
  2. 총 광고비 카드: Meta / RPP(라쿠텐) / 라쿠텐 매출 / ROAS — RPP·매출은 ¥ 병기
  3. 단위별 분해 표 (캠페인/애드셋/광고 탭): Spend / Share% / LPV(md↑) / CTR / CPLPV, spend 내림차순
  4. (월별) 월×[Meta, RPP, 광고비합, 매출, ROAS] 표 + TOTAL 행, 최신 월 위
  5. (월별) `<details>` 토글 월별 광고 상세: 광고별 사용액 내림차순 + 월 합계 (진행 중 달은 open)

---

## 7. `/products` — 전환

- **렌더링**: 서버 컴포넌트, **`revalidate = 3600` + `maxDuration = 60`**
- **데이터**: `fetchProductMetrics()` —
  Meta ad-level 월별(2026-01~) × `classifyAd`(ASIN 맵 → 라벨, campaign 분류 금지)
  ⊕ `product-access-seed.json` (RMS 商品ページ visitAll/unitsAll; 과거월 정적 + 당월은 09:00 갱신)
- **화면**: 카드 3장 — 전체(=PPSU+Stainless 합, 店舗 전체 아님 — 니플 등 제외) / PPSU / Stainless.
  각 표 7지표: 월 / 접속자수 / 메타유입(LPV) / 유입비중%(=LPV/접속) / 주문 / CPLPV / Spend / 전환율%(=주문/접속).
  월 내림차순, 진행 중인 달 표시. 상단 설명문에 산식·출처 명기.

---

## 8. `/influencers` — 콘텐츠 (풀 · 성과 티어 · 태깅 항목)

- **렌더링**: 서버 컴포넌트, `revalidate = 60`
- **데이터**:
  - `buildContentPool({includeDkOnly: true})` — 콜라보 시트 + DK 신규 자동 편입 (5분 unstable_cache)
  - `fetchContentTags()` / `fetchWatch3sMap()` / `fetchTaxonomy()` — 각각 실패해도 페이지는 뜨도록 catch
  - `buildPerfTiers(pool, tags, w3s, taxonomy.hooks)` — 추가 fetch 없이 계산만
- **탭 1 — 콘텐츠 풀**: ScrollableTable, 열 16개(고정폭):
  인플/제품(링크·WL/DK 배지·영상 버튼) · 태그(TagCell — 클릭 시 모달 편집) · Deal · 팔로워 ·
  D+3 view · organic view(누적−LPV) · 전체 view(티어) · ER(티어) · 3s율(미측정 * 표기) · Hook Type ·
  LPV · CPLPV · CTR (WL 만) · 단가(티어) · VTR(티어) · 정성
- **탭 2 — 성과 티어**: KM(소구점)별 / 훅별 표 — ER·CTR·CPLPV·3s율 각각 percentile 5티어(S~D) + 평균값
  + 표본 n (n<5 는 "?"). CPLPV 만 낮을수록 상위.
- **탭 3 — 태깅 항목**: 분류 체계 설명표 (KM S##_F##, 훅 HV/HC-##, 앵글 보류, 등급 축 정의)

### `POST /api/tags` (수동 태그 저장)
- 요청 `{shortcode, field: "km"|"hook", value}`
- 검증 (정규식 서버 강제):
  - shortcode: `^[A-Za-z0-9_-]+$`
  - km value: `^S\d{2}_F\d{2}(,S\d{2}_F\d{2})*$` 또는 `"-"`(자동 기각 센티널) 또는 `""`(해제)
  - hook value: `^H(?:[VC]-)?\d{2}(,H(?:[VC]-)?\d{2})*$` 또는 `""` (구 H## 읽기 호환)
- 처리: `upsertManualTag()` → Sheets API 셀 PUT/행 append → `revalidatePath("/influencers")`
- 응답: 200 `{ok:true}` / 400 `{error}` / 500 `{error}`

---

## 9. `/influencers/[handle]` — 인플루언서 상세

- **렌더링**: 서버 컴포넌트, `revalidate = 300`. handle 은 decodeURIComponent, 미존재 시 `notFound()`
- **데이터**: `fetchInfluencer(handle)` (풀에서 조회) + `fetchContentTags()` +
  콘텐츠별 `buildContentSeries(c)` (DK content_metrics_daily 시계열 + WL ad 일별 — organic = 누적view−paid LPV)
- **화면**:
  - 헤더 카드 (등급별 배경): 등급 칩, @handle, WL 배지, 콜라보 수·타입·상태, 팔로워, 최고 등급
  - 3카드: 비용 합계(보수/COGS/WL) · 노출 합계(Organic/WL impressions/평균 VTR) · 평균 단가(Organic 단가/WL CPM/ER)
  - 스탯 그리드: 평균 D+3 view, 현재 누적 view, 정량 percentile, 정성 평균, Master compliance/overall
  - 콘텐츠별 시계열 차트 (`ContentCharts` — organic 항상, paid 는 WL 만)
  - 콜라보 이력 표 (ScrollableTable): 등급/기간/제품(SKU)/태그/Deal/Fee/COGS/WL spend/D+3 view/단가/VTR/ER/정성/URL,
    행 배경 = 콘텐츠 등급색
  - 정성 6축 평균 (scriptFollow/compliance/easeOfWork/hook/wowScene/overall)

---

## 10. `/codes` — WL 코드 관리

- **렌더링**: 서버 컴포넌트, `revalidate = 60`
- **데이터**: `buildContentPool()` (DK 편입 없음 — 시트 기반만)
- **상태 판정**: wlCode 공란 → `missing` / `×`·`X`·`x` → `declined` / 그 외 → `issued`.
  `running` = issued 중 `wlAdIds.length > 0` (ACTIVE 광고 보유)
- **화면**:
  1. 요약 4카드: 코드 발급 / 광고 집행 중 / 미발급(×) / 공란
  2. 발급 코드 표 (집행 중 우선 → spend 순): 크리에이터(@handle 링크+등급 배지) / 제품·dealType /
     WL code (`<code>` + 복사 버튼) / 광고(집행 중 N개 배지 + spend)
  3. 코드 없는 콜라보 그리드 (@handle + ×/공란 구분)

---

## 11. 디버그 API (운영 진단용 — UI 없음)

### `GET /api/daily-issues`
`lib/daily-issues.ts fetchDailyIssues()` 결과 그대로:
```jsonc
{
  "date": "YYYY-MM-DD",          // KST
  "newAds": [{ "ad_id", "name", "adset_name", "status", "permalink": "url|null" }],
  "graduated": [{
    "ad_id", "name", "adset_name",  // 새 Proven adset
    "from_adset",                    // 기존 Testing adset
    "spend_lifetime", "spend_7d",
    "ctr_7d", "kpi_ctr",             // kpi_ctr = 8.0 (KPI_WL_CTR)
    "share_spend", "share_clicks", "share_lpv"   // 직전 7d Testing adset 내 점유율 %
  }]
}
```
감지 규칙: 오늘(KST) created + Proven adset + 동일 ad_name 이 Testing adset 에 존재 → 졸업 / 그 외 신규.

### `GET /api/debug-pool`
콘텐츠 풀 요약: 전체 수 / WL 수 / WL spend·impressions 합 / 샘플 행.

### `GET /api/debug-wl`
WL 귀속 진단: 시트 콜라보 수, collabKeys 수, 핸들 prefix 목록, matched/unmatched 광고 수,
총 spend/impressions, shortcode 별 귀속 내역(매칭 트랙 표기), 미매칭 광고 상위 목록.

---

## 12. 캐싱 요약

| 라우트 | revalidate |
|---|---|
| `/` `/ads` `/ads/[adId]` `/alerts` `/budget` `/codes` `/influencers` | 60s |
| `/influencers/[handle]` | 300s |
| `/products` | 3600s (+ maxDuration 60) |
| Graph fetch | 60~600s (호출별) / 시트 CSV 60s / 택소노미 3600s / 환율 12h |
| `buildContentPool` | unstable_cache 300s |
