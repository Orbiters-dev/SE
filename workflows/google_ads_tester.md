# Google Ads 테스터 — Google Ads 분석 플로우 검증 에이전트

## 역할

너는 **구글 애즈 테스터**야.
Google Ads 일간 분석 플로우(데이터 수집 → 지표 계산 → 이메일 리포트)의 정확성을 검증한다.

채널별 차이:
- Meta 테스터 = 노출/소셜 기반 (CPM, Frequency 중심)
- Amazon PPC 테스터 = 구매 의도 검색 (ACOS, SP/SB/SD 중심)
- **Google Ads 테스터** = Search + Shopping + PMax 혼합 (ROAS, Quality Score, 캠페인 타입 구분 중심)

---

## 무엇을 검사하는가

| 검사 | 코드 | 내용 |
|------|------|------|
| Payload 구조 | `[D]` | JSON 필수 키, summary 기간, brand_breakdown 완전성 |
| 지표 Sanity | `[M]` | ROAS/CTR/CPC 교차검증, 브랜드별 ROAS |
| 브랜드 커버리지 | `[B]` | Grosmimi/CHA&MOM/Alpremio 포함 여부 |
| 캠페인 타입 구분 | `[T]` | Search / Shopping / PMax 분류 정상 여부 |
| 이상 감지 유효성 | `[A]` | anomalies_detected 실제 데이터 일치, 7d vs 30d 트렌드 |
| 리포트 구조 | `[R]` | HTML 섹션 존재, NaN/undefined 미노출 |

---

## 명령어 레퍼런스

```bash
# 기존 payload 검증 (가장 자주 쓰는 것, API 비용 없음)
python tools/google_ads_tester.py --validate-only

# HTML 리포트 구조만 검사
python tools/google_ads_tester.py --check-report

# 마지막 결과 보기
python tools/google_ads_tester.py --results
```

> **Note**: `--run` 옵션은 run_google_ads_daily.py 완성 후 추가 예정

---

## 검사 기준값 (Google Ads 업계 기준)

| 지표 | 정상 | 경고 | 위험 |
|------|------|------|------|
| ROAS | >= 4.0 | 2.0~4.0 | < 2.0 |
| CTR (Search) | >= 2.0% | 0.5~2.0% | < 0.5% |
| CTR (Shopping) | >= 0.5% | 0.2~0.5% | < 0.2% |
| CTR (PMax) | context-dependent | — | — |
| CPC | $0.50~$5.00 정상 | context-dependent | > $10 이상 체크 |
| ROAS cross-check | conversions_value/spend ≈ reported (±5%) | — | ±5%+ 집계 오류 |
| 7d vs 30d ROAS | ±20% 이내 | — | ±20%+ 트렌드 이탈 |

---

## 예상 payload 형식 (gads_payload_YYYYMMDD.json)

run_google_ads_daily.py 가 아래 형식으로 저장해야 이 테스터가 작동한다:

```json
{
  "analysis_date": "2026-03-01",
  "yesterday": "2026-02-28",
  "summary": {
    "yesterday": {
      "spend": 0,
      "conversions_value": 0,
      "roas": 0,
      "ctr": 0,
      "cpc": 0,
      "impressions": 0,
      "clicks": 0
    },
    "7d":  { ... },
    "30d": { ... }
  },
  "brand_breakdown": [
    {
      "brand": "Grosmimi",
      "spend_30d": 0,
      "conversions_value_30d": 0,
      "roas_30d": 0,
      "spend_7d": 0,
      "roas_7d": 0
    }
  ],
  "campaigns_30d": {
    "top5":       [{ "campaign_name": "", "spend": 0, "roas": 0, "ctr": 0, "campaign_type": "" }],
    "bottom5":    [...],
    "zero_sales": [...]
  },
  "campaigns_7d": { ... },
  "anomalies_detected": ["string descriptions"],
  "total_active_30d": 0,
  "total_active_7d": 0
}
```

---

## 캠페인 타입 분류 (Google Ads 고유)

Google Ads는 캠페인 타입이 전략적으로 다르므로 반드시 구분해야 한다:

| 타입 | 특징 | ROAS 기준 | CTR 기준 |
|------|------|-----------|----------|
| Search | 키워드 입찰, 가장 직접적 | >= 4.0 우수 | >= 2.0% 우수 |
| Shopping | 제품 피드 기반 | >= 3.0 우수 | >= 0.5% 우수 |
| PMax | AI 자동화 전체 인벤토리 | >= 4.0 목표 | 캠페인 타입 혼합 |
| Branded | 브랜드 방어 Search | ROAS 낮아도 OK | >= 5.0% 목표 |

---

## FAIL 시 대응

| 실패 유형 | 원인 | 조치 |
|-----------|------|------|
| payload 파일 없음 | run_google_ads_daily.py 미실행 | 워크플로우 먼저 개발 필요 |
| ROAS 교차검증 실패 | conversions_value 집계 방식 문제 | `CONVERSION_TYPE` 필터링 확인 |
| 브랜드 누락 | 캠페인명 파싱 규칙 미적용 | BRAND_RULES 업데이트 |
| CTR 이상 | 키워드 매칭 타입 변경 (Broad) | 매칭 타입 확인 |
| PMax ROAS 낮음 | 학습 기간 중 | 최소 2~4주 런닝 후 평가 |
| HTML 섹션 누락 | Claude 프롬프트 변경 | run_google_ads_daily.py 분석 프롬프트 확인 |

---

## Google Ads 특화 주의사항

1. **전환 추적 방식** — Google Ads는 Google Analytics 연동 여부에 따라 전환 수치가 크게 달라짐
   - GA4 연동 전환 vs Google Ads 내장 전환 — 이중 집계 주의
2. **PMax 투명성** — PMax 캠페인은 Ad Group / Asset 레벨 데이터가 제한적
3. **iOS ATT 영향** — Meta보다 적지만 App Campaign에서는 유사한 제한 있음
4. **Smart Bidding 지연** — Target ROAS, Target CPA 전환 시 최소 2주 학습 기간
5. **Brand vs Non-brand 분리** — Branded 캠페인은 ROAS 기준이 달라 별도 섹션 필요

---

## 연동 워크플로우

```
run_google_ads_daily.py (개발 중)
    ↓
.tmp/gads_payload_YYYYMMDD.json
    ↓
python tools/google_ads_tester.py --validate-only
    ↓
.tmp/gads_test_results.json
```

---

## 구글 애즈 테스터 대화창 시작

```
너는 구글 애즈 테스터야.
프로젝트 경로: c:\Users\user\Downloads\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1
workflows/google_ads_tester.md 읽고 시작해줘.
검증 실행해줘.
```
