# n8n Workflow Evaluate Checklist

단일 워크플로우의 구조적 정합성을 검증하는 체크리스트.
Pathlight AI n8n-evaluate에서 적응, ORBI n8n 환경(orbiters.co.kr) 특화.

---

## 실행 방법

```bash
# 1. 워크플로우 fetch
curl -sk -H "X-N8N-API-KEY: $KEY" \
  "https://n8n.orbiters.co.kr/api/v1/workflows/$WF_ID" > /tmp/wf_eval.json

# 2. JSON 파싱 후 아래 체크리스트 순회
```

---

## 체크리스트

### 1. Credential 검증

모든 노드를 순회하며:

- [ ] `authentication` 설정된 노드 → `credentials` 객체 존재 확인
- [ ] `credentials.{type}.id` 값이 실제 존재하는 credential ID인지
- [ ] HTTP Request + `predefinedCredentialType` → `credentials.{type}.id` populated
- [ ] 알려진 Credential ID 매칭:
  - `rIJuzuN1C5ieE7dr`: Shopify Admin API (Gifting)
  - `59gWUPbiysH2lxd8`: Airtable PAT (WJ Test)

### 2. Expression 참조 검증

- [ ] 모든 `$('Node Name')` 참조 → 해당 이름의 노드가 workflow에 존재
- [ ] `$('Node Name')` 참조 → 현재 노드의 실행 경로에서 도달 가능
  - IF/Switch 분기 뒤의 노드를 다른 분기에서 참조하면 **실행 안 됨**
- [ ] 크로스 분기 참조 → `try/catch`로 감싸져 있는지
- [ ] `$json.fieldName` → upstream 노드 출력에 해당 필드 존재 가능성

### 3. Airtable 노드 특화

- [ ] **Update 노드**: `matchingColumns` 포함 (보통 `["id"]`)
- [ ] **Select 필드**: 값이 Airtable 스키마의 유효 옵션과 일치
- [ ] **Date 필드**: ISO 8601 형식 (`YYYY-MM-DD`), datetime 아님
- [ ] **Zero-value guard**: Update에서 `0` 값 숫자 필드 → 기존 데이터 덮어쓰기 위험
  - `Age: 0`, `Followers: 0` 등 → 의도적인지 확인
- [ ] **id 필드**: update operation의 id가 유효한 record ID로 resolve되는지 (undefined 아닌지)

### 4. Gmail 노드 특화

- [ ] `appendAttribution: false` 설정 (n8n 서명 제거)
- [ ] `resource`와 `operation` 명시적 설정 (v2+ 필수)
- [ ] 메일 본문에서 `$('Node Name')` 참조 유효성

### 5. 토폴로지 검증

- [ ] **끊어진 노드**: input도 output도 없는 노드 (trigger, Sticky Note 제외)
- [ ] **고아 분기**: 어디로도 연결 안 된 경로
- [ ] **Merge 노드**: 모든 예상 입력이 연결되어 있는지
  - IF 분기 한쪽만 Merge에 연결 → 데이터 누락 위험
- [ ] **SplitInBatches v3**: output[0]=done, output[1]=loop (v1/v2와 **반대**)
- [ ] **Trigger 노드**: active WF의 trigger가 disabled → WARNING
- [ ] **executionOrder**: `"v1"` 확인

### 6. Config Flow-Through 검증

Config 노드(정적 JSON 반환하는 Code 노드)가 있는 경우:

- [ ] Config 출력의 모든 필드 → downstream에서 최소 1곳 이상 `$('Config').first().json.field` 참조
- [ ] **미소비 Config 필드**: SET했지만 downstream에서 안 읽힘 → silent bug
- [ ] **Shadowed Config**: downstream에서 hardcoded fallback이 Config 값을 덮어씀
- [ ] **Limit/Cap 필드** (batchSize, contentLimit 등): 무거운 처리 노드(AT write, API call) **전에** 적용
- [ ] **Enable/Disable 플래그**: 관련 gate 노드 **모두에서** 체크 (하나만 체크 ≠ 완전)

### 7. Test Mode 탐지

- [ ] Manual Trigger 노드 이름에 "test", "debug" 포함 → FLAG
- [ ] `HUMAN_IN_LOOP = false` 같은 test override → FLAG
- [ ] Production trigger가 disabled → FLAG
- [ ] WJ TEST 워크플로우인데 PROD Airtable base ID(`appNPVxj4gUJl9v15`) 참조 → CRITICAL

---

## 출력 포맷

```markdown
## Workflow Evaluation: {workflow name}
**ID**: {id} | **Nodes**: {count} | **Active**: {yes/no} | **환경**: PROD/WJ TEST

### CRITICAL (반드시 수정)
- [{node name}] {issue}
  Fix: {specific instruction with parameter values}

### WARNING (수정 권장)
- [{node name}] {issue}

### INFO (참고)
- [{node name}] {observation}

### Summary
- {X} critical, {Y} warning, {Z} info
- Status: PASS / NEEDS_FIXES / BLOCKED
```
