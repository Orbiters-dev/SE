# Influencer Gifting Order Processing 워크플로우

## 목적

인플루언서 기프팅 폼 제출 데이터를 받아 Shopify에:
1. Customer 생성/조회 (이메일 중복 방지)
2. Customer metafields 설정 (Instagram, TikTok, 아이 생일 등)
3. Draft Order 생성 (태그 "pr, influencer-gifting" + 무료배송)

기존 n8n의 Draft Order 생성 로직을 대체.

---

## 실행 방법

```bash
# 파일 입력
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/process_influencer_order.py --input payload.json

# JSON 문자열 입력 (n8n Execute Command용)
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/process_influencer_order.py --json '{"form_type": "influencer_gifting", ...}'

# stdin 입력
cat payload.json | "C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/process_influencer_order.py

# 미리보기 (API 호출 없음)
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/process_influencer_order.py --dry-run --input payload.json
```

---

## 입력 페이로드 형식

Shopify 인플루언서 폼 또는 Typeform에서 전송되는 JSON:

```json
{
  "form_type": "influencer_gifting",
  "submitted_at": "2026-02-20T03:52:17.803Z",
  "personal_info": {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+12125551234",
    "instagram": "@janedoe",
    "tiktok": "@janedoe"
  },
  "baby_info": {
    "child_1": {"birthday": "2025-08-15", "age_months": 6},
    "child_2": null
  },
  "selected_products": [
    {
      "product_key": "ppsu_bottle",
      "variant_id": 51854035059058,
      "title": "Grosmimi PPSU Baby Bottle - 10oz (300ml)",
      "color": "Olive White",
      "price": "19.60"
    }
  ],
  "shipping_address": {
    "street": "123 Main St",
    "apt": "Apt 4B",
    "city": "New York",
    "state": "NY",
    "zip": "10001",
    "country": "US"
  },
  "terms_accepted": true
}
```

---

## 처리 흐름

```
1. 페이로드 검증 (필수 필드 체크)
2. 이메일로 기존 고객 검색
   ├─ 기존 고객 발견:
   │   ├─ 이름이 "Newsletter Subscriber" 등 기본값 → 폼 이름으로 업데이트
   │   ├─ Customer metafields 업서트
   │   └─ 태그 "pr, influencer-gifting" 추가
   └─ 고객 없음:
       └─ 새 고객 생성 (이름, 이메일, 전화, metafields, 태그)
3. Draft Order 생성
   ├─ 제품: variant_id 기반 line items
   ├─ 태그: "pr, influencer-gifting"
   ├─ 배송: "Influencer Gifting - Free Shipping" ($0)
   └─ 노트: 인플루언서 정보 요약
```

---

## Customer Metafields

| Namespace | Key | Type | 설명 |
|-----------|-----|------|------|
| `influencer` | `instagram` | single_line_text_field | 인스타그램 핸들 |
| `influencer` | `tiktok` | single_line_text_field | 틱톡 핸들 |
| `influencer` | `child_1_birthday` | date | 첫째 아이 생일 |
| `influencer` | `child_2_birthday` | date | 둘째 아이 생일 (선택) |
| `influencer` | `submitted_at` | date_time | 폼 제출 시간 |

"None", "nope", "n/a" 값은 metafield에 저장하지 않음.

---

## n8n 연동

기존 n8n 워크플로우 수정:

1. 기존 "Shopify Create Draft Order" 노드 제거
2. "Execute Command" 노드 추가:
   ```
   "C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/process_influencer_order.py --json '{{ JSON.stringify($json) }}'
   ```
3. stdout 파싱으로 결과 확인:
   ```json
   {"success": true, "customer_id": 12345, "draft_order_id": 67890, "draft_order_name": "#D1234"}
   ```

---

## 전제조건

| 항목 | 위치 | 비고 |
|------|------|------|
| `SHOPIFY_SHOP` | `.env` | mytoddie.myshopify.com |
| `SHOPIFY_ACCESS_TOKEN` | `.env` | `write_customers` + `write_draft_orders` 스코프 필요 |
| Python 패키지 | - | `python-dotenv` (이미 설치됨) |

**중요**: OAuth 토큰에 `write_customers` 스코프가 없으면 고객 생성/수정 시 403 에러 발생.
스코프 추가 후 `python tools/shopify_oauth.py` 재실행 필요.

---

## 트러블슈팅

| 에러 | 원인 | 해결 |
|------|------|------|
| 403 Forbidden on customer create | `write_customers` 스코프 누락 | OAuth 재실행 |
| 422 on customer create | 이메일 이미 존재 (레이스 컨디션) | 재실행하면 기존 고객 사용 |
| 400 on draft order | 잘못된 variant_id | 제품 variant ID 확인 |
| Validation error | 필수 필드 누락 | 페이로드 형식 확인 |
