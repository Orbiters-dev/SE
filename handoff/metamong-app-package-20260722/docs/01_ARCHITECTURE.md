# 01. 메타몽 앱 아키텍처 & 재구현 가이드

> 이 문서는 패키지의 메인 문서다. 라우트별 상세는 `02_PAGES_AND_ROUTES.md`,
> 컴포넌트 상세는 `03_COMPONENTS.md`, 파이프라인 도구 상세는 `04_PIPELINE_TOOLS.md`.
> 모든 수치·조건식은 2026-07-22 시점 소스 코드에서 그대로 옮긴 것이다.

---

## 1. 한 줄 정의

**메타몽 앱** = Grosmimi JP(라쿠텐 스토어) Meta 광고 + 인플루언서 WL(whitelisting) 콘텐츠 운영을
한 화면에서 판정하는 **읽기 전용 운영 대시보드**. 광고 mutate(on/off·예산)는 하지 않고,
"무엇을 켜고/끄고/증액할지"의 **후보 판정과 근거 제시**까지만 한다. 실행은 운영자가 Ads Manager에서.

## 2. 기술 스택 (package.json 실측)

| 레이어 | 기술 | 버전 |
|---|---|---|
| 프레임워크 | Next.js (App Router, RSC 중심) | **16.2.7** |
| UI | React | 19.2.4 |
| 스타일 | Tailwind CSS v4 (`@tailwindcss/postcss`) + shadcn(base-ui 계열) | tailwindcss ^4 |
| 차트 | **Recharts** | ^3.8.1 |
| CSV 파싱 | csv-parse (Google Sheets CSV export 파싱) | ^6.2.1 |
| 아이콘 | lucide-react | ^1.17.0 |
| 기타 dep | @tanstack/react-query(^5.101.0 — 설치돼 있으나 현행 코드는 RSC fetch 캐시 사용), clsx, tailwind-merge, class-variance-authority, tw-animate-css | |
| 언어 | TypeScript ^5 | |
| 배포 | **Vercel CLI** (`vercel --prod`) — SE 레포에서 meta-app 은 gitignore, git push 배포 아님 | 계정 seheo-9230 / 프로젝트 meta-app / alias meta-app-one.vercel.app |

빌드 스크립트 (`package.json`):

```json
"dev": "next dev",
"prebuild": "node scripts/check-status-source.mjs",   // ← 절대 룰 가드 (아래 §7-1)
"build": "next build",
"start": "next start"
```

## 3. 디렉터리 맵

```
meta-app/
├─ app/
│  ├─ page.tsx                 # 홈 (어제/7일 KPI + Total ROAS + 슈퍼세일 비교)
│  ├─ products/page.tsx        # 전환 탭 (제품별 월별: 접속·메타유입·비중·주문·CVR)
│  ├─ ads/page.tsx             # 광고 탭 (7일 풀 + BEST/WORST + 전체표)
│  ├─ ads/[adId]/page.tsx      # 광고 상세 (생애 일별/누적 차트)
│  ├─ budget/page.tsx          # 예산 탭 (기간별 Meta+RPP+매출+Total ROAS, 월별 분해)
│  ├─ alerts/page.tsx          # 알림 탭 (증액/졸업/OFF/모니터링/피로도/저CTR/CPC스파이크)
│  ├─ influencers/page.tsx     # 콘텐츠 탭 (콘텐츠 풀 + 성과 티어 + 태깅 항목)
│  ├─ influencers/[handle]/    # 인플루언서 상세 (콜라보 이력 + 시계열)
│  ├─ codes/page.tsx           # 코드 탭 (WL 코드 발급/미발급 현황)
│  ├─ login/page.tsx           # 비밀번호 로그인
│  └─ api/
│     ├─ login/route.ts        # POST 비밀번호 → HMAC 세션 쿠키
│     ├─ tags/route.ts         # POST 수동 태그 저장 (→ Google Sheets)
│     ├─ daily-issues/route.ts # GET 오늘 신규/졸업 광고 (팝업용)
│     ├─ debug-pool/route.ts   # GET 콘텐츠 풀 디버그
│     └─ debug-wl/route.ts     # GET WL 귀속 디버그
├─ components/
│  ├─ AppShell.tsx             # 헤더 + 모바일 하단 네비 (7탭)
│  ├─ meta/*                   # 도메인 컴포넌트 (팝업 체인·차트·태그편집·등급칩 등)
│  └─ ui/*                     # shadcn 계열 primitives
├─ lib/                        # ★ 도메인 로직 전부 (아래 §5, §7)
├─ scripts/check-status-source.mjs  # prebuild 가드
├─ proxy.ts                    # Next 16 미들웨어(구 middleware) — 전 라우트 로그인 게이트
└─ public/monkeys/*.svg        # 마스코트 10종 / public/decks/*.html 산출물 호스팅
```

`public/decks/` 는 앱 기능과 무관한 **HTML 리포트 호스팅 폴더**다 (노션 링크용 산출물 배포처).
이식 시 대시보드 기능에는 불필요 — 정책적으로 유지 여부만 결정하면 된다.

## 4. 데이터 소스 전체 목록 (출처 포함)

앱이 읽는 외부 소스는 정확히 6종 + 시드 JSON 3종이다.

### 4-1. DataKeeper (사내 PG API) — 1차 데이터 소스

- Base: `https://orbitools.orbiters.co.kr/api/datakeeper/query/?table=...`
- 인증: `Authorization: Bearer <DK_SE_READ_TOKEN>` (read tier). env 부재 시 소스 내 fallback 토큰(§9).
- 클라이언트: `lib/datakeeper.ts` — **동시요청 상한 4 + 429/5xx 지수 백오프(150/400/900ms+지터) 4회 재시도**.
  orbitools nginx/gunicorn 이 버스트에 즉시 503을 뱉는 실측 한계 때문 (필수 이식 사항).
- `fields=` 파라미터로 컬럼 선택 필수인 테이블 있음 — Next data cache 한도 2MB 초과 시
  매 렌더 재fetch → DK 부하 → 503 루프 (content_posts 3.3MB→0.22MB, raw_creative 5.6MB→0.2MB 실측).

| 테이블 | 용도 | 주의 |
|---|---|---|
| `meta_ads_daily` (brand="Grosmimi JP") | 광고 일별 성과 (spend/impr/clicks/reach/freq/purchases/LPV/…) | 전체 이력 미보유 (2026-03-01부터 + 누락 구간) → Graph union 으로 보완 중 (§7-2) |
| `raw_meta_ad_creative` | 광고별 effective_status / IG media_id / permalink | **status 는 stale 위험 — Graph 실시간의 fallback 전용** (§7-1) |
| `content_posts` | IG 게시물 메타 (post_date, followers, views_30d, plays_30d, ER, url) | fields 필수. post_id = IG shortcode |
| `content_metrics_daily` | 게시물 일별 views/likes/comments (D+3 뷰 산출용) | 50K행 limit, 0-glitch 행 존재(무시 로직 있음) |

### 4-2. Meta Graph API (v18.0) — status 실시간 + 이력 보완

- Base: `https://graph.facebook.com/v18.0` (`lib/meta-constants.ts META_GRAPH_BASE`)
- 인증: `META_JP_ACCESS_TOKEN` (query param), 계정 `META_JP_AD_ACCOUNT_ID` = `act_4117678028561958`
- 클라이언트: `lib/meta-api.ts`
- 사용처:
  1. **on/off 상태**: `fetchAdStatuses` — 계정 edge `/act_x/ads?fields=id,effective_status` 페이지네이션.
     (per-id `?ids=배치` 방식은 배치 내 삭제된 id 1개로 전체 400 → fail-open 사고 이력. 계정 edge가 정답)
  2. **인사이트 union**: DK 미보유 이력 + LPV 보강 (§7-2)
  3. **크리에이티브**: `?ids=<50개 배치>&fields=creative{instagram_permalink_url,effective_instagram_media_id}`
  4. **게시자 username**: ad → media_id → `/media?fields=username` 2단 배치 (WL 귀속 트랙 2)
  5. **오늘 등록 감지**: `created_time` 은 DK 미보관 → `/act_x/ads?fields=created_time,...` (daily-issues)
- 통화: **JP 계정 = KRW** (₩ 표기 전제. JPY 아님)
- LPV 정의: `actions[]` 중 `action_type == "landing_page_view"` (구매 = `purchase`/`omni_purchase`).
  전환 픽셀은 Rakuten LP 라 없음 → **LPV 가 측정 천장** (Conversion 불가 확정, 2026-06-30).

### 4-3. Google Sheets — 읽기 (공개 CSV export, 무인증)

`lib/sheets.ts`. URL 형식: `https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>`

| 시트 | ID / GID | 내용 · 파싱 규칙 |
|---|---|---|
| 콜라보 SSOT — Master DB 탭 | `1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU` / gid=0 | 인플루언서 로스터. 행 3부터, **컬럼 인덱스 고정**: 0=creatorId, 2=fullName, 7=babyInfo, 16=igHandle, 18=followers, 20=avgViews, 29=creatorType, 31/32=rating, 33=pic, 35=status, 36/37=recentContact/Rate |
| 콜라보 SSOT — Grosmimi 탭 | 동일 ID / gid=386147805 | 콜라보 이력. 행 4부터(데이터), 인덱스: 0=기간, 3=creatorId(@), 5=deliverableType, 6=product, 8=status, 13=expectedUpload, 15=wlCode, 16=url(→shortcode 추출), 23=dealType, 24=fee, 27=adCode, 29=wlDuration, 31/32=paymentStatus/Date, 37~42=정성 6축(scriptFollow/compliance/easeOfWork/hook/wowScene/overall), 43=hookType |
| 태그 시트 — Content Tags (JP) 탭 | `13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE` / gid=699625745 | 자동+수동 태그. **헤더명 기준 동적 컬럼 해석** (shortcode, km_primary, km_sub, hook_primary, confidence, evidence, km_manual, hook_manual). km_manual="-" = 자동태그 기각 센티널 |
| 택소노미 — KM SSOT (JIAH)_v2 | `1HnouC4gMRVTcGwGeInJlGJl_W7eNgI_4m63ZDSxzfZY` / gid=44578416 | S##(Subject) → S##_F##(Focus) 종속. 행 regex 스캔 (`^S\d{2}_F\d{2}$`) |
| 택소노미 — WL 훅 taxonomy v2 | 동일 ID / gid=1298743912 | 훅 2축: HV-##(비주얼) / HC-##(캡션). 구 H## 은 읽기 호환만 |

> ⚠️ Master/Grosmimi 탭은 **컬럼 인덱스 하드코딩** → 시트에 열 삽입 시 앱이 조용히 깨진다.
> 태그 탭만 헤더명 기반(과거 사고 후 수정). 이식 시 전부 헤더명 기반 권장.

### 4-4. Google Sheets — 쓰기 (수동 태그 저장)

`lib/tag-write.ts`. 태그 시트의 `km_manual`/`hook_manual` 셀 upsert.
- 인증: **서비스 어카운트 JWT RS256 직접 서명** (`node:crypto` — 외부 라이브러리 0).
  `GOOGLE_SA_EMAIL` + `GOOGLE_SA_PRIVATE_KEY` → oauth2.googleapis.com/token 교환, scope=spreadsheets.
- 컬럼 위치는 헤더 행에서 매번 동적 해석 (컬럼 삽입 사고 재발 방지). 행 없으면 append.
- SA: `influence-sync@influencer-db-claude.iam.gserviceaccount.com` — 시트에 편집자로 공유돼 있어야 함.

### 4-5. Rakuten RMS Order API — 당월 라이브 주문

`lib/rakuten.ts`. `https://api.rms.rakuten.co.jp/es/2.0/order/searchOrder` + `getOrder`.
- 인증: `Authorization: <RMS_ESA_AUTH>` (형식 `ESA base64(serviceSecret:licenseKey)` — licenseKey 만료 로테이션 있음).
- searchOrder 는 긴 기간에 403 → **7일 청크 + 최대 ~40일 창** 유지. getOrder 는 100건 배치.
- 분류: manageNumber 에 `ppsu`→PPSU / `stainless`→Stainless, 그 외(니플 등)=제외. orderProgress 900(취소확정) 제외.
- 과거월은 시드(product-access-seed.json)로 정적, **당월만 라이브**.

### 4-6. 환율

`lib/rpp.ts fetchJpyKrw()` — `https://open.er-api.com/v6/latest/JPY` (12h 캐시). 실패 시 fallback **9.11** (2026-07-21 실측).
JPY(라쿠텐 매출·RPP) → KRW(Meta spend와 합산) 환산에 사용.
참고: 인플루언서 보수 환산은 별도 상수 `KRW_PER_JPY = 10` (influencer-aggregation.ts — 고정 근사값, 라이브 환율 아님).

### 4-7. 시드 JSON 3종 (파이프라인 도구가 갱신 → 재배포로 반영)

앱 번들에 import 되는 정적 JSON. **갱신 = 도구가 파일 덮어쓰기 + `vercel --prod` 재배포** 구조.

| 파일 | 스키마 | 생산자 (스케줄은 §8) | 소비자 |
|---|---|---|---|
| `lib/rpp-daily-seed.json` | `{updated_at, days: {YYYY-MM-DD: {clicks, spend_jpy, cpc_jpy, ctr_pct, sales_12h_jpy, orders_12h, roas_12h_pct, sales_720h_jpy, orders_720h, roas_720h_pct}}}` | `tools/collect_rpp_daily.py --update-app` (RPP 콘솔 내부 API downloadPerfFile periodType=2 — 공식 API 미노출이라 Playwright 로그인+xsrf 토큰) | `lib/rpp.ts` → 홈/예산 Total ROAS 분모 |
| `lib/rakuten-sales-seed.json` | `{updated_at, days: {날짜: {sales_jpy, orders, units}}}` | `tools/collect_rakuten_sales_daily.py --update-app` (RMS Order API, 취소 제외, 40일 재수집 창) | `lib/rakuten-sales.ts` → Total ROAS 분자 |
| `lib/product-access-seed.json` | `{PPSU: {YYYY-MM: {access, orders}}, Stainless: {...}}` | `tools/rms_access_downloader.py --update-app` (RMS 商品ページ get-item-list: visitAll/unitsAll, 商品管理番号 분류) | `lib/product-metrics.ts` → 전환 탭 |
| `lib/store-seed.json` | 월별 {access, orders, cvr} | (잔재) | **소비처 없음 — 죽은 파일.** 이식 시 제외 가능 |

## 5. 인증 / 게이트

- `proxy.ts` (Next 16: middleware → proxy 개명): `/login`, `/api/login`, 정적 파일 제외 전 라우트에서
  세션 쿠키 검증 실패 시 `/login?next=<path>` 리다이렉트.
- `lib/auth.ts`: 쿠키명 **`meta_app_session`**, 값 `v1.<expiryMs>.<HMAC-SHA256(v1.<expiryMs>)>`,
  TTL **30일**, 시크릿 `APP_SESSION_SECRET`(최소 16자), 비밀번호 `APP_PASSWORD` (단일 사용자).
  비교는 `timingSafeEqual`. DB/세션 스토어 없음.
- `POST /api/login` `{password, next}` → 성공 시 Set-Cookie(httpOnly, secure(prod), sameSite=lax) + `{ok:true,next}` / 실패 401.

## 6. 데이터 흐름 (요청 한 사이클)

```
[브라우저] → proxy.ts(쿠키 검증) → RSC 페이지 (revalidate 60~3600s)
   페이지 → lib/meta-aggregations · influencer-aggregation · product-metrics ...
      ├─ lib/dk-meta.fetchInsights()          ← DK meta_ads_daily  ⊕ Graph union(이력·LPV 보완)
      ├─ lib/dk-meta.fetchAdStatuses()        ← Graph /act_x/ads (실시간) → 실패 시에만 DK raw
      ├─ lib/sheets.fetchMaster/fetchCollabs  ← 콜라보 시트 CSV (revalidate 60s)
      ├─ lib/sheets.fetchContentTags/Taxonomy ← 태그·택소노미 시트 CSV (60s/3600s)
      ├─ lib/datakeeper.fetchContentPosts/Metrics ← DK content_* (fields 경량화)
      ├─ lib/wl-attribution                   ← 위 결과 조합 (4-track 매칭, §7-4)
      ├─ lib/rpp.ts / rakuten-sales.ts        ← 번들 내 시드 JSON (정적)
      └─ lib/rakuten.ts                       ← RMS Order API (당월만, revalidate 3600s)
[쓰기 경로] TagCell/TagEditor → POST /api/tags → lib/tag-write (Sheets API) → revalidatePath("/influencers")
```

캐시: 전 페이지 ISR (`revalidate = 60`; 인플 상세 300, 전환 탭 3600 + `maxDuration = 60`).
`buildContentPool` 은 `unstable_cache` 5분 — DK 50K행 쿼리 보호.

## 7. 핵심 도메인 로직 (판정 규칙 전부)

### 7-1. ★ 절대 룰: 광고 on/off = Graph 실시간만

- 배경 사고: DK `raw_meta_ad_creative` 는 로컬 push(09:10)가 죽으면 stale ACTIVE 로 남는다.
  2026-07-09 RHYTHMICAL_MAMA — 이미 OFF 한 광고가 후보에 재등장.
- 규칙: 졸업/OFF/증액/집행중 카운트 등 **모든 on/off 판정은 `lib/dk-meta.ts fetchAdStatuses()`
  (Graph 계정 edge 우선, DK 는 Graph 실패 시 fallback) 만 경유**한다.
- 강제 장치: `scripts/check-status-source.mjs` (prebuild) 가
  ① allowlist(dk-meta.ts, meta-api.ts) 밖의 `raw_meta_ad_creative` 참조
  ② 같은 파일 내 `dkQuery` + `effective_status` 동시 사용
  을 감지하면 **빌드 실패**. 이식 시 이 가드를 반드시 유지/이식할 것.
- 단, 성과·spend **이력 표시는 OFF 광고도 그대로** (후보/집행중 판정만 ACTIVE 한정).
- status 조회 전체 실패 시 fail-open(전부 유지) — 빈 표 방지 의도적 선택.

### 7-2. DK ⊕ Graph union (임시 이력 보완 — 제거 예정 코드)

`lib/dk-meta.ts fetchInsights()`:
DK가 계정 전체 이력(2025-12~)을 다 담지 못함(2026-03-01부터 + 누락 구간) + 과거 LPV 컬럼 부재.
→ DK 를 base 로 두고 Graph(전 기간)를 union: DK 에 없는 `(ad_id, date)` 행은 Graph 로 채우고,
DK 행의 LPV 0 이면 Graph LPV 주입. **DK 백필 완료 시 Graph union 은 제거 예정** (소스 주석 명시).
이식 시: intelligence 쪽 DWH 가 전체 이력을 가지면 이 union 레이어는 통째로 불필요.

### 7-3. 게이트 상수 (`lib/meta-constants.ts` — 전량)

```
CTR_BENCH 1.71% / CTR_LOW 1.0% / FREQ_HIGH 2.5 / CPC_SPIKE_PCT 30%
KPI: WL CTR 8% · 이미지 CTR 4% · CPC ₩100
졸업(Testing→Proven, D+3 판정): CPC ≤ ₩95 AND CTR ≥ 8% AND CPLPV ≤ ₩130   [3개 모두]
OFF(Testing, D+3 판정):
  ① CPC ≤ ₩150 AND CTR ≥ 5% → 생존
  ② 하나라도 나쁨 → CPLPV ≥ ₩190 이면 OFF / CPLPV 정상이면 D+5 유예(모니터링)
  ③ 둘 다 양호 + CPLPV ≥ ₩190 → OFF (이탈형)
Proven OFF: delivery 실패만 — D+90+ AND 누적 spend < ₩5,000 (시간 단독 트리거 X, WL 3~6개월 운용)
슈퍼세일 비교 상수: 2026-06-04~06-11, 증액 시작 06-02
통화 KRW / Graph v18.0
```

변경 이력이 잦은 값 (동기화 룰: 앱과 `tools/meta_jp_daily.py` 를 같은 턴에 함께 수정):
- 졸업 CPLPV 135→**130** (2026-07-09 확정) / 졸업·OFF 판정 D+7→**D+3** (2026-07-06 확정)
- OFF CPLPV 190→150 하향 **제안 중, 미확정** (확정 전 판정은 현행 190)

### 7-4. WL spend 귀속 (광고 ↔ 인플루언서 콘텐츠 매칭, `lib/wl-attribution.ts`)

전체 이력(2025-12-01~오늘) ad-level 인사이트를 4-track 순차 매칭 (2026-06-10 승인):

1. **partnership**: creative permalink 의 shortcode 가 콜라보 시트 게시물과 정확 일치할 때만
2. **poster_username**: 광고 게시물의 실제 IG username = 시트 Creator ID 정확 일치
   (공식계정 grosmimi_japan 제외. 동일 인플 행 복수면 광고명 제품 토큰 ppsu/stain+200/300 +4점,
   사이즈 +2점, 날짜 근접 +0~1점 스코어로 행 선택)
3. **ad_code**: 시트 Ad code(col 27) 가 ad_name 에 substring 포함
4. **ad_name_handle**: ad_name 토큰(≥3자) 에 핸들 prefix 매칭 + 광고명 날짜(YYYYMMDD 또는
   Y26M06D19 형식)와 게시일 근접 (보수적 fallback)

집계: shortcode 별 spend/impressions/clicks/LPV 합산 + `adIds`(**ACTIVE 만** — §7-1).
미매칭 광고는 unmatchedAds 로 노출(디버그 `/api/debug-wl`).

### 7-5. ad_name 파싱 규약 (광고 명명 규칙이 곧 데이터 스키마)

광고 이름에 메타데이터가 인코딩돼 있어 파서가 판정의 전제가 된다:

- **신 명명** (2026-06~): `Y26M06D19_Grosmimi_RKT_WL-G_핸들_ASIN_CT-##`
  - `Y(\d{2})M(\d{2})D(\d{2})` → 런칭일 (D+N 계산 기준)
  - `WL-P` = Paid / `WL-G` = Gift
- **구 명명**: `... | PAID | ... | yyyymmdd` (끝 8자리 = 런칭일, `| PAID |`/`| GIFT |` 라벨)
- 제품 분류: ad_name 내 **ASIN (`B0[A-Z0-9]{8}`) → `lib/product-metrics.ts` ASIN_PRODUCT 맵(68개)** 이 1순위.
  라벨(ppsu/stainless substring) 이 2순위. **campaign 명으로 분류 금지**
  (6/18 이전 Stainless 캠페인에 PPSU 광고 혼재 → 비중 130% 사고 이력).
- Testing/Proven 판정: campaign_name 또는 adset_name 에 `/test/i` — 나이 기반 판정 금지
  (D+15+ Testing 이 Proven 으로 새는 것 방지).

### 7-6. 종합 BEST/WORST (광고 탭)

자격: 7일 노출 ≥ 200. 종합점수 = 풀 내 percentile 가중합 **CPLPV 50% + CTR 30% + CPC 20%**
(LPV 효율이 운영 1차 축). clicks/LPV 0 이면 해당 축 최하점. WORST 는 BEST 제외 후 선정.
n=3 (풀 절반 미만이면 자동 축소).

### 7-7. 증액 후보 (알림 탭)

**Proven 만** (Testing 은 증액 제도 없음 — 졸업/OFF 뿐, 2026-07-07 확정).
자격: spend ≥ ₩30,000, LPV·CTR > 0, Freq ≤ 2.5, Testing 아님.
조건: `CPLPV ≤ 풀평균×0.85 AND CTR ≥ 풀평균×1.1`.
증액폭: CPLPV 개선율 ≥50% → +30% / ≥20% → +20% / 그 외 +10%. 상위 5개.

### 7-8. 콘텐츠 등급 (`lib/influencer-aggregation.ts` — Organic 풀 / WL 풀 분리)

- **Organic 풀** (전 콘텐츠): view = **D+3 실측** (±7일 창에서 가장 가까운 view>0 행. 실측 없으면 na —
  추정환산 폐기 2026-07-02), 단가 = (보수₩ + COGS₩)/D+3뷰, VTR = D+3뷰/팔로워
- **WL 풀** (WL spend 있는 콘텐츠만): view = 현재 누적(최신 view>0 행, 없으면 views_30d),
  통합 단가 = (보수+COGS+WL spend)/현재뷰, WL CPM/CTR/CPLPV
- 점수: percentile 가중합 **단가 0.45 + VTR 0.45 + 정성 0.10** →
  등급 S≥80 / A≥60 / B≥25 / C — 단 **S 게이트**: rateScore ≥70 AND vtrScore ≥70 아니면 A로 강등,
  view 미실측이면 S/A → B 강등. 정성 bump: 시트 overall ≥4.5 → +1등급 / ≤2.0 → −1등급.
- 비용 상수: 보수 환산 KRW_PER_JPY=10. COGS (`lib/cogs.ts`): stainless ₩32,000 / fliptop ₩25,000 / ppsu ₩20,000
  (키워드 substring, 긴 키워드 우선). 제품 표기 통일 `lib/product.ts` (ppsu300-skyblue 형식).
- 같은 shortcode 콜라보 중복 행은 1행 병합(빈 필드 보충). DK 자동 편입 옵션(`includeDkOnly`):
  시트에 없는 JP·IG 신규 게시물을 빈 콜라보 행으로 풀에 추가 (콘텐츠 탭 전용).
- 인플루언서 등급 = 보유 콘텐츠 **최고** 등급.

### 7-9. 성과 티어 (`lib/perf-tiers.ts`)

KM(소구점 S##)·훅(HV/HC-##) 그룹별로 ER / CTR / CPLPV / 3초율 각각 **percentile 5티어(S~D)**.
표본 5개 미만 그룹은 "?"(티어 없음). 수동 태그가 있으면 자동 태그 대신 사용, km_manual="-" 는 집계 제외.
3초율 = views/plays, **plays > views 인 실측 행만** (동일값은 미측정 취급).

### 7-10. 오늘의 이슈 (`lib/daily-issues.ts`)

- 졸업 감지 = 오늘(KST) created + Proven adset 소속 + **동일 ad_name 이 Testing adset 에 기존 존재**
  (졸업 메커니즘 "Testing pause + Proven 새 ad_id" 기준. rename 방식은 감지 불가 — 알려진 한계).
- 신규 = 오늘 created 중 졸업 아닌 것 + permalink 첨부.
- 졸업 근거: 직전 7d Testing adset 내 spend/clicks/LPV share + CTR vs KPI 8%.

## 8. 운영 스케줄 (2026-07-22 실측 — Task Scheduler XML 은 `schedules/` 동봉)

| 시각(KST) | 실행 주체 | 커맨드 | 효과 |
|---|---|---|---|
| 08:47~09:52 (5회 cron + 당일성공 dedup) | GitHub Actions `meta_jp_daily.yml` | `python tools/meta_jp_daily.py --mode 1d` | 9시 운영 메일 (앱과 동일 게이트의 메일판) → se.heo@orbiters.co.kr |
| 09:00 | Task Scheduler `RMS_ProductAccess_Update` | `python tools\rms_access_downloader.py --update-app` | product-access-seed.json 갱신 + **vercel --prod 재배포** |
| 09:10 | Task Scheduler `MetaJP_Creative_DK` | `python tools\collect_meta_jp_creative.py` | Graph → DK `raw_meta_ad_creative` 적재 (status fallback 용) |
| 09:20 | Task Scheduler `RakutenRPP_Daily_Spend` | `collect_rakuten_sales_daily.py --update-app` → `collect_rpp_daily.py --update-app` (순차 체인) | 매출·RPP 시드 2종 갱신 + **vercel --prod 재배포** |
| 09:25 | Task Scheduler `MetaJP_ContentTag_Auto` | `python tools\tag_jp_content.py --incremental --write-sheet --sync-jp` | 신규 콘텐츠 LLM 자동 태깅 → 태그 시트 |
| 주간 | GitHub Actions `meta_jp_weekly.yml` | `meta_jp_daily.py --mode 7d` | 주간 메일 |
| (DK 자체) | GitHub Actions (WONGI 측) | — | meta_ads_daily 등 18채널 PST 0:00/12:00 수집 |

주의: GH cron 은 지연/누락이 흔해 다중 cron + 당일 성공 dedup 가드 패턴을 쓴다 (yml 참조).
이식 시 이 체인 전체를 서버 크론 1곳으로 통합하는 것이 정배 (아래 §11).

## 9. 시크릿 / 보안 (이식 시 필수 처리)

| 항목 | 현행 | 이식 시 권장 |
|---|---|---|
| DK read 토큰 | env `DK_SE_READ_TOKEN` + **`lib/datakeeper.ts` 에 fallback 하드코딩** (Vercel env CLI 빈값 버그 회피책이었음) | 하드코딩 제거 + 토큰 로테이션 (소스가 외부에 나간 시점 기준) |
| Meta 토큰 | env. ads_read 스코프 | 시스템 사용자 토큰으로 재발급 관리 |
| RMS ESA | env. licenseKey 만료 주기 있음 (만료 시 401 → 로테이션 이력 있음) | 로테이션 runbook 포함 |
| Google SA 키 | env (`\n` 이스케이프 1줄) | Secret manager |
| 앱 비밀번호 | `APP_PASSWORD` 단일 계정 + HMAC 쿠키 | 사내 SSO 로 대체 |
| 콜라보/태그 시트 | **링크 공개(CSV export 무인증)** 상태가 전제 | 이식 시 Sheets API 인증 읽기로 전환 검토 |

패키지의 `.env.handoff.template` 에 변수별 출처 정리. **실제 값은 미포함 — 별도 채널로 전달.**

## 10. 알려진 이슈 / 기술 부채 (재설계 시 반영할 것)

1. **DK 이력 갭 + Graph union 이중화** (§7-2) — 근본 해결은 DK(또는 새 DWH) 백필.
2. **DK write 토큰 read 강등 (2026-07-08 perm cutover)** — `collect_meta_jp_creative.py` 의 DK push 가
   403 으로 죽으면 raw 테이블이 stale 해짐. 앱은 Graph 실시간 우선이라 안전하지만 fallback 품질 저하.
3. **DK 503 버스트 한계** — 동시 4 + 재시도로 우회 중. 서버측 rate limit 정책이 근본 해결.
4. **시트 컬럼 인덱스 하드코딩** (Master/Grosmimi 탭) — 열 삽입에 취약.
5. **시드 JSON + 재배포 구조** — 데이터 갱신에 배포가 필요한 안티패턴. 이식 시 DB/API 로 대체 (§11).
6. **공지 팝업 하드코딩** — `components/meta/*Announcement.tsx` 6종은 만료일 박힌 1회성 콘텐츠.
   재구현 시 공지 시스템(팝업 체인 프레임 + 데이터 분리)으로 일반화 권장.
7. **roas/purchase_value 필드 미구현** (AdRow 에 0 고정) — LPV 천장 때문에 의도적 미사용.
8. **ContentSummary 의 legacy alias 다수** (organicView=organicViewD3 등) — 상세 페이지 호환용 잔재.
9. **store-seed.json 소비처 없음** — 죽은 파일.
10. **@tanstack/react-query 미사용 dep** — 초기 계획 잔재.

## 11. 재구현 체크리스트 (intelligence 이식용)

**계약(무엇이 같아야 100% 동일인가):**
- [ ] §7 판정 규칙 전부 (상수·조건식·풀 자격·percentile 방식) — 여기가 제품의 본체
- [ ] §7-5 ad_name 파싱 규약 (신/구 명명 모두)
- [ ] LPV 정의 = actions.landing_page_view, 통화 KRW, D+N = 광고명 런칭일 기준
- [ ] Total ROAS = 라쿠텐매출(JPY)×환율 ÷ (Meta spend KRW + RPP spend JPY×환율)
- [ ] on/off = Graph 실시간 절대 룰 + 빌드 가드 상응물

**인프라 대체 매핑 (권장):**
| 현행 | 이식 후 |
|---|---|
| 시드 JSON + vercel 재배포 | RPP/매출/접속 수집기를 서버 크론화 → DB 테이블 (rpp_daily, rakuten_sales_daily, product_access_monthly) |
| 로컬 Task Scheduler 4개 + GH Actions | 단일 스케줄러 (worker/cron) |
| 공개 시트 CSV | Sheets API 인증 읽기 or 시트 자체를 DB 이관 |
| DK+Graph union | DWH 백필 후 단일 소스 |
| 비밀번호 게이트 | SSO |

**검증(마이그레이션 대사):**
- [ ] 임의 7일 구간: 계정 합계 spend/impr/clicks/LPV 가 현행 앱 = 신규 구현 일치
- [ ] 졸업/OFF/증액 후보 목록이 같은 날짜 기준 동일 (특히 D+N 파싱)
- [ ] WL 귀속: `/api/debug-wl` 의 matched/unmatched 카운트 재현
- [ ] 콘텐츠 등급: 동일 입력에서 S/A/B/C 분포 일치 (percentile 동률 처리 = (lt + eq/2)/n 방식 주의)

**환경 준비물 (별도 전달 필요):**
- [ ] Meta 토큰(ads_read, act_4117678028561958 접근) / DK read 토큰 / RMS ESA / Google SA 키+시트 공유 / 앱 비밀번호
- [ ] 파이프라인 쪽: DK write:ingest 토큰, ANTHROPIC_API_KEY(태깅), GEMINI_API_KEY(메일 감사), Gmail OAuth(발송), RMS 로그인(Playwright)

## 12. 관련 시스템 경계 (이 패키지 밖)

- **DataKeeper** (WONGI 소유, EC2 Django + PG): 앱은 읽기만. 수집기·스키마는 별도 시스템.
- **tools/meta_jp_daily.py** (9시 메일): 앱과 **같은 게이트를 공유하는 메일판**. 패키지에 동봉
  (pipeline-tools/) — 앱 상수 변경 시 같은 턴에 동기화하는 운영 룰이 있다.
- **build_jp_meta_deck.py**: 주간 발표 덱 생성기 (앱 데이터 소스 공유, 산출물은 별도 HTML).
- **콜라보 시트**: 인플루언서 운영(DM·계약) 파이프라인이 채우는 SSOT — 앱은 소비자.
