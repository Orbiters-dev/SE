# Amazon PPC 일간 분석 워크플로우

## 목적
Polar Analytics MCP에서 Amazon Ads 캠페인 데이터를 가져와
PPC 성과를 분석하고 개선 전략을 이메일로 발송한다.

## 발송 정보
- **보내는 주소**: orbiters11@gmail.com
- **받는 주소**: wj.choi@orbiters.co.kr
- **발송 주기**: 매일 (전날 데이터 기준)

---

## Agent 시스템 프롬프트 (PPC Analyst)

```
당신은 10년 경력의 아마존 PPC 전문 마케터입니다.
아마존 스폰서드 광고(SP/SB/SD)에 대한 깊은 이해를 갖고 있으며,
데이터 기반으로 정확하고 실행 가능한 인사이트를 제공합니다.

분석 원칙:
1. 숫자만 나열하지 않는다 — 반드시 의미와 액션을 함께 제시한다
2. ROAS 기준: 3.0 이상 우수 / 2.0~3.0 보통 / 2.0 미만 위험
3. ACOS 기준: 15% 미만 효율적 / 15~25% 보통 / 25% 초과 비효율
4. 전날 대비, 지난주 동요일 대비, 지난달 대비 3가지 맥락에서 판단한다
5. 브랜드별(Grosmimi, CHA&MOM, Alpremio 등)로 구분하여 분석한다
6. 결론은 항상 "이번 주 해야 할 액션 3가지"로 마무리한다
```

---

## 워크플로우 단계

### Step 1: Polar MCP 초기화
```
get_context → conversation_id 확보
```

### Step 2: Amazon Ads 데이터 조회

**기간 설정**:
- 분석 기간: 최근 30일 (전날 기준)
- 비교 기간: 그 이전 30일

**쿼리**:
```
metrics: amazonads cost, attributed_sales, clicks, impressions
dimensions: campaign
granularity: day
date_range: 최근 30일
```

### Step 3: PPC 분석 수행

아래 항목을 순서대로 분석한다:

#### A. 전체 요약
| 지표 | 어제 | 7일 평균 | 30일 평균 | 전월 대비 |
|------|------|----------|-----------|-----------|
| 총 광고비 | | | | |
| 총 광고 매출 | | | | |
| ROAS | | | | |
| ACOS | | | | |
| CPC | | | | |
| CTR | | | | |

#### B. 브랜드별 성과
캠페인명 파싱으로 브랜드 분류:
- Grosmimi (ppsu, grosmimi, gm 키워드)
- CHA&MOM (cha&mom, cm 키워드)
- Alpremio
- Naeiae
- Easy Shower
- 기타

각 브랜드별: 광고비 / 매출 / ROAS / 전월 대비 증감

#### C. 성과 상위/하위 캠페인
- ROAS 상위 5개 캠페인 (잘 되는 것)
- ROAS 하위 5개 캠페인 (문제 있는 것)
- 광고비 대비 매출 0인 캠페인 (즉시 점검 필요)

#### D. 트렌드 이상 감지
전날 대비 변화가 큰 항목 자동 감지:
- ROAS 20% 이상 급락한 캠페인
- 광고비가 갑자기 2배 이상 증가한 캠페인
- 클릭은 있는데 매출이 0인 캠페인

#### E. 개선 전략 (이번 주 액션 3가지)
데이터 기반으로 구체적인 액션 3가지 제시:
예시:
- "Grosmimi PPSU 캠페인 일예산 20% 증액 (ROAS 4.2로 효율 우수)"
- "CHA&MOM Skincare 캠페인 일시 중단 검토 (7일 ROAS 0.8)"
- "Alpremio 캠페인 입찰가 15% 인하 (ACOS 38%로 목표치 초과)"

---

### Step 4: HTML 이메일 생성

이메일 형식:
```html
제목: [Amazon PPC] 일간 리포트 — {날짜} | ROAS {전체ROAS} | ACOS {전체ACOS}%

본문:
- 헤더: 날짜, 전체 요약 수치
- 섹션 1: 브랜드별 성과 테이블
- 섹션 2: 주목할 캠페인 (상위/하위)
- 섹션 3: 이상 감지 알림 (빨간 배경)
- 섹션 4: 이번 주 액션 3가지 (강조 박스)
- 푸터: 분석 기준 날짜 및 데이터 출처(Polar Analytics)
```

HTML 스타일:
- 배경: 흰색, 폰트: sans-serif
- 테이블: 헤더 #232F3E (아마존 색상), 행 교차 #f9f9f9
- 위험 수치: 빨간색(#d32f2f) / 우수 수치: 초록색(#2e7d32)
- 모바일 반응형

---

### Step 5: 이메일 발송

```bash
python tools/send_gmail.py \
  --to wj.choi@orbiters.co.kr \
  --subject "[Amazon PPC] 일간 리포트 — {날짜}" \
  --body-file .tmp/ppc_report_{날짜}.html
```

---

## 실행 명령

```bash
# 기본 실행 (어제 데이터 분석 → wj.choi@orbiters.co.kr 발송)
python tools/run_amazon_ppc_daily.py

# 이메일 발송 없이 HTML만 저장 (테스트)
python tools/run_amazon_ppc_daily.py --dry-run

# 수신자 변경
python tools/run_amazon_ppc_daily.py --to other@example.com
```

Claude에게:
```
"어제 아마존 PPC 분석해서 wj.choi@orbiters.co.kr로 이메일 보내줘"
```

---

## 실행 흐름 (tools/run_amazon_ppc_daily.py)

```
Step 1: Amazon Ads API → 최근 60일 일별 SP 캠페인 데이터 수집
Step 2: 지표 계산 (ROAS, ACOS, CPC, CTR) + 브랜드 분류 + 이상 감지
Step 3: Claude API (claude-sonnet-4-6) → PPC 전문가 JSON 분석
Step 4: HTML 이메일 생성 → .tmp/ppc_report_{날짜}.html
Step 5: tools/send_gmail.py → 이메일 발송
```

---

## 초기 설정 (최초 1회)

### 1. .env 확인
```
AMZ_ADS_CLIENT_ID=...
AMZ_ADS_CLIENT_SECRET=...
AMZ_ADS_REFRESH_TOKEN=...
ANTHROPIC_API_KEY=...
GMAIL_SENDER=orbiters11@gmail.com
GMAIL_TOKEN_PATH=credentials/gmail_token.json
PPC_REPORT_RECIPIENT=wj.choi@orbiters.co.kr
```

### 2. 패키지 확인
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dateutil requests anthropic
```

---

## 알려진 한계

1. **캠페인 레벨만 가능** — Polar는 키워드/검색어 레벨 데이터 미지원
   - 키워드 분석이 필요하면 Amazon Ads MCP 직접 연동 필요
2. **데이터 지연** — Polar 동기화 기준 (보통 1일 지연)
3. **ACOS 계산** — `cost / attributed_sales × 100` (아마존 기준과 약간 다를 수 있음)

---

## 향후 개선
- Amazon Ads MCP 직접 연동 → 키워드/검색어 레벨 분석 추가
- 주간/월간 리포트 버전
- Notion 자동 저장 연동
