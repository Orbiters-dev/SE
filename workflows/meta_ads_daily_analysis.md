# Meta Ads 일간/주간 분석 워크플로우

## 목적
Meta Graph API에서 Facebook/Instagram 광고 성과 데이터를 가져와
캠페인 → Ad Set → Ad 레벨로 드릴다운 분석 후 이메일로 발송한다.

## 발송 정보
- **보내는 주소**: orbiters11@gmail.com
- **받는 주소**: wj.choi@orbiters.co.kr
- **발송 주기**: 매일 (전날 데이터 기준) 또는 주간 (월요일, 지난 7일 기준)

---

## Agent 시스템 프롬프트 (Meta Ads Analyst)

```
당신은 10년 경력의 Meta(Facebook/Instagram) 광고 전문 퍼포먼스 마케터입니다.
이커머스 DTC 브랜드의 유료 광고를 운영한 깊은 경험을 보유하고 있으며,
크리에이티브 최적화, 오디언스 세그먼테이션, ROAS 극대화에 특화되어 있습니다.
데이터 기반으로 정확하고 실행 가능한 인사이트를 제공합니다.

분석 원칙:
1. 숫자만 나열하지 않는다 — 반드시 의미와 액션을 함께 제시한다
2. ROAS 기준: 3.0 이상 우수 / 2.0~3.0 보통 / 2.0 미만 위험
3. CTR 기준: 1.5% 이상 우수 / 0.8~1.5% 보통 / 0.8% 미만 위험 (크리에이티브 피로 신호)
4. CPM 기준: 높을수록 오디언스 포화 또는 경쟁 심화 — 전주 대비 20% 이상 상승 시 주목
5. Frequency 기준: 3.0 이상이면 오디언스 번아웃 위험 — 새 크리에이티브 또는 오디언스 확장 필요
6. 전날 대비, 지난주 동요일 대비, 지난달 대비 3가지 맥락에서 판단한다
7. 브랜드별(Grosmimi, CHA&MOM, Alpremio 등)로 구분하여 분석한다
8. 크리에이티브 레벨(Ad)에서 이상 징후를 포착하고 교체/스케일 여부를 판단한다
9. 결론은 항상 "이번 주 해야 할 액션 3가지"로 마무리한다
```

---

## 워크플로우 단계

### Step 1: Meta Ads 데이터 수집 (3개 레벨)

```bash
# 캠페인 레벨 (전체 요약용)
python tools/no_polar/fetch_meta_ads_daily.py --level campaign --days 60

# Ad Set 레벨 (오디언스/타겟팅 분석용)
python tools/no_polar/fetch_meta_ads_daily.py --level adset --days 30

# Ad 레벨 (크리에이티브 성과 분석용)
python tools/no_polar/fetch_meta_ads_daily.py --level ad --days 30
```

출력: `.tmp/meta_ads/campaign.json`, `.tmp/meta_ads/adset.json`, `.tmp/meta_ads/ad.json`

---

### Step 2: 지표 계산

각 레벨에서 아래 지표를 계산한다:

| 지표 | 계산식 | 단위 |
|------|--------|------|
| ROAS | purchases_conversion_value / spend | 배수 |
| CTR | clicks / impressions × 100 | % |
| CPC | spend / clicks | $ |
| CPM | spend / impressions × 1000 | $ |
| Frequency | impressions / reach | 횟수 |
| Purchase Rate | purchases / clicks × 100 | % |
| CPA | spend / purchases | $ (구매당 비용) |

---

### Step 3: 분석 수행

#### A. 전체 요약 (캠페인 레벨)

| 지표 | 어제 | 7일 평균 | 30일 평균 | 전월 대비 |
|------|------|----------|-----------|-----------|
| 총 광고비 | | | | |
| 총 광고 매출 | | | | |
| ROAS | | | | |
| CTR | | | | |
| CPC | | | | |
| CPM | | | | |
| Frequency | | | | |

#### B. 브랜드별 성과 (캠페인명 파싱)

캠페인명에서 브랜드 분류 키워드:
- **Grosmimi**: grosmimi, grosm, gm, ppsu, stainless, straw
- **CHA&MOM**: cha&mom, cha_mom, cm, skincare, lotion, hair wash
- **Alpremio**: alpremio
- **Easy Shower**: easy shower, shower stand
- **Hattung**: hattung
- **Beemymagic**: beemymagic, beemy
- **Comme Moi**: commemoi, comme moi, commemo
- **BabyRabbit**: babyrabbit, baby rabbit
- **Naeiae**: naeiae, rice snack, pop rice
- **RIDE & GO**: ride & go, ridego
- **BambooeBebe**: bamboobebe
- **Non-classified**: zezebaebae 단독, dsh (멀티브랜드 → Ad Set명으로 재분류)

각 브랜드별: 광고비 / 매출 / ROAS / CTR / CPM / 전월 대비 증감

#### C. Ad Set 레벨 — 오디언스 분석

- **Frequency 위험 Ad Set**: Frequency ≥ 3.0 → 오디언스 번아웃 경고
- **CPM 급등 Ad Set**: 전주 대비 CPM 20% 이상 상승 → 오디언스 포화 또는 경쟁 심화
- **ROAS 상위 5개 Ad Set**: 예산 증액 후보
- **ROAS 하위 5개 Ad Set**: 일시 중단 또는 타겟 재설정 후보

#### D. Ad 레벨 — D+N 크리에이티브 분석 (최근 7일 기준)

**Top Performer** (최근 7일 기준, D+14 이상):
- CVR 캠페인: 7일 ROAS >= 3.0
- Traffic 캠페인: 7일 CTR >= 1.5%
- 조건: 누적 지출 $50+, 7일 지출 $10+

**Worst Performer** (최근 7일 기준, D+14 이상):
- CVR/Other 캠페인: 7일 ROAS < 2.0
- Traffic 캠페인: 7일 CTR < 1.0%
- 조건: 누적 지출 $100+, 7일 지출 $10+

**캠페인 타입 분류 규칙**:
1. Meta API objective 기반 (OUTCOME_SALES → cvr, OUTCOME_TRAFFIC → traffic)
2. 캠페인명에 "CVR" 포함 시 무조건 cvr로 강제 (user naming convention 우선)
3. WL/AMZ/Amazon 시그널 → traffic으로 override (단, "CVR" 명시 캠페인은 제외)

- **지출 있는데 구매 0인 Ad**: 즉시 점검 필요

#### E. 이상 감지 (자동)

전날 대비 변화가 큰 항목:
- ROAS 20% 이상 급락한 캠페인/Ad Set
- 광고비가 갑자기 2배 이상 증가한 캠페인
- CTR이 0.5% 미만으로 떨어진 Ad (크리에이티브 피로)
- Frequency ≥ 4.0인 Ad Set (즉시 새 크리에이티브 필요)
- 클릭은 있는데 구매 전환 0인 Ad

#### F. 개선 전략 (이번 주 액션 3가지)

데이터 기반으로 구체적인 액션 3가지 제시:
예시:
- "Grosmimi PPSU 캠페인 일예산 20% 증액 (ROAS 4.2, CTR 2.1%로 효율 우수)"
- "CHA&MOM Skincare Ad Set 오디언스 확장 (Frequency 3.8 → 번아웃 위험)"
- "Alpremio 광고 소재 3개 교체 필요 (CTR 0.4%, 7일 ROAS 0.9)"

---

### Step 4: HTML 이메일 생성

```html
제목: [Meta Ads] 일간 리포트 — {날짜} | ROAS {전체ROAS} | CTR {전체CTR}%

본문:
- 헤더: 날짜, 전체 요약 수치
- 섹션 1: 브랜드별 성과 테이블
- 섹션 2: Ad Set 오디언스 이상 감지 (Frequency/CPM)
- 섹션 3: 크리에이티브 상위/하위 Ad
- 섹션 4: 이상 감지 알림 (빨간 배경)
- 섹션 5: 이번 주 액션 3가지 (강조 박스)
- 푸터: 분석 기준 날짜 및 데이터 출처 (Meta Graph API)
```

HTML 스타일:
- 배경: 흰색, 폰트: sans-serif
- 테이블: 헤더 #1877F2 (Meta 파란색), 행 교차 #f9f9f9
- 위험 수치: 빨간색(#d32f2f) / 우수 수치: 초록색(#2e7d32)
- 모바일 반응형

---

### Step 5: 이메일 발송

```bash
python tools/send_gmail.py \
  --to wj.choi@orbiters.co.kr \
  --subject "[Meta Ads] 일간 리포트 — {날짜}" \
  --body-file .tmp/meta_ads_report_{날짜}.html
```

---

## 실행 명령

```bash
# 기본 실행 (어제 데이터 분석 → 이메일 발송)
python tools/run_meta_ads_daily.py

# 이메일 발송 없이 HTML만 저장 (테스트)
python tools/run_meta_ads_daily.py --dry-run

# 주간 리포트 (지난 7일)
python tools/run_meta_ads_daily.py --weekly
```

Claude에게:
```
"어제 Meta 광고 분석해서 wj.choi@orbiters.co.kr로 이메일 보내줘"
"지난주 Meta Ads 주간 리포트 만들어줘"
```

---

## 실행 흐름

```
Step 1: Meta Graph API → campaign/adset/ad 레벨 일별 데이터 수집 (최근 60일)
Step 2: 지표 계산 (ROAS, CTR, CPC, CPM, Frequency) + 브랜드 분류 + 이상 감지
Step 3: Claude API (claude-sonnet-4-6) → Meta 전문가 JSON 분석
Step 4: HTML 이메일 생성 → .tmp/meta_ads_report_{날짜}.html
Step 5: tools/send_gmail.py → 이메일 발송
```

---

## 초기 설정

### .env 필요 항목
```
META_ACCESS_TOKEN=...
META_AD_ACCOUNT_ID=act_...
ANTHROPIC_API_KEY=...
GMAIL_SENDER=orbiters11@gmail.com
GMAIL_TOKEN_PATH=credentials/gmail_token.json
META_REPORT_RECIPIENT=wj.choi@orbiters.co.kr
```

### 패키지
```bash
pip install requests python-dateutil anthropic google-auth-oauthlib google-api-python-client
```

---

## 알려진 한계 및 주의사항

1. **Frequency는 reach 필드 필요** — 현재 `fetch_meta_ads_monthly.py`는 reach 미수집 → 툴 확장 필요
2. **Ad 레벨 데이터량** — Ad 수가 많을 경우 API 응답 느릴 수 있음 (pagination 처리 필수)
3. **구매 전환 추적** — Meta Pixel 설정 누락 시 `purchases_conversion_value` = 0 오류 가능
4. **데이터 지연** — Meta Insights API는 약 48시간 지연 발생 가능 (특히 전환 데이터)
5. **iOS ATT 제한** — iOS 14+ 이후 전환 추적 부정확 → reported ROAS가 실제보다 낮을 수 있음

---

## 향후 개선
- 크리에이티브 이미지 썸네일 이메일 첨부
- Notion 자동 저장 연동
- 주간/월간 트렌드 차트 생성
- 경쟁사 CPM 벤치마크 비교
