# Shopify Influencer Gifting Page 배포

## 목적
Shopify 스토어(onzenna.com)에 인플루언서 기프팅 신청 전용 페이지를 배포.
- IGF 같은 제품 이미지 + 색상 선택 UI
- 아기 생년월일 기반 연령 자동 계산 + 제품 추천
- 둘째 아이 지원 (연령대 합산으로 제품 표시)
- 구조화된 주소 입력 (Street, City, State, ZIP)
- Shopify 고객 로그인 감지 + 정보 자동 채움
- n8n webhook 연동

## 전제조건

| 항목 | 위치 |
|------|------|
| `.env` | `SHOPIFY_SHOP`, `SHOPIFY_ACCESS_TOKEN` (write_themes + write_content 스코프 필요) |
| `.env` | `N8N_INFLUENCER_WEBHOOK` (n8n webhook URL) |
| Python 패키지 | `python-dotenv` |

### OAuth 스코프 업데이트
기존 READ 스코프에 `write_themes`, `write_content` 추가 필요:
```bash
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/shopify_oauth.py
```
브라우저에서 Shopify OAuth 승인 → 새 토큰 자동 저장.

## 실행 방법

### 배포
```bash
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/deploy_influencer_page.py
```

### Dry Run (변경 없이 확인만)
```bash
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/deploy_influencer_page.py --dry-run
```

### 롤백 (배포 취소)
```bash
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/deploy_influencer_page.py --rollback
```

## 배포 내용

### Shopify 테마 파일 (자동 업로드)
| 파일 | 설명 |
|------|------|
| `sections/influencer-gifting.liquid` | 폼 UI 전체 (HTML/CSS/JS) |
| `templates/page.influencer-gifting.json` | 페이지 템플릿 (OS 2.0) |

### Shopify 페이지
- Handle: `influencer-gifting`
- URL: `https://onzenna.com/pages/influencer-gifting`
- Template: `page.influencer-gifting`

## 폼 구조 (5단계)

### Step 1: Personal Info
- Full Name (필수)
- Email (필수)
- Phone +1 (필수)
- Instagram handle (선택)
- TikTok handle (선택)

### Step 2: Baby Info
- First Child Birthday / Due Date (필수)
  - JS로 나이 자동 계산 + 표시
- ☐ I have another child
  - Second Child Birthday (체크 시 표시)

### Step 3: Product Selection
연령대 기반 자동 표시 (두 아이 합산):
| 제품 | 연령대 | 가격 |
|------|--------|------|
| PPSU Baby Bottle 10oz | Expecting ~ 6개월 | $19.60 |
| PPSU Straw Cup 10oz | 6 ~ 18개월 | $24.90 |
| SS Straw Cup 10oz | 6 ~ 18개월 | $46.80 |
| SS Tumbler 10oz | 18 ~ 36개월 | $49.80 |
| CHA&MOM Duo Bundle | 0 ~ 48개월 (Optional) | $46.92 |

### Step 4: Shipping Address
- Street Address, Apt/Suite, City, State (드롭다운), ZIP, Country

### Step 5: Terms & Submit
- Collaboration Terms 표시 + I agree 체크
- Submit → n8n webhook POST

## n8n Webhook 페이로드
```json
{
  "form_type": "influencer_gifting",
  "submitted_at": "2026-02-19T15:30:00Z",
  "personal_info": { "full_name": "...", "email": "...", "phone": "+1...", "instagram": "@...", "tiktok": "@..." },
  "baby_info": {
    "child_1": { "birthday": "2025-08-15", "age_months": 6 },
    "child_2": { "birthday": "2024-02-10", "age_months": 24 }
  },
  "selected_products": [
    { "product_key": "ppsu_straw", "product_id": 8288579256642, "variant_id": 45373972545858, "title": "...", "color": "Peach", "price": "$24.90" }
  ],
  "shipping_address": { "street": "...", "apt": "...", "city": "...", "state": "NY", "zip": "10001", "country": "US" },
  "terms_accepted": true,
  "shopify_customer_id": 12345678
}
```

## Collaboration Terms
```
- Total video length: 30 seconds
- Uploaded content must include voiceover + subtitles
- Must use royalty-free music
- Must tag: @zezebaebae_official (IG), @zeze_baebae (TikTok), @grosmimi_usa (IG & TikTok)
- Must include: #Grosmimi #PPSU #sippycup #ppsusippycup #Onzenna
```

## 향후 연동

### Phase 2: n8n → Shopify Draft Order
```
n8n Webhook 수신
  → Shopify Draft Order API 호출 (선택 제품 variant ID 기반)
  → 내부 알림 (Slack/Email)
```

### Phase 3: Airtable + 후속 이메일
```
Draft Order 승인 → Order 생성
  → Airtable 레코드 업데이트
  → 컨텐츠 가이드 이메일 발송
```

## 트러블슈팅

| 문제 | 해결 |
|------|------|
| `write_themes` 스코프 에러 | `tools/shopify_oauth.py` 재실행하여 OAuth 재인증 |
| 테마에 페이지가 안 보임 | Shopify Admin → Pages에서 `influencer-gifting` 페이지 published 확인 |
| 폼 제출 에러 | `.env`의 `N8N_INFLUENCER_WEBHOOK` URL 확인 |
| CSS 깨짐 | 모든 CSS 클래스가 `igf-` 접두사 사용 중 — 테마 충돌 시 확인 |
| 롤백 | `--rollback` 플래그로 배포 취소 가능 |
