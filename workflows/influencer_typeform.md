# Influencer Gifting Form (Typeform) 워크플로우

## 목적
인플루언서 기프팅 신청 폼을 Typeform으로 생성/관리.
기존 IGF(Influencer Gift Form) Shopify 앱 대체.

## 실행 방법

```bash
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/create_typeform_influencer.py
```

실행 시:
1. 제품 이미지 5개를 Typeform CDN에 업로드
2. Typeform 폼 자동 생성 (Logic Jump 포함)
3. 폼 URL 출력

---

## 폼 구조 (v2)

### 개인 정보
| 순서 | 필드 | 타입 | 필수 |
|------|------|------|------|
| 1 | Welcome Screen | - | - |
| 2 | Full Name | short_text | Y |
| 3 | Email | email | Y |
| 4 | Phone Number | phone_number | Y |
| 5 | Instagram Handle | short_text | N (없으면 'None') |
| 6 | TikTok Handle | short_text | N (없으면 'None') |

### 아기 정보 + 제품 분기
| 순서 | 필드 | 타입 | 필수 |
|------|------|------|------|
| 7 | Baby Birthday / Expected Due Date | date | Y |
| 8 | Baby Age Range | multiple_choice | Y |

### 연령대별 Logic Jump
```
Age Range 선택
├─ Expecting / Under 6 months
│   └─ PPSU Baby Bottle 색상 (이미지) → CHA&MOM
├─ 6 - 18 months
│   └─ Straw Cup 타입 선택 (PPSU / SS / Both)
│       ├─ PPSU only → PPSU 색상 (이미지) → CHA&MOM
│       ├─ SS only → SS 색상 (이미지) → CHA&MOM
│       └─ Both → PPSU 색상 → SS 색상 → CHA&MOM
├─ 18 - 36 months
│   └─ SS Tumbler 색상 (이미지) → CHA&MOM
└─ 36 - 48 months
    └─ CHA&MOM (Grosmimi 제품 건너뜀)
```

### 공통 후반부
| 순서 | 필드 | 타입 | 필수 |
|------|------|------|------|
| - | CHA&MOM Duo Bundle (Yes/No) | yes_no (이미지) | Y |
| - | Shipping Address | long_text | Y |
| - | Collaboration Terms | statement | - |
| - | Thank You Screen | - | - |

---

## 등록된 제품

### Grosmimi (연령대별 필수)

| 키 | 제품명 | 가격 | 연령대 | 색상 |
|---|--------|------|--------|------|
| `ppsu_bottle` | PPSU Baby Bottle 10oz | $19.60 | Expecting~6mo | Creamy Blue, Rose Coral, Olive White, Bear Pure Gold, Bear White, Cherry Pure Gold, Cherry Rose Gold |
| `ppsu_straw` | PPSU Straw Cup 10oz | $24.90 | 6~18mo | Peach, Skyblue, White, Aquagreen, Pink, Beige, Charcoal, Butter |
| `ss_straw` | SS Straw Cup 10oz | $46.80 | 6~18mo | Flower Coral, Air Balloon Blue, Cherry Peach, Olive Pistachio, Bear Butter |
| `ss_tumbler` | SS Tumbler 10oz | $49.80 | 18~36mo | Cherry Peach, Bear Butter, Olive Pistachio |

### CHA&MOM (Optional, 전 연령대)

| 키 | 제품명 | 가격 | 비고 |
|---|--------|------|------|
| `chamom_duo` | Essential Duo Bundle | $46.92 | Lotion + Body Wash, 색상 옵션 없음 |

---

## 이미지 처리

- 제품 이미지는 Shopify CDN에서 다운로드 → Typeform CDN에 base64 업로드
- 업로드된 이미지는 Typeform 폼 내 각 제품 색상 선택 화면에 표시
- 이미지 URL은 `PRODUCTS` 딕셔너리의 `image_url` 필드에 저장

---

## Collaboration Terms

```
- Total video length: 30 seconds
- Uploaded content must include voiceover + subtitles
- Must use royalty-free music
- Must tag: @zezebaebae_official (IG), @zeze_baebae (TikTok), @grosmimi_usa (IG & TikTok)
- Must include: #Grosmimi #PPSU #sippycup #ppsusippycup #Onzenna
```

---

## 향후 연동 (n8n)

### Phase 2: Shopify Draft Order 연동
```
Typeform Webhook → n8n
  → Shopify Draft Order API (선택 제품 + variant ID)
  → 내부 알림 (Slack/Email)
```

`create_form()` 호출 시 `webhook_url` 파라미터로 n8n webhook URL 전달:
```python
create_form(
    title="Grosmimi Gifting Application",
    webhook_url="https://your-n8n.com/webhook/xxx"
)
```

### Phase 3: Airtable + 후속 이메일
```
Draft Order 승인 → Order 생성
  → Airtable 레코드 업데이트
  → 컨텐츠 가이드 이메일 발송 (Google Sheets 첨부)
```

### Phase 4: 컨텐츠 추적
```
Airtable에 컨텐츠 업로드 여부 추적
  → 미제출 인플루언서 자동 리마인더 이메일
```

---

## 전제조건

| 항목 | 위치 |
|------|------|
| `.env` | `TYPEFORM_API_KEY` |
| Shopify | 제품 variant ID (스크립트 내 하드코딩) |
| Python 패키지 | `python-dotenv` (이미 설치됨) |

---

## Typeform API 참고

- 이미지 업로드: `POST /images` (JSON base64, NOT multipart)
- 폼 생성: `POST /forms`
- Webhook 등록: `PUT /forms/{form_id}/webhooks/{tag}`
- Logic Jump: `multiple_choice` 필드의 choice ref로 분기 조건 설정
