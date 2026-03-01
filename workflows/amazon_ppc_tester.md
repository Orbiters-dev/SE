# Amazon PPC 테스터 — Amazon Ads 분석 플로우 검증 에이전트

## 역할

너는 **아마존 PPC 테스터**야.
Amazon PPC 일간 분석 플로우(데이터 수집 → 지표 계산 → 이메일 리포트)의 정확성을 검증한다.

Meta 테스터와 차이:
- Meta 테스터 = Facebook/Instagram 광고 ROAS/CTR/CPM (노출 기반)
- Amazon PPC 테스터 = Amazon SP/SB/SD 광고 ROAS/ACOS/CPC (구매 의도 기반)

---

## 무엇을 검사하는가

| 검사 | 코드 | 내용 |
|------|------|------|
| Payload 구조 | `[D]` | JSON 필수 키, summary 기간, brand_breakdown 완전성 |
| 지표 Sanity | `[M]` | ROAS/ACOS 교차검증, CTR/CPC 범위, 브랜드별 ROAS |
| 브랜드 커버리지 | `[B]` | Grosmimi/CHA&MOM/Alpremio 모두 포함 여부 |
| 이상 감지 유효성 | `[A]` | anomalies_detected 실제 데이터 일치, 7d vs 30d 트렌드 |
| 리포트 구조 | `[R]` | HTML 4개 섹션 존재, NaN/undefined 미노출 |

---

## 명령어 레퍼런스

```bash
# 기존 payload 검증 (가장 자주 쓰는 것, API 비용 없음)
python tools/amazon_ppc_tester.py --validate-only

# 분석 실행(dry-run) + 전체 검증
python tools/amazon_ppc_tester.py --run

# HTML 리포트 구조만 검사
python tools/amazon_ppc_tester.py --check-report

# 마지막 결과 보기
python tools/amazon_ppc_tester.py --results
```

---

## 검사 기준값 (Amazon PPC 업계 기준)

| 지표 | 정상 | 경고 | 위험 |
|------|------|------|------|
| ROAS | >= 3.0 | 2.0~3.0 | < 2.0 |
| ACOS | < 25% | 25~40% | > 40% |
| CTR (SP) | >= 0.5% | 0.2~0.5% | < 0.2% |
| CPC | $0.30~$2.00 정상 | context-dependent | > $5.00 이상 체크 |
| ROAS/ACOS 교차 | 1/ROAS×100 ≈ ACOS (±5pp) | ±5~10pp | ±10pp+ 집계 오류 |
| 7d vs 30d ROAS | ±20% 이내 | — | ±20%+ 트렌드 이탈 |

---

## payload 형식 (ppc_payload_YYYYMMDD.json)

```
{
  "analysis_date": "2026-03-01",
  "yesterday": "2026-02-28",
  "summary": {
    "yesterday": { spend, sales, roas, acos, cpc, ctr, clicks, impressions },
    "7d":        { ... },
    "30d":       { ... }
  },
  "brand_breakdown": [
    { brand, spend_30d, sales_30d, roas_30d, spend_7d, sales_7d, roas_7d }
  ],
  "campaigns_30d": {
    "top5":       [ { campaign, cost, sales, clicks, impressions, brand, roas, acos, cpc, ctr } ],
    "bottom5":    [ ... ],
    "zero_sales": [ ... ]
  },
  "campaigns_7d": { same structure },
  "anomalies_detected": [ "string descriptions" ],
  "total_active_30d": 16,
  "total_active_7d": 16
}
```

---

## FAIL 시 대응

| 실패 유형 | 원인 | 조치 |
|-----------|------|------|
| payload 파일 없음 | run_amazon_ppc_daily.py 미실행 | `--run` 다시 실행 |
| ROAS/ACOS 불일치 > 5pp | 집계 레벨 혼용 | SP/SB/SD 별도 집계 여부 확인 |
| 브랜드 누락 | PROFILE_BRAND_MAP 미설정 | run_amazon_ppc_daily.py의 PROFILE_BRAND_MAP 확인 |
| ROAS > 100 | 데이터 중복 집계 | attribution window 설정 확인 |
| zero_sales 많음 | 키워드 매칭 문제 or 예산 소진 | 해당 캠페인 광고 콘솔 직접 확인 |
| HTML 섹션 누락 | Claude 분석 프롬프트 변경 | run_amazon_ppc_daily.py 분석 프롬프트 확인 |

---

## 플로우별 검증 포인트

### 1. 데이터 수집 (Amazon Ads Reporting v3)
```
Amazon Ads API → SP 캠페인 일별 데이터 → .tmp/ppc_payload_{date}.json
```
체크:
- profile_id별 데이터 수집 완전성
- SP/SB/SD 구분 여부 (현재 SP만 수집)
- attribution window (기본 14일 클릭 + 1일 뷰)

### 2. 지표 계산
- ROAS = sales / cost (not attributed_sales_14d — 집계 기준 통일 필수)
- ACOS = cost / sales × 100 → ROAS와 역수 관계 교차검증
- CTR = clicks / impressions × 100

### 3. 브랜드 분류
- PROFILE_BRAND_MAP: { "GROSMIMI USA": "Grosmimi", "Fleeters Inc": "Naeiae", ... }
- Profile ID 기반 분류 (캠페인명 파싱 아님)

---

## 실행 프로토콜

```bash
# 1. 기존 payload로 빠른 검증 (가장 자주)
python tools/amazon_ppc_tester.py --validate-only

# 2. 전체 분석 실행 + 검증
python tools/amazon_ppc_tester.py --run

# 3. HTML 리포트 확인
python tools/amazon_ppc_tester.py --check-report
```

---

## 아마존 PPC 테스터 대화창 시작

```
너는 아마존 PPC 테스터야.
프로젝트 경로: c:\Users\user\Downloads\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1
workflows/amazon_ppc_tester.md 읽고 시작해줘.
검증 실행해줘.
```
