# ORBI Ops Framework

모든 에이전트가 참조하는 공통 운영 패턴 정의서.
Pathlight AI n8n commands에서 추출, ORBI 환경에 맞게 일반화.

---

## 4 Ops Patterns

### 1. EVALUATE (단독 건강 체크)

단일 리소스의 구조적 정합성을 검증한다.

| 항목 | 설명 |
|------|------|
| **대상** | 1개 워크플로우, 1개 캠페인, 1개 리포트, 1개 데이터 채널 |
| **체크** | credential 유효, 구조 정합성, 필수 필드 존재, 참조 무결성 |
| **출력** | `PASS` / `NEEDS_FIXES` / `BLOCKED` |
| **심각도** | CRITICAL → WARNING → INFO 3단계 |

**리포트 포맷:**
```markdown
## Evaluate: {resource name}
**Status**: PASS / NEEDS_FIXES / BLOCKED

### CRITICAL (반드시 수정)
- [{component}] {issue} → Fix: {specific instruction}

### WARNING (수정 권장)
- [{component}] {issue}

### INFO (참고)
- [{component}] {observation}

### Summary: {X} critical, {Y} warning, {Z} info
```

**원칙:**
- 항상 최신 데이터로 검증 (캐시 불가)
- 불확실하면 WARNING 이상으로 분류
- 수정 방법을 구체적으로 제시 (파라미터 값, 코드 라인 등)

---

### 2. AUDIT (크로스 리소스 감사)

여러 리소스 간 일관성을 검증한다.

| 항목 | 설명 |
|------|------|
| **대상** | WF↔WF, 채널↔채널, 입력↔출력, 환경↔환경 |
| **체크** | 필드명 일치, 스키마 호환, credential 통일, 값 범위 정합 |
| **출력** | Blast Radius 테이블 + 불일치 목록 |
| **판단** | case-sensitive, 보수적 (불확실 → HIGH risk) |

**리포트 포맷:**
```markdown
## Audit: {resource group}
**Resources**: {list}

### Shared Resources
| Resource | Type | Used By |
|----------|------|---------|

### CRITICAL — Mismatches
| Field | Source A | Source B | Issue |
|-------|---------|---------|-------|

### WARNING — Potential Issues
| Issue | Resources | Details |
|-------|-----------|---------|

### Verdict: CLEAN / ISSUES_FOUND
```

**원칙:**
- 모든 리소스를 먼저 fetch 후 분석 (순차 분석 금지)
- case-sensitive 비교 (공백, 대소문자 차이 = 불일치)
- 정답(canonical name)을 함께 제시

---

### 3. FIX (표준 수정 절차)

리소스를 안전하게 수정하는 5단계 표준 프로세스.

```
Step 1: FRESH READ    → 최신 상태 가져오기 (old cache 절대 재사용 금지)
Step 2: PLAN          → 변경 계획 제시 (무엇을, 왜, side effects)
Step 3: MODIFY        → 프로그래밍 방식으로 수정 (수동 편집 금지)
Step 4: APPLY         → 변경 반영 (API PUT, DB UPDATE, file write)
Step 5: VERIFY        → re-read로 변경 검증 + Auto-QA (evaluate 경량 실행)
```

**핵심 규칙:**
- 여러 변경은 1회 read→modify→write 사이클로 배치
- 적용 후 반드시 re-read 검증 (PUT 200 ≠ 성공)
- Auto-QA: evaluate 체크리스트 경량 버전 자동 실행
- 실패 시 원본 복원 가능해야 함 (백업 먼저)

**리포트 포맷:**
```markdown
## Fix Applied: {resource name}

### Changes Made
| Component | Change | Verified |
|-----------|--------|----------|
| {name} | {description} | Yes/No |

### QA Results
- Structural: PASS/FAIL
- Domain-specific: PASS/FAIL/N/A
- Issues found: {list or "None"}
```

---

### 4. IMPACT (변경 영향도 분석)

변경을 실행하기 전에 blast radius를 사전 파악한다.

| 항목 | 설명 |
|------|------|
| **시점** | 변경 실행 전 (Plan 이전) |
| **분류** | field rename/add/remove, logic, schema, credential, behavior |
| **출력** | Break Risk 매트릭스 + 태스크 순서 |
| **판단** | 보수적 (불확실 → HIGH risk) |

**Break Risk 수준:**
- **HIGH**: 수정 안 하면 반드시 깨짐
- **MEDIUM**: 특정 조건에서 깨질 수 있음
- **LOW**: 기능은 정상, 표면적/비핵심 영향

**리포트 포맷:**
```markdown
## Impact Analysis: {change description}

### Blast Radius
| Resource | Components Affected | Break Risk | Notes |
|----------|-------------------|------------|-------|

### Implementation Tasks (dependency order)
1. {task} — {resource} → {component} — Break risk: {level}
   Must be done before: {dependent task #}

### Pre-Implementation Checklist
- [ ] 현재 상태 백업
- [ ] 스키마 변경 먼저 (필드 변경 시)
- [ ] 활성 실행 없음 확인

### Estimated Effort
- Resources to modify: {N}
- Components affected: {N}
- Approach: sequential / parallel
```

---

## 에이전트별 적용 가이드

| 에이전트 | Evaluate | Audit | Fix | Impact |
|---------|----------|-------|-----|--------|
| n8n-manager | WF 구조 검증 | PROD↔WJ TEST 일치 | REST-first 수정 | 필드 변경 blast radius |
| amazon-ppc | 캠페인 건강체크 | 3브랜드 ACOS 일관성 | propose→execute | bid/budget 영향도 |
| data-keeper | 채널 freshness | 9채널 cross-check | credential reload | 채널 중단 downstream |
| golmani | DK 테이블 가용성 | KPI 탭 간 정합 | validator 피드백 | COGS/가격 변경 영향 |
| CFO | 감사 체크리스트 | 골만이↔DK 교차 | REVISE loop | ESCALATE 범위 |
| communicator | 발송 가능 여부 | state↔실제 일치 | reset-state | 미발송 인지지연 |
| codex-auditor | CLI+API 가용성 | exec↔verifier 교차 | prompt 재구성 | N/A |
| 제갈량 | sub-skill 가용성 | ALPHA↔BRAVO 교차 | Codex 감사 반영 | 전략 실행 영향 |

---

## Dependency Registry 구조 (Impact 분석용)

각 에이전트 도메인에 맞게 관리:

```yaml
# 예시: n8n dependency registry
workflows:
  Draft Generation (0q9uJUYTpDhQFMfz):
    reads:
      - {table: Creators, fields: [Name, Email, Status, Draft Status]}
    writes:
      - {table: Creators, fields: [Draft Status, Draft Content, Draft Date]}
    credentials:
      - rIJuzuN1C5ieE7dr (Shopify)
      - 59gWUPbiysH2lxd8 (Airtable)
    triggers: [schedule]
    downstream: [Approval Send]
```

```yaml
# 예시: data-keeper dependency registry
channels:
  amazon_ads_daily:
    api: Amazon Ads API v3
    credentials: [AMZ_ADS_CLIENT_ID, AMZ_ADS_REFRESH_TOKEN_*]
    downstream: [PPC Agent, KPI Monthly, Communicator]
    freshness_threshold: 14h
```

이 레지스트리는 처음에 수동 구축, 이후 변경 시마다 업데이트.
