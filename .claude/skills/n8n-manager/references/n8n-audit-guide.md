# n8n Cross-Workflow Audit Guide

여러 워크플로우 간 일관성을 검증하는 감사 가이드.
PROD↔WJ TEST 환경 간 동기화 검증에 특화.

---

## 실행 방법

```bash
# 모든 워크플로우 fetch (한번에)
curl -sk -H "X-N8N-API-KEY: $KEY" \
  "https://n8n.orbiters.co.kr/api/v1/workflows?limit=100" > /tmp/wf_all.json

# 또는 특정 워크플로우들만
for ID in 0q9uJUYTpDhQFMfz mmkBpmvhzbgmSayh nVtYmhU0InRqRn4K; do
  curl -sk -H "X-N8N-API-KEY: $KEY" \
    "https://n8n.orbiters.co.kr/api/v1/workflows/$ID" > /tmp/wf_$ID.json
done
```

**규칙: 모든 대상 워크플로우를 먼저 fetch 후 분석 (순차 분석 금지)**

---

## Audit 항목

### 1. Airtable 필드 일관성

같은 Airtable 테이블을 사용하는 워크플로우 간:

| 체크 | 설명 |
|------|------|
| Write 필드 일치 | WF-A가 `"Draft Status"` 쓰면 WF-B도 동일 이름으로 읽는지 |
| Read 필드 존재 | WF-B가 읽는 필드를 WF-A (또는 다른 WF)가 실제 쓰는지 |
| 고아 Write | 아무 WF도 안 읽는 필드를 쓰고 있는지 |
| 누락 Write | 읽히지만 아무 WF도 안 쓰는 필드 |
| Case 일치 | `"Draft Status"` vs `"draft_status"` vs `"DraftStatus"` — **case-sensitive** |

**추출 방법:**
- Airtable 노드: `columns.value` (write), `filterByFormula` (filter)
- Code 노드: `$json.fieldName` 패턴
- Expression: `$('Node').first().json.fieldName` 패턴

### 2. PROD↔WJ TEST 환경 일관성

| 체크 | 설명 |
|------|------|
| Airtable Base ID | PROD=`appNPVxj4gUJl9v15`, WJ TEST=`appT2gLRR0PqMFgII` — 혼재 금지 |
| Shopify Store | PROD=`mytoddie.myshopify.com`, WJ TEST=`toddie-4080.myshopify.com` |
| Credential ID | 같은 서비스에 다른 credential ID 사용 → FLAG |
| 노드 구조 | 같은 논리의 WF 쌍에서 노드 수/이름 차이 |
| Config 패턴 | PROD=AT Dashboard, WJ TEST=Google Sheets — 의도적 차이 확인 |

### 3. Status/Select 필드 값 크로스체크

Airtable Select 필드를 여러 WF에서 사용하는 경우:

```
Draft Gen이 Status="Draft Ready" 쓰는데
Reply Handler가 Status="DraftReady" 체크 → 불일치!
```

- 모든 WF에서 해당 Select 필드에 쓰는/읽는 값 수집
- 값 목록 교차 비교 (공백, 대소문자 차이 포함)

### 4. Credential 일관성

- 같은 서비스(Airtable, Shopify, Gmail) → 같은 credential ID 사용
- 다른 credential ID → 의도적인지 확인 (예: WJ TEST용 별도 credential)

### 5. Gmail Thread 연속성

여러 WF가 Gmail thread를 공유하는 경우:
- Thread ID 필드명 일치
- 모든 WF가 같은 AT 필드에서 thread ID 읽기

### 6. Data Shape 일관성

WF-A가 Airtable에 쓴 데이터를 WF-B가 읽는 경우:
- WF-B의 expected shape가 WF-A의 actual output과 일치
- WF-A가 선택적으로 안 쓰는 필드 → WF-B에서 null 핸들링

---

## WJ TEST 워크플로우 인벤토리 (18개, 2026-03-13 기준)

| ID | 이름 | 연관 WF |
|----|------|--------|
| `0q9uJUYTpDhQFMfz` | Draft Generation | → Approval Send |
| `mmkBpmvhzbgmSayh` | Approval Send | ← Draft Gen, → Reply Handler |
| `nVtYmhU0InRqRn4K` | Reply Handler | ← Approval Send |
| `4q5NCzMb3nMGYqL4` | Gifting | → Fulfillment |
| `734aqkcOIfiylExL` | Gifting2 → Draft Order | → Fulfillment |
| `UP1OnpNEFN54AOUn` | Fulfillment → Airtable | ← Gifting/Gifting2 |
| `Vd5NiKMwdLT7b9wa` | Sample Sent → Complete | |
| `2vsXyHtjo79hnFoD` | Shipped → Delivered | |
| `82t55jurzbY3iUM4` | Delivered → Posted | → Content Tracking |
| `FT70hFR6qI0mVc2T` | Syncly Metrics Sync | |
| `wyttsPSZJlWLgy86` | Customer Lookup | |
| `zKmOX0tEWi6EBT9h` | Content Tracking | ← Delivered→Posted |
| `6BNQRz57oCtdROlH` | Syncly Data Processing | |
| `k08R16VJIuSPdi6T` | ManyChat Automation | |

---

## 출력 포맷

```markdown
## Cross-Workflow Audit Report
**Workflows**: {list with names and IDs}
**Instance**: orbiters.co.kr
**Date**: {today}

### Shared Resources
| Resource | Type | Workflows |
|----------|------|-----------|

### CRITICAL — Field Mismatches
| Field | WF-A (writes) | WF-B (reads) | Issue |
|-------|---------------|--------------|-------|

**Fix**: {which WF, which node, exact field name}

### WARNING — Potential Inconsistencies
| Issue | Workflows | Details |
|-------|-----------|---------|

### INFO
- {patterns, redundancies, optimization opportunities}

### Verdict: CLEAN / ISSUES_FOUND
```
