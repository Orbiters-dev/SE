# Data Keeper Briefing — 팀 공유용

> 이 문서는 다른 프로젝트의 Claude가 Data Keeper 구조를 이해하기 위한 브리핑이다.
> 최종 업데이트: 2026-03-11

---

## 1. Data Keeper란?

ORBI의 **단일 데이터 수집 게이트웨이**. 7개 채널의 광고/판매 데이터를 하루 2회 자동 수집하여 PostgreSQL에 저장한다. 모든 팀 에이전트는 여기서 데이터를 읽는다.

**핵심 원칙: Data Keeper만 쓰기, 나머지는 읽기 전용.**

---

## 2. 수집 채널 (7개)

| # | 채널 | PG 테이블 | API | 계정 |
|---|------|----------|-----|------|
| 1 | Amazon Ads | `gk_amazon_ads_daily` | Reporting v3 (비동기) | 3 프로필 (Orbitool, GROSMIMI, Fleeters) |
| 2 | Amazon Sales | `gk_amazon_sales_daily` | SP-API flat-file | 3 셀러 (Grosmimi USA, Fleeters Inc, Orbitool) |
| 3 | Meta Ads | `gk_meta_ads_daily` | Graph API v18 | 1 ad account |
| 4 | Google Ads | `gk_google_ads_daily` | search_stream (GAQL) | MCC + 하위 계정 |
| 5 | GA4 | `gk_ga4_daily` | Analytics Data API | Property 397533207 |
| 6 | Klaviyo | `gk_klaviyo_daily` | REST API | 1 account |
| 7 | Shopify | `gk_shopify_orders_daily` | Admin REST API | onzenna.myshopify.com |

모든 채널: **35일 lookback**, **upsert** (중복 방지), 하루 2회 수집 (PST 0:00 / 12:00).

---

## 3. 전체 아키텍처

```
GitHub Actions (PST 0:00 / 12:00)
  │
  ▼
data_keeper.py ─── 7채널 순차 수집
  │
  ├──▶ .tmp/datakeeper/*.json     (로컬 캐시, 디버깅용)
  ├──▶ PostgreSQL (gk_* 테이블)    (정식 저장소)
  └──▶ Shared/datakeeper/latest/   (팀 에이전트용 JSON)
         │
         ▼
  data_keeper_client.py ─── 읽기 전용 클라이언트
         │
         ├── 아마존퍼포마 (PPC 분석/실행)
         ├── KPI 월간 리포트 (Excel 생성)
         ├── 커뮤니케이터 (상태 이메일)
         ├── Meta 에이전트 (Meta Ads 분석)
         ├── 골만이 (재무 모델링)
         └── 팀 에이전트 11명 (Shared JSON 읽기)
```

---

## 4. 너(팀 에이전트)의 데이터 접근 규칙

### 데이터가 필요할 때

```
1단계: Shared/datakeeper/latest/manifest.json 확인
       → 채널이 있으면 → 해당 JSON 파일 읽기 (끝)
       → 채널이 없으면 → 2단계

2단계: API 직접 스크래핑 → 시그널 YAML 생성
       → Shared/datakeeper/data_signals/{channel}.yaml 에 저장
       → Data Keeper가 나중에 흡수함
```

### 시그널 YAML 형식

```yaml
channel: tiktok_ads
requested_by: your_project_name
created: 2026-03-11
api_endpoint: https://api.example.com/...
credentials_needed:
  - API_KEY_NAME
sample_data_path: your_folder/.tmp/sample.json
status: pending
```

### 절대 하지 말 것

- ❌ PostgreSQL `gk_*` 테이블에 직접 쓰기
- ❌ `Shared/datakeeper/latest/` 파일 수정
- ❌ Data Keeper가 이미 수집하는 채널을 별도 API 호출로 중복 수집

---

## 5. Shared 폴더 구조

```
Shared/datakeeper/
├── latest/                         ← 읽기 전용 JSON (7채널)
│   ├── manifest.json               ← 채널 목록 + 메타데이터
│   ├── amazon_ads_daily.json
│   ├── amazon_sales_daily.json
│   ├── meta_ads_daily.json
│   ├── google_ads_daily.json
│   ├── ga4_daily.json
│   ├── klaviyo_daily.json
│   └── shopify_orders_daily.json
├── data_signals/                   ← 신규 데이터 요청 드롭존
├── BRIEFING.md                     ← 이 문서
├── CLAUDE.md                       ← 팀 에이전트용 규칙
└── README.md
```

---

## 6. PostgreSQL API (필요한 경우)

Base URL: `https://orbitools.orbiters.co.kr/api/datakeeper`
인증: HTTP Basic (`ORBITOOLS_USER` / `ORBITOOLS_PASS`)

| Method | Endpoint | 용도 |
|--------|----------|------|
| GET | `/query/?table=...&date_from=...&brand=...` | 데이터 조회 |
| GET | `/tables/` | 테이블 목록 + row 수 |
| GET | `/status/` | 최종 수집 시각 |
| POST | `/save/` | Data Keeper 전용 (너는 사용 금지) |

---

## 7. 브랜드 구분

| 브랜드 | 키워드 | 주요 채널 |
|--------|--------|----------|
| Grosmimi | grosmimi, grosm | Amazon, Shopify, Meta |
| CHA&MOM | cha&mom, chamom, orbitool | Amazon, Shopify |
| Naeiae | naeiae, fleeters | Amazon, Shopify, Meta |
| Onzenna | onzenna, zezebaebae | Shopify, Meta |
| Alpremio | alpremio | Shopify |

---

## 8. 주의사항 (반드시 읽을 것)

### Shopify "Amazon" 채널 함정

`shopify_orders_daily`에서 `channel="Amazon"`으로 보이는 주문은 **진짜 Amazon Marketplace 판매가 아니다.**

- **FBA MCF**: Shopify DTC 판매인데 Amazon 물류(WebBee)를 쓰는 것 → 실제로는 D2C
- **Faire**: B2B 도매 주문 → 실제로는 B2B

현재 코드에서 이미 재분류 완료:
- `"faire" in tags` → `channel = "B2B"`
- `"exported to amazon" in tags` → `channel = "D2C"` (물류만 Amazon)
- 진짜 Amazon Marketplace 데이터 = `amazon_sales_daily` (SP-API)

### Grosmimi 가격 변경

- 2025-03-01 이전: 구가격 (GROSMIMI_OLD_PRICES)
- 2025-03-01 이후: 현재 Shopify 가격
- `ref_price = max(ref_price, sell_price)` → 음수 할인 방지

### Amazon Ads 히스토리

- API가 60~90일만 보관
- Naeiae(Fleeters Inc)는 2025년 12월부터만 PG에 존재
- 그 이전 데이터는 물리적으로 불가

### 데이터 새로고침 주기

- 하루 2회 (PST 0:00, 12:00)
- `status` API로 최종 수집 시각 확인 가능
- 14시간 이내면 "fresh", 이후면 "stale"

---

## 9. 현재 운영 중인 에이전트 생태계

```
┌─────────────────────────────────────────────────┐
│                 Data Keeper (수집)                │
│  data_keeper.py → PG → Shared/datakeeper/       │
└──────────────────────┬──────────────────────────┘
                       │ (읽기)
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌──────────┐   ┌──────────┐   ┌──────────────┐
│아마존퍼포마│   │메타에이전트│   │ KPI 월간리포트│
│ PPC 실행  │   │ Meta 분석 │   │ Excel 생성   │
└──────────┘   └──────────┘   └──────────────┘
       │                               │
       ▼                               ▼
┌──────────┐                   ┌──────────────┐
│커뮤니케이터│                   │   골만이      │
│상태 이메일 │                   │ 재무 모델링   │
└──────────┘                   └──────────────┘
```

| 에이전트 | 역할 | 사용 채널 |
|---------|------|----------|
| 아마존퍼포마 | Amazon PPC 분석/입찰/예산 실행 | amazon_ads, amazon_sales |
| 메타 에이전트 | Meta Ads 분석 (Breakdown Effect 주의) | meta_ads |
| KPI 월간 리포트 | 할인율/광고비/시딩비용 Excel | 전 채널 |
| 커뮤니케이터 | 12시간 상태 이메일 | /status/ endpoint |
| 골만이 | DCF, Comps, 피치덱 등 IB 업무 | 전 채널 (매출/비용) |
| UI테스터 | Shopify UI + 인플루언서 파이프라인 | shopify_orders |

---

## 10. 요약

1. **데이터 필요하면** → `Shared/datakeeper/latest/manifest.json` 먼저 확인
2. **있으면** → 해당 JSON 읽기
3. **없으면** → 직접 스크래핑 + `data_signals/`에 YAML 드롭
4. **PG 직접 쓰기 절대 금지**
5. **Shopify "Amazon" ≠ 진짜 Amazon** 항상 기억

---

*이 문서에 대한 질문은 WJ Test1 프로젝트의 Data Keeper 스킬을 참조하세요.*
*파일: `.claude/skills/data-keeper/SKILL.md`*
