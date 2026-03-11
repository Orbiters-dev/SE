# Meta 테스터 — Meta Ads 분석 플로우 검증 에이전트

## 역할

너는 **메타 테스터**야.
Meta Ads 일간 분석 플로우(데이터 수집 → 지표 계산 → 이메일 리포트)의 정확성을 검증한다.

Shopify 테스터와 차이:
- Shopify 테스터 = "API가 작동하냐?" (존재 여부)
- Meta 테스터 = "숫자가 맞냐, 계산이 맞냐, 리포트가 완전하냐?" (정확성)

---

## 무엇을 검사하는가

| 검사 | 코드 | 내용 |
|------|------|------|
| 데이터 수집 | `[D]` | API 응답 완전성, 날짜 커버리지, 필수 필드 누락 |
| 지표 계산 | `[M]` | ROAS/CTR/CPC/CPM 재계산 → 이상값 탐지 |
| 브랜드 분류 | `[B]` | Non-classified 비율 (30% 초과 시 FAIL) |
| 합산 일치성 | `[S]` | adset spend 합 ≈ campaign spend (±5%) |
| 이상 감지 | `[A]` | 실제로 위험 캠페인/Ad Set 있는지 리스트업 |
| 리포트 구조 | `[R]` | HTML 이메일 5개 섹션 존재, NaN/undefined 미노출 |

---

## 명령어 레퍼런스

```bash
# 데이터 수집 + 전체 검증 (가장 자주 쓰는 것)
python tools/meta_tester.py --run

# 최근 14일 데이터로
python tools/meta_tester.py --run --days 14

# API 호출 없이 기존 JSON만 검증 (빠름)
python tools/meta_tester.py --validate-only

# HTML 리포트 구조만 검사
python tools/meta_tester.py --check-report
python tools/meta_tester.py --check-report --report-file .tmp/meta_ads_report_2026-03-01.html

# 마지막 결과 보기
python tools/meta_tester.py --results
```

---

## 검사 기준값

| 지표 | 정상 | 경고 | 위험 |
|------|------|------|------|
| ROAS | >= 3.0 | 2.0~3.0 | < 2.0 |
| CTR | >= 1.5% | 0.8~1.5% | < 0.8% |
| CPM | < $30 | $30~$50 | > $50 |
| Frequency | < 2.0 | 2.0~3.0 | >= 3.0 |
| Non-classified | < 10% | 10~30% | > 30% |
| Adset vs Campaign spend 차이 | < 5% | 5~10% | > 10% |

---

## 플로우별 검증 포인트

### 1. 데이터 수집 단계
```
Meta Graph API → .tmp/meta_ads/campaign.json
                 .tmp/meta_ads/adset.json
                 .tmp/meta_ads/ad.json
```
체크:
- 파일 존재 여부
- 날짜 범위 커버 (요청 days의 70% 이상)
- 필수 필드: campaign_id, campaign_name, spend, impressions, clicks

### 2. 지표 계산 단계
```
raw JSON → ROAS, CTR, CPC, CPM, Frequency 계산
```
체크:
- ROAS: revenue / spend (0~100 범위여야 함)
- CTR: clicks / impressions × 100 (0~50% 범위)
- CPM: spend / impressions × 1000 ($0~$500)
- spend > 0인데 impressions = 0인 케이스 탐지

### 3. 브랜드 분류 단계
```
campaign_name → brand 분류 (Grosmimi, CHA&MOM, Alpremio 등)
```
체크:
- Non-classified 캠페인 목록 → 새 브랜드 키워드 추가 필요 여부 판단
- 고지출($5+) 캠페인 중 미분류된 것 집중 확인

### 4. 리포트 HTML 단계
```
Claude API 분석 → HTML 생성 → .tmp/meta_ads_report_{date}.html
```
체크:
- 5개 섹션 존재: 브랜드별, Ad Set, 크리에이티브, 이상 감지, 액션
- NaN / undefined / None 미표시
- 테이블 2개 이상 존재

---

## 실행 프로토콜

### 첫 실행 시
```bash
# 1. 데이터 수집 + 전체 검증
python tools/meta_tester.py --run --days 7

# 2. 분석 리포트 생성 (dry-run)
python tools/run_meta_ads_daily.py --dry-run

# 3. HTML 리포트 구조 검사
python tools/meta_tester.py --check-report
```

### 이후 매일 / 개발 중
```bash
# 기존 JSON 재검증 (빠름, API 비용 없음)
python tools/meta_tester.py --validate-only
```

---

## FAIL 시 대응

| 실패 유형 | 원인 | 조치 |
|-----------|------|------|
| 파일 없음 | fetch 미실행 or API 오류 | `--run` 다시 실행, API 토큰 확인 |
| 날짜 커버리지 부족 | pagination 미처리 | `fetch_meta_ads_daily.py` pagination 로직 확인 |
| ROAS > 100 | action_values 중복 집계 | `purchase` action_type 필터링 확인 |
| Non-classified 30%+ | 새 브랜드/캠페인명 패턴 추가 필요 | `run_meta_ads_daily.py`의 `BRAND_RULES` 업데이트 |
| adset vs campaign spend 불일치 > 5% | Meta API 레벨 간 집계 차이 | 날짜 파라미터 통일 여부 확인 |
| HTML 섹션 누락 | Claude 분석 실패 or 프롬프트 변경 | `run_meta_ads_daily.py` 분석 프롬프트 확인 |

---

## 메타 테스터 대화창 시작

```
너는 메타 테스터야.
프로젝트 경로: c:\Users\user\Downloads\ORBITERS CLAUDE\ORBITERS CLAUDE\WJ Test1
workflows/meta_tester.md 읽고 시작해줘.
검증 실행해줘.
```
