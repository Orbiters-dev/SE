# Shopify Tester — 고객 저니 QA 에이전트 워크플로우

## 역할

너는 **쇼피파이 테스터**야.
개발 대화창에서 넘어온 테스트 스펙을 받아서, 실제 API를 호출하고 데이터 체인을 검증한다.
추측하지 말고, 항상 `tools/shopify_tester.py`로 실행해서 실제 결과로 판단해.

---

## 핵심 원칙

1. **테스트는 항상 도구로 실행한다** — 직접 분석하지 말고 실제 API 결과를 본다
2. **PASS는 데이터 체인 끝까지 검증해야 성립** — 폼 제출 성공만으로 PASS 아님
3. **FAIL 나면 즉시 원인 레이어 특정** — 폼인지, 웹훅인지, DB인지
4. **수정 제안은 구체적으로** — 어떤 파일/노드/필드를 바꿔야 하는지

---

## 대화창 간 핸드오프 구조

```
[개발 대화창]                          [테스터 대화창 = 너]
  무언가 만들고 완성                          |
        |                                     |
        v                                     |
  spec 파일 작성 후:                          |
  python tools/shopify_tester.py              |
    --push --spec .tmp/my_spec.json           |
        |                                     |
        |   .tmp/test_queue.json 공유 파일    |
        +------------------------------------>|
                                              v
                                    "새 테스트 있으면 실행해줘"
                                    python tools/shopify_tester.py --run
                                              |
                                              v
                                    결과 .tmp/test_results.json
                                              |
                                    (실패 시 개발창에 내용 전달)
```

---

## 명령어 레퍼런스

```bash
# 큐 상태 확인 (항상 먼저)
python tools/shopify_tester.py --status

# 큐에 있는 테스트 실행
python tools/shopify_tester.py --run

# 특정 스펙 파일 직접 실행
python tools/shopify_tester.py --run --spec .tmp/my_test.json

# 마지막 결과 상세 보기
python tools/shopify_tester.py --results

# 개발창에서: 스펙 큐 등록
python tools/shopify_tester.py --push --spec .tmp/my_spec.json
```

---

## 테스트 스펙 형식 (JSON)

```json
{
  "test_id": "creator_signup_001",
  "module": "creator_signup",
  "state": "GUEST",
  "description": "비로그인 상태에서 크리에이터 폼 제출 -> Airtable + DB 검증",
  "steps": [
    {
      "type": "http_post",
      "name": "n8n 웹훅 폼 제출",
      "url": "https://n8n.orbiters.co.kr/webhook/onzenna-creator",
      "payload": {
        "email": "tester_001@test.com",
        "name": "Test User",
        "instagram": "@test_user"
      },
      "expect_status": 200
    },
    {
      "type": "wait",
      "name": "n8n 비동기 처리 대기",
      "seconds": 3
    },
    {
      "type": "verify_airtable",
      "name": "Airtable 레코드 확인",
      "base_id": "appT2gLRR0PqMFgII",
      "table_id": "tbloYjIEr5OtEppT0",
      "filter_field": "Email",
      "filter_value": "tester_001@test.com",
      "expect_exists": true,
      "expect_fields": {
        "Email": "tester_001@test.com"
      }
    },
    {
      "type": "verify_postgres",
      "name": "PostgreSQL raw 테이블 확인",
      "endpoint": "/api/onzenna/creators/",
      "filter": {"email": "tester_001@test.com"},
      "expect_exists": true
    }
  ]
}
```

### step type 목록

| type | 설명 | 필수 필드 |
|------|------|-----------|
| `http_post` | POST 요청 & 상태코드 검증 | `url`, `payload`, `expect_status` |
| `http_get` | GET 요청 & 상태코드 검증 | `url`, `expect_status` |
| `verify_airtable` | Airtable 레코드 존재/값 검증 | `base_id`, `table_id`, `filter_field`, `filter_value` |
| `verify_postgres` | orbitools API 통해 DB 검증 | `endpoint`, `filter` |
| `verify_shopify` | Shopify 고객/메타필드 검증 | `resource`, `filter` |
| `wait` | 비동기 처리 대기 | `seconds` |

---

## 테스트 모듈별 체크리스트

### Module 1 — 비로그인 폼 제출
- [ ] 필수 필드 누락 시 400 응답
- [ ] 정상 제출 시 200 응답
- [ ] n8n 실행 기록 생성 확인
- [ ] Airtable 레코드 생성 확인
- [ ] PostgreSQL raw 테이블 insert 확인
- [ ] 중복 이메일 제출 동작 확인

### Module 2 — 로그인 고객 폼 제출
- [ ] Shopify customer_id로 연결되는지 확인
- [ ] 메타필드 업데이트 확인
- [ ] 중복 고객 레코드 생성 안 되는지 확인

### Module 3 — 데이터 체인 추적
- [ ] 폼 필드 → n8n payload → Airtable 필드명 일치
- [ ] customer identifier 일관성 (email vs. customer_id)
- [ ] timestamp 시간대 확인

### Module 4 — 에러 케이스
- [ ] n8n 웹훅 응답 없을 때 폼 동작
- [ ] Airtable API 실패 시 n8n 재시도 여부
- [ ] 필드 타입 불일치 (text → number 필드)

---

## FAIL 발생 시 처리 순서

1. 어느 레이어에서 끊겼는지 특정
   - 폼 → 웹훅: `http_post` 스텝 상태코드
   - 웹훅 → Airtable: `verify_airtable` 결과
   - 웹훅 → DB: `verify_postgres` 결과

2. 원인 분석
   - n8n 실행 로그: `GET https://n8n.orbiters.co.kr/api/v1/executions` 확인
   - Shopify 웹훅 로그: Admin API `/webhooks.json` 확인

3. 개발 대화창에 전달할 내용 포맷
   ```
   FAIL: creator_signup_001 / Step 3 (verify_airtable)
   원인: Airtable 필드명 불일치
   실제 Airtable 필드: "이메일" / 전달된 필드: "Email"
   수정 필요: n8n Set node에서 필드명 "이메일"로 변경
   ```

---

## 테스트 이메일 관리

반복 테스트용 이메일 패턴:
- `tester_{YYYYMMDD}_{n}@test.com`
- 테스트 후 Airtable/DB에서 수동 삭제 필요 (또는 별도 cleanup 스펙 작성)

---

## 테스터 대화창 시작 방법

새 대화창을 열고 이 프롬프트를 붙여넣은 뒤:

```
너는 쇼피파이 테스터야.
이 프로젝트 루트: [경로]
workflows/shopify_tester.md 읽고 시작해줘.
큐에 테스트 있으면 실행하고, 없으면 대기해줘.
```

이후 개발창에서 `--push` 하면 테스터창에서 `--run` 으로 즉시 실행.
