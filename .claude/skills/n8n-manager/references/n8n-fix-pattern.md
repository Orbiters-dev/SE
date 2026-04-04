# n8n Standard Fix Pattern

워크플로우를 안전하게 수정하는 REST-first 5단계 표준 절차.
MCP update 도구(n8n_update_partial_workflow 등)는 known bug으로 **사용 금지**.

---

## 5단계 절차

### Step 0: 인스턴스 확인

```bash
# API Key 로드
source ~/.wat_secrets  # N8N_API_KEY
BASE="https://n8n.orbiters.co.kr/api/v1"
```

### Step 1: Fresh Fetch

**절대 old `/tmp/wf_*.json` 파일 재사용 금지. 매번 새로 fetch.**

```bash
curl -sk -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$BASE/workflows/$WF_ID" > /tmp/wf_current.json
```

파싱 후 mental model 구축:
- 모든 노드: 이름, 타입, 주요 파라미터
- 커넥션 맵
- 변경 영향받는 노드 식별

### Step 2: Change Plan 제시

수정 전 반드시 계획 명시:

```markdown
### Change Plan
- **Node(s) affected**: {list}
- **What changes**: {description}
- **Side effects to check**: {downstream nodes referencing changed fields}
```

### Step 3: Python으로 JSON 수정

```python
import json

with open('/tmp/wf_current.json', 'rb') as f:
    wf = json.loads(f.read().decode('utf-8'))

# --- 변경 적용 ---
# for node in wf['nodes']:
#     if node['name'] == 'Target Node':
#         node['parameters']['field'] = 'new_value'
# --- 변경 끝 ---

# PUT 페이로드 구성 (4필드 필수)
payload = {
    'name': wf['name'],
    'nodes': wf['nodes'],
    'connections': wf['connections'],
    'settings': wf.get('settings', {})
}

with open('/tmp/wf_payload.json', 'w', encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False)
```

### Step 4: PUT + 즉시 검증

```bash
# 배포
curl -sk -X PUT \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/wf_payload.json \
  "$BASE/workflows/$WF_ID" > /tmp/wf_result.json

# 즉시 re-fetch로 검증
curl -sk -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$BASE/workflows/$WF_ID" > /tmp/wf_verify.json
```

**변경된 필드 하나하나 대조. PUT 200 ≠ 성공.**

### Step 5: Auto-QA

evaluate 체크리스트 경량 버전 실행:
- [ ] 변경된 노드의 `$('Node Name')` 참조 유효
- [ ] Airtable 노드: `matchingColumns: ["id"]`
- [ ] Gmail 노드: `appendAttribution: false`
- [ ] 끊어진 노드 없음
- [ ] Credential ID 유효

---

## 핵심 규칙

### API 규칙
| 규칙 | 설명 |
|------|------|
| PUT 4필드 필수 | `name`, `nodes`, `connections`, `settings` |
| POST시 active 금지 | `active` 필드 포함 → 400 |
| PUT시 name 필수 | name 누락 → 400 |
| Windows curl | `-sk` 플래그 필수 |
| 큰 WF (50+ nodes) | 파일로 저장 후 `rb` + `decode('utf-8')` |

### 노드 규칙
| 규칙 | 설명 |
|------|------|
| IF gate downstream | `main[1]` (FALSE)에 연결, `main[0]` (TRUE)이 아님 |
| Gmail | `appendAttribution: false` 항상 |
| Airtable Update | `matchingColumns: ["id"]` 항상 |
| SplitInBatches v3 | `output[0]`=done, `output[1]`=loop (**v1/v2와 반대**) |
| 새 노드 위치 | 기존 노드에서 +800px offset (겹침 방지) |
| 새 노드 ID | UUID 생성 |

### 배치 규칙
| 규칙 | 설명 |
|------|------|
| 1회 사이클 | 여러 변경 → 1회 fetch→modify→PUT (순차 PUT 금지) |
| old cache 금지 | 매번 fresh fetch |
| 백업 | 수정 전 현재 상태 `/tmp/wf_backup_{id}.json` 저장 |

---

## 리포트 포맷

```markdown
## Fix Applied: {workflow name}
**Workflow ID**: {id}
**URL**: https://n8n.orbiters.co.kr/workflow/{id}

### Changes Made
| Node | Change | Verified |
|------|--------|----------|
| {name} | {what changed} | Yes/No |

### QA Results
- Structural: PASS/FAIL
- Airtable: PASS/FAIL/N/A
- Issues found: {list or "None"}

### Side Effects Checked
- [ ] {downstream node} — {field reference still valid}
```
