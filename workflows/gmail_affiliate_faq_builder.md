# Gmail Affiliate FAQ Builder

## 목적
`affiliates@onzenna.com` Gmail 받은편지함의 이메일 로그를 수집하여
인플루언서/어필리에이트 협업 문의에 대한 **FAQ를 자동 생성**합니다.

## 결과물
- **Google Sheets**: `AFFILIATE_FAQ_SHEET_ID` 스프레드시트의 `Affiliate_FAQ` 시트
- **Excel 백업**: `.tmp/gmail_affiliate_faq/affiliate_faq_YYYY-MM-DD_HHMM.xlsx`

---

## 최초 설정 (1회만 필요)

### 1. Google Cloud Console 설정

1. [https://console.cloud.google.com](https://console.cloud.google.com) 접속
2. 프로젝트 선택 또는 새 프로젝트 생성
3. **API 및 서비스 → 라이브러리 → Gmail API 검색 → 사용 설정**
4. **OAuth 동의 화면** 구성
   - 앱 유형: 내부 (Google Workspace) 또는 외부
   - 앱 이름, 이메일 입력 후 저장
5. **사용자 인증 정보 → OAuth 2.0 클라이언트 ID 만들기**
   - 유형: **데스크톱 앱** 선택
   - 이름 입력 후 생성
6. **JSON 다운로드** → `credentials/gmail_oauth_credentials.json`에 저장

### 2. .env 파일에 추가

```bash
GMAIL_OAUTH_CREDENTIALS_PATH=credentials/gmail_oauth_credentials.json
AFFILIATE_FAQ_SHEET_ID=<FAQ를 저장할 Google Sheets ID>
```

Google Sheets ID는 시트 URL에서 추출:
`https://docs.google.com/spreadsheets/d/**{SHEET_ID}**/edit`

> **주의**: 해당 스프레드시트에 `GOOGLE_SERVICE_ACCOUNT_PATH`의 서비스 계정 이메일을 편집자로 공유해야 합니다.

### 3. 패키지 설치

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client gspread
```

### 4. 첫 실행 시 Gmail 인증

```bash
python tools/gmail_affiliate_faq_builder.py --dry-run --months 1
```

- 브라우저가 자동으로 열립니다
- **`affiliates@onzenna.com`** 계정으로 로그인
- "Gmail 읽기 권한" 승인
- 토큰이 `credentials/gmail_token.json`에 저장 (이후 자동 인증)

---

## 실행 방법

```bash
# 기본 실행 (최근 3개월, Google Sheets + Excel 저장)
# NOTE: Tool implementation pending - workflow documentation complete

# 기간 변경 (최근 6개월)
python tools/gmail_affiliate_faq_builder.py --months 6

# Excel만 저장 (Google Sheets 건너뜀) - 결과 미리보기용
python tools/gmail_affiliate_faq_builder.py --dry-run
```

---

## 처리 흐름

```
Step 1: Gmail OAuth 인증 + 이메일 페치
        ↓ (받은편지함, after:{N개월 전}, 자동회신 필터링)
Step 2: 이메일 파싱
        ↓ (제목, 발신자, 날짜, 본문 추출)
Step 3: Claude Haiku로 분류
        ↓ (카테고리 + 파트너십 유형 분류 + FAQ 대상 여부 판단)
Step 4: Claude Sonnet으로 FAQ 합성
        ↓ (카테고리 × 파트너십 유형별 Q&A + 질문 변형 생성)
Step 5: Google Sheets 저장
        ↓ (Affiliate_FAQ 시트)
Step 6: Excel 로컬 백업
        → .tmp/gmail_affiliate_faq/affiliate_faq_YYYY-MM-DD_HHMM.xlsx
```

---

## FAQ 카테고리 (영어, 11개)

| Category | 설명 |
|----------|------|
| How to Join & Get Started | 가입/신청 방법 |
| Product Selection & What We Send | 수령 제품 종류/선택 |
| Shipping & Delivery of Product | 제품 배송 관련 |
| Commission Rate & Structure | 커미션 비율/구조 |
| Payment Schedule & Method | 정산 일정/방법 |
| Promo Code & Affiliate Link | 추적 링크/할인 코드 |
| Content Requirements & Posting | 콘텐츠 요건/게시 규칙 |
| Eligibility & Follower Requirements | 자격 요건/팔로워 기준 |
| Exclusivity & Brand Conflicts | 타 브랜드 협업 제한 |
| Timeline & Next Steps | 다음 단계/일정 |
| Other | 기타 |

---

## 파트너십 유형 (내부 분류 — 이메일 답변에는 절대 사용 금지)

| 유형 | 설명 |
|------|------|
| **High Touch** (내부용) | 유료 협업. 계약서 서명, 커스텀 콘텐츠 가이드, 페이 지급. |
| **Low Touch** (내부용) | 무료 샘플 제공. 링크 1개로 처리, 표준 프로세스. |
| **General** | 유형 불분명 또는 공통 문의. |

> ⚠️ "High Touch" / "Low Touch" 표현은 내부 분류 전용. 인플루언서에게 보내는 답변에는 절대 포함하지 말 것.

---

## 협업 조건 (FAQ 답변 기준)

### Low Touch (샘플 협업)
- 영상 길이: 30초
- Voiceover + 자막 필수
- 저작권 무료 음악 사용
- 태그: @zezebaebae_official (IG), @zeze_baebae (TikTok), @grosmimi_usa (IG & TikTok)
- 해시태그: #Grosmimi #PPSU #sippycup #ppsusippycup #Onzenna
- 샘플 수령 후 1주일 이내 업로드
- 원본 파일(자막/음악 없음) 제공 필수
- 업로드 후 Whitelisting code 제공

### High Touch (유료 협업, 계약서 기준)
- 납품물: 보통 Instagram Reel 2개 + TikTok 영상 2개
- 금액: **`[ ]` USD** — 구체적 금액은 Syncly 로직으로 결정, 답변에는 `[ ]`로 표기
- 정산: PayPal, NET 30 (게시 후 30일)
- 태그: @onzenna, @grosmimi_usa 필수. #Ad 또는 #Sponsored 공시
- 원본 파일(자막/음악 없음) 제공 → Whitelisting 활용
- 모든 콘텐츠는 게시 전 브랜드 검토/승인 필요
- Meta Whitelisting 및 Spark Ads 활용 가능
- 계약 금액 기밀 유지

---

## 답변 작성 규칙

1. **High Touch / Low Touch 표현 금지** — 답변(Answer)에는 절대 사용 금지. Internal Notes에만 가능.
2. **간결하게** — 2~4문장. 불필요한 설명 제거.
3. **금액은 `[ ]`** — Commission/Payment 답변에서 구체적 금액 대신 `[ ]` 사용.
4. **Question Variations** — 같은 카테고리 내 다른 각도의 질문 3~5개 제시.

---

## 결과물 컬럼

| 컬럼 | 설명 |
|------|------|
| faq_id | FAQ 고유 ID (AFF-001, AFF-002, ...) |
| Category | FAQ 분류 (영어) |
| Partnership Type | 내부 분류 (High Touch / Low Touch / General) |
| Email Count | 해당 그룹 이메일 개수 |
| Question Variations | 질문 변형 3~5개 (bullet) |
| Answer | 권장 답변 (영어, 2~4문장) |
| Internal Notes | 내부 참고사항 (High/Low Touch 용어 사용 가능) |
| Related Keywords | 연관 키워드 |
| Update Log | 생성 일시 및 버전 |

---

## 환경변수 참조

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API 키 |
| `GMAIL_OAUTH_CREDENTIALS_PATH` | ✅ | OAuth Client ID JSON 경로 |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | ✅ | Google Sheets용 서비스 계정 JSON |
| `AFFILIATE_FAQ_SHEET_ID` | ✅ | FAQ 저장할 Google Sheets ID |
| `GMAIL_TOKEN_PATH` | 선택 | Gmail 토큰 저장 경로 (기본: credentials/gmail_token.json) |
