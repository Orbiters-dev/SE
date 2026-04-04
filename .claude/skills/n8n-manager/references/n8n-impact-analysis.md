# n8n Impact Analysis Guide

변경을 실행하기 전에 blast radius를 사전 파악하는 가이드.

---

## 실행 시점

**변경을 실행하기 전** (Fix Step 2 이전):
- Airtable 필드 이름 변경
- 워크플로우 로직 변경
- 새 integration 추가
- Credential 변경
- 스키마 변경

---

## Step 1: Dependency Registry 로드

워크플로우 간 의존성 맵. 최초 구축 후 변경 시마다 업데이트.

### Registry 구조

```yaml
workflows:
  Draft Generation (0q9uJUYTpDhQFMfz):
    reads:
      airtable:
        - table: Creators
          fields: [Name, Email, Instagram, Status, Draft Status, Brand]
        - table: Dashboard
          fields: [Is Active?, Mode, Draft Template]
    writes:
      airtable:
        - table: Creators
          fields: [Draft Status, Draft Content, Draft Date, Thread ID]
    credentials:
      - rIJuzuN1C5ieE7dr  # Shopify
      - 59gWUPbiysH2lxd8  # Airtable
    triggers: [schedule]
    downstream: [Approval Send]
    upstream: []

  Approval Send (mmkBpmvhzbgmSayh):
    reads:
      airtable:
        - table: Creators
          fields: [Name, Email, Draft Content, Draft Status]
    writes:
      airtable:
        - table: Creators
          fields: [Status, Sent Date]
      gmail:
        - action: send
          uses_thread: true
    credentials:
      - 59gWUPbiysH2lxd8  # Airtable
    triggers: [schedule]
    downstream: [Reply Handler]
    upstream: [Draft Generation]
```

### Registry 위치

`.claude/skills/n8n-manager/references/dependency-registry.yaml`

> **TODO**: 전체 WJ TEST 18개 워크플로우에 대해 최초 registry 구축 필요.
> `curl -sk` 로 전체 fetch → 자동 파싱 스크립트 작성 가능.

---

## Step 2: 변경 타입 분류

| 타입 | 설명 | 위험도 기본값 |
|------|------|-------------|
| **Field rename** | Airtable 필드 이름 변경 | HIGH (가장 위험) |
| **Field add** | 새 필드 추가 | LOW |
| **Field remove** | 필드 폐기 | MEDIUM |
| **Logic change** | 분기/처리 로직 변경 | MEDIUM |
| **Schema change** | 테이블 구조 변경 (새 테이블, 새 뷰) | HIGH |
| **Credential change** | API key/auth 변경 | HIGH |

---

## Step 3: Blast Radius 추적

Dependency Registry에서 변경 영향 추적:

### Field 변경의 경우

1. 해당 필드를 **READ**하는 모든 WF 목록
2. 해당 필드를 **WRITE**하는 모든 WF 목록
3. 해당 필드를 **FILTER**하는 모든 WF 목록
4. 각 WF 내에서 해당 필드를 참조하는 **노드** 목록:
   - Airtable 노드 (columns.value, filterByFormula)
   - Code 노드 (jsCode에서 필드명 사용)
   - Expression (`$json.fieldName`)
   - Gmail/HTTP 노드 (템플릿에서 사용)

### Logic 변경의 경우

1. 변경되는 WF의 output이 다른 WF에 feed되는지
2. Downstream WF가 현재 behavior에 의존하는지

### Credential 변경의 경우

1. 해당 credential 사용하는 모든 WF
2. 각 WF의 credential 참조 노드

---

## Step 4: Risk Assessment

각 영향받는 WF별:

| Risk | 의미 |
|------|------|
| **HIGH** | 수정 안 하면 반드시 깨짐 |
| **MEDIUM** | 특정 조건에서 깨질 수 있음 |
| **LOW** | 기능은 정상, 표면적 영향 |

추가 평가:
- **Data Risk**: 기존 데이터 손상 가능성 (예: field rename without migration)
- **Execution Risk**: 실행 중인 WF 실패 가능성

---

## Step 5: 태스크 순서 생성

의존성 순서로 태스크 생성:

```
1. Airtable 스키마 변경 (필드 변경 시)
2. 상류 WF 수정 (데이터 쓰는 쪽)
3. 하류 WF 수정 (데이터 읽는 쪽)
4. Evaluate 실행 (각 수정된 WF)
5. Audit 실행 (수정된 WF 그룹)
```

---

## 출력 포맷

```markdown
## Impact Analysis: {change description}

### Blast Radius
| Workflow | Nodes Affected | Break Risk | Data Risk | Notes |
|----------|---------------|------------|-----------|-------|

### Implementation Tasks (dependency order)
1. **{task}** — {WF} → {node} — Break risk: {level}
   Must be done before: {#}
2. ...

### Pre-Implementation Checklist
- [ ] 현재 상태 백업 (fetch → /tmp/wf_backup_*.json)
- [ ] Airtable 스키마 변경 선행 (필드 변경 시)
- [ ] 활성 실행 없음 확인
- [ ] Dependency Registry 업데이트 준비

### Post-Implementation Checklist
- [ ] Evaluate 실행 (각 수정된 WF)
- [ ] Audit 실행 (수정된 WF 그룹)
- [ ] 422 에러 없음 확인 (Airtable writes)
- [ ] Dependency Registry 업데이트

### Estimated Effort
- Workflows to modify: {N}
- Total nodes affected: {N}
- Approach: sequential / parallel
```
