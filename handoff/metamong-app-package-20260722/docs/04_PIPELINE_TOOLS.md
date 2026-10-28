# 04. 데이터 파이프라인 도구 상세 (pipeline-tools/)

> 앱은 읽기 전용이고, 데이터 신선도는 아래 도구들이 만든다. 도구 원본은 패키지 `pipeline-tools/`,
> 스케줄 원본은 `schedules/*.xml`(Task Scheduler 실측 export)과 `github-workflows/*.yml`.
> 공통 의존: `data_keeper_client.py`(DK 읽기), `env_loader.py`(.env 로더),
> `rms_review_playwright.py`(RMS Playwright 로그인 공통 플로우) — 함께 동봉.

## 0. 스케줄 실측표 (2026-07-22 Task Scheduler / GH Actions 기준 — 이것이 정본)

| KST | 주체 | 작업명 | 커맨드 |
|---|---|---|---|
| 08:47/09:02/09:17/09:32/09:52 (당일 성공 시 dedup skip) | GH Actions | `meta_jp_daily.yml` | `python -u tools/meta_jp_daily.py --mode 1d` |
| 09:00 매일 | Task Scheduler | `RMS_ProductAccess_Update` | `python tools\rms_access_downloader.py --update-app` |
| 09:10 매일 | Task Scheduler | `MetaJP_Creative_DK` | `python tools\collect_meta_jp_creative.py` |
| 09:20 매일 | Task Scheduler | `RakutenRPP_Daily_Spend` | `collect_rakuten_sales_daily.py --update-app` → `collect_rpp_daily.py --update-app` (한 작업에서 순차) |
| 09:25 매일 | Task Scheduler | `MetaJP_ContentTag_Auto` | `python tools\tag_jp_content.py --incremental --write-sheet --sync-jp` |
| 주간 | GH Actions | `meta_jp_weekly.yml` | `python -u tools/meta_jp_daily.py --mode 7d` |

모든 Task Scheduler 작업은 `PYTHONIOENCODING=utf-8` 프리픽스 (Windows cp949 방지),
작업 디렉터리 = SE 레포 루트. `build_jp_meta_deck.py` 는 스케줄 없음 — 발표 전 수동 실행.

---

## 1. collect_rakuten_sales_daily.py — 라쿠텐 일별 매출 → 앱 시드

- **접점**: `meta-app/lib/rakuten-sales-seed.json` 덮어쓰기 (Total ROAS 분자)
- **소스**: RMS Order API `/es/2.0/order/searchOrder` + `getOrder` — `priceTaxIncl × units` 합산,
  취소확정(orderProgress=900) 제외, 주문일 기준
- **CLI**: `--backfill YYYY-MM-DD`(지정일~오늘) / `--days N`(기본 40 — 취소 소급 반영 위해 과거 재수집) /
  `--update-app`(시드 복사; 없으면 로컬 store 만)
- **시드 스키마**: `{updated_at, source, days: {"YYYY-MM-DD": {sales_jpy, orders, units}}}`
- 403 rate limit 시 지수 백오프(2s→4s→8s)

## 2. collect_rpp_daily.py — RPP 일별 광고비 → 앱 시드 + 재배포

- **접점**: `meta-app/lib/rpp-daily-seed.json` 갱신 + **`vercel --prod --yes` 재배포** (timeout 600s)
- **소스**: 라쿠텐 RPP 콘솔 **내부 API** `ad.rms.rakuten.co.jp/rpp/api/reports/downloadPerfFile`
  (POST, periodType=2 일별 집계) — 공식 RMS API 미노출 경로.
  인증 = Playwright 로그인 후 리포트 페이지 fetch 로 `x-xsrf-token` 캡처. CSV 는 cp932,
  프리앰블(검색조건 블록) 스킵 후 「日付」 헤더행부터 파싱. 실적 0일은 CSV 행 자체가 생략 → 0 채움.
- **CLI**: `--backfill YYYY-MM-DD`(31일 단위 분할) / `--days N`(기본 35 — 720h 귀속 소급) / `--update-app`
- **시드 스키마**: `{updated_at, source, days: {날짜: {clicks, spend_jpy, cpc_jpy, ctr_pct,
  sales_12h_jpy, orders_12h, roas_12h_pct, sales_720h_jpy, orders_720h, roas_720h_pct}}}`
- 검증 이력: 2026-06 합계 ¥106,902 = 운영자 제공값 일치

## 3. rms_access_downloader.py — 제품별 월별 접속·주문 → 앱 시드 + 재배포

- **접점**: `meta-app/lib/product-access-seed.json` (당월만 갱신, 과거월 보존) + `vercel --prod --yes`
- **소스**: RMS 商品ページ 내부 API
  `datatool.rms.rakuten.co.jp/access/item/get-item-list/?period=monthly&device=all&startDate=&endDate=`
  (Playwright 로그인 컨텍스트의 request.get) — `salesFormula.visitAll`(접속)/`unitsAll`(주문),
  `item.mngNumber` 로 PPSU/Stainless 분류 (니플 등 제외)
- **CLI**: `--period daily|monthly`(기본 monthly) / `--no-headless` / `--json` / `--update-app`
- **시드 스키마**: `{PPSU: {"YYYY-MM": {access, orders}}, Stainless: {...}}`

## 4. collect_meta_jp_creative.py — 광고 status/creative → DK 적재

- **접점**: DK `gk_raw_meta_ad_creative` (앱의 status **fallback** 소스 — 1차는 Graph 실시간)
- **소스**: Graph v21.0 `/act_x/ads` 배치 50 — id, campaign_id, adset_id, effective_status,
  creative{id, effective_instagram_media_id, instagram_permalink_url, effective_object_story_id}
- **적재**: `https://orbitools.orbiters.co.kr/api/datakeeper/save/` Bearer `DK_SE_CRM_TOKEN`
  (**write:ingest tier 필수** — Basic 인증 거부), 1000행 배치
- **CLI**: 없음
- ⚠️ 2026-07-08 DK perm cutover 로 SE write 토큰이 read 강등 → push 403 상태 이력.
  push 가 죽으면 raw 테이블 stale — 앱이 Graph 우선이라 치명적이진 않으나 복구 대상 (01 문서 §10-2)
- 배경: WONGI 의 raw 크론은 US 계정만 수집 → JP 는 SE 가 자체 적재

## 5. tag_jp_content.py — 콘텐츠 LLM 자동 태깅

- **접점**: 태그 시트(`13S1cST2...`) `Content Tags (auto)` 탭 기록 + `Content Tags (JP)` 탭
  자동 컬럼(km_*, hook_*, evidence, tagged_at) 동기화 — 앱 콘텐츠 탭·성과 티어의 태그 소스
- **입력**: DK `content_posts` (JP region, caption + whisper key_message/hook_text_3s,
  일본어 비율 ≥10% + 제품 명사 노이즈 필터), 택소노미 시트(KM SSOT v2 + WL 훅 taxonomy v2),
  JP 탭의 수동 교정 사례 = few-shot
- **LLM**: `claude-sonnet-4-6` (env `ANTHROPIC_MODEL` override), 배치 5건, 허용 코드 고정
  (S##_F##, HV-##, HC-##), confidence 高/中/低
- **CLI**: `--dry-run` / `--limit N` / `--write-sheet` / `--from-csv`(직전 CSV 재반영, LLM 재실행 X) /
  `--sync-jp` / `--incremental`(미태깅 shortcode 만 — 데일리 잡 모드)
- **수동 태그 불가침**: km_manual/hook_manual 은 건드리지 않음 (앱에서 수동이 자동보다 우선)

## 6. meta_jp_daily.py — 9시 운영 메일 (앱의 메일판)

- **접점**: 앱과 파일 공유 없음. 단 **판정 상수·게이트 로직이 앱과 1:1 동기화 대상**
  (`lib/meta-constants.ts` 헤더 주석: 상수 변경 시 같은 턴에 양쪽 수정).
- **데이터**: DK `meta_ads_daily`(Grosmimi JP) + Graph(status 실시간 `/act_x/ads`, creative permalink 배치)
- **모드**: `--mode 1d`(어제 스냅샷 — 매일 발송) / `7d`(주간 트렌드) / `14d`(진단).
  `--to`(기본 se.heo@orbiters.co.kr) / `--no-send` / `--skip-audit` / `--date YYYY-MM-DD`
- **1d 메일 구성**: 계정 요약(전일比) → 캠페인별 → 알림(CTR<1%·Freq>2.5·CPC 급등) → 광고 TOP5 →
  KPI 카운터 → OFF 권장(D+3 게이트) → Delivery 실패 후보 → 졸업 후보 → BEST/WORST → 운용 조언
- **`_is_live_active()` 게이트**: 후보 빌더 4종(graduation / off / delivery / budget) **내부에 내장** —
  호출자가 깜빡해도 non-ACTIVE 광고가 후보에 못 들어옴. status 전체 조회 실패 시 fail-open.
- **판정 임계값** (앱과 동일): 졸업 CPC≤95·CTR≥8%·CPLPV≤130·D+3 / OFF 게이트 150·5%·190·D+3 /
  delivery 실패 = 14d share<1% AND zero-days≥7, D+14+ (메일판 정의; 앱의 Proven delivery 게이트는
  D+90+&spend<₩5K — 두 시스템의 delivery 정의가 다름에 주의) / 증액 = 참고용 (매출 귀속 미검증으로 발송 보류)
- **발송 전 감사**: rule 기반 + Gemini (score ≥ 80 통과, `GEMINI_API_KEY`)
- **출력**: `.tmp/meta_jp_daily/meta_jp_{mode}_{date}.html` + Gmail 발송(`GMAIL_*` OAuth)
- **실행**: GH Actions (다중 cron + 당일 성공 dedup — yml 동봉). 로컬 스케줄 아님.

## 7. build_jp_meta_deck.py — 주간 발표 덱 (수동)

- **접점**: 앱 데이터 소스 공유 (Graph v21.0 인사이트·ads·breakdowns·creative 배치 / DK content_posts·
  meta_ads_daily 교차검증 / 태그·콜라보 시트). 산출물은 앱 밖 HTML.
- **CLI**: 무인자(collect+render) / `--render`(ssot.json 만 재렌더)
- **출력**: SSOT `C:\Users\orbit\.tmp\jp_meta_deck\ssot.json` +
  HTML `Desktop\s\performance marketing\META ADS 관리용\operations\11_jp_meta_weekly_deck.html`
  (env `JP_DECK_OUT` override)
- 덱 확정 형식: 최근 1달 런칭 풀 4색 디스포지션(파랑 좋음/초록 중간/빨강 나쁨/검정 즉시 OFF),
  BEST3+WORST3 = 생애 CPLPV 순(spend<₩3,000 제외), 3초율·creator type 포함

---

## 8. 시드 파일 쓰기 지점 전수 (SE 레포 grep 결과)

| 파일 | 쓰는 코드 |
|---|---|
| `meta-app/lib/rakuten-sales-seed.json` | collect_rakuten_sales_daily.py (`SEED = ROOT/"meta-app"/"lib"/...`) |
| `meta-app/lib/rpp-daily-seed.json` | collect_rpp_daily.py (+ vercel 배포) |
| `meta-app/lib/product-access-seed.json` | rms_access_downloader.py (+ vercel 배포) |
| (기타) | `.tmp/backfill_*.py` — 일회성 백필 유틸 (프로덕션 스케줄 아님, 패키지 제외) |

## 9. 파이프라인 환경변수 (SE 레포 루트 .env — 앱 .env.local 과 별개)

| 변수 | 소비자 |
|---|---|
| `META_JP_ACCESS_TOKEN` / `META_JP_AD_ACCOUNT_ID` | meta_jp_daily, collect_meta_jp_creative, build_jp_meta_deck |
| `DK_SE_CRM_TOKEN` (write:ingest) | collect_meta_jp_creative |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | tag_jp_content |
| `GEMINI_API_KEY` | meta_jp_daily (발송 전 감사) |
| `GMAIL_OAUTH_CREDENTIALS_PATH` / `GMAIL_TOKEN_PATH` / `GMAIL_SENDER` | meta_jp_daily (GH Actions 는 secrets 로 주입 — yml 참조) |
| RMS 로그인 (Playwright — `RAKUTEN_RMS_LOGIN_PASSWORD` 등) | collect_rpp_daily, rms_access_downloader (do_login 공통) |
| `JP_DECK_OUT` | build_jp_meta_deck 출력 경로 override |

## 10. 이식 시 대체 설계 노트

- 시드 3종(§1~3)은 "파일 + 재배포" 구조 → intelligence 에선 **DB 테이블 + 일반 수집 크론**으로 대체
  (rpp_daily / rakuten_sales_daily / product_access_monthly). 앱 lib/rpp.ts·rakuten-sales.ts·
  product-metrics.ts 의 집계 함수(월별 합산·기간 합산)는 SQL 로 1:1 치환 가능한 단순 로직.
- RPP·商品ページ는 **공식 API 가 없어 Playwright 세션 의존** — 크레덴셜 로테이션(RMS licenseKey,
  로그인 비밀번호) runbook 이 운영 필수.
- collect_meta_jp_creative 는 새 DWH 가 JP raw 를 직접 수집하면 폐기 가능 (US 만 수집하는
  기존 크론의 보완용이었음).
