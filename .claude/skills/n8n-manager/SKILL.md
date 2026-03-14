---
name: n8n-manager
description: "n8n 워크플로우 관리 전문가. 워크플로우 조회/생성/수정/복제/마이그레이션, PROD-WJ TEST 환경 동기화, 노드 머지, 크레덴셜 관리, 서버 진단을 담당한다. n8n API, 워크플로우 복제, PROD WJ TEST 동기화, 노드 비교, 워크플로우 활성화, n8n 서버, n8n 재시작 관련 작업에 반드시 사용할 것."
---

# n8n Workflow Manager

n8n 셀프호스트 인스턴스의 워크플로우를 프로그래밍 방식으로 관리하는 스킬이다.
PROD ↔ WJ TEST 환경 간 워크플로우 동기화, 노드 머지, 크레덴셜 관리를 포함한다.

## When to Use This Skill

- n8n 워크플로우 조회/생성/수정/삭제
- PROD → WJ TEST 워크플로우 복제 또는 역방향 동기화
- 워크플로우 간 노드 비교 및 머지
- n8n 서버 상태 확인/재시작
- 워크플로우 활성화/비활성화
- 크레덴셜 관리
- n8n API 관련 트러블슈팅

## Infrastructure

| 항목 | 값 |
|------|-----|
| 인스턴스 | `orbiters-n8n-server` (EC2, `i-0ddaa6796683e8043`) |
| URL | `https://n8n.orbiters.co.kr` |
| API Key | `~/.wat_secrets` > `N8N_API_KEY` |
| Docker | `/home/ubuntu/n8n/docker-compose.yml` |
| 컨테이너 | `n8n-n8n-1` + `n8n-caddy-1` |

## Environments

| 환경 | Airtable Base | Shopify Store | 워크플로우 수 |
|------|--------------|---------------|-------------|
| **PROD** | `appNPVxj4gUJl9v15` | mytoddie.myshopify.com | 17 |
| **WJ TEST** | `appT2gLRR0PqMFgII` | toddie-4080.myshopify.com | 18 |

### 환경 식별 규칙
- WJ TEST: 이름에 `[WJ TEST]` 접두사, 태그 `wj-test-1`
- PROD: 접두사 없음, 태그 `Pathlight` 또는 `ICO`

## n8n API Reference

### 인증
```bash
curl -sk -H "X-N8N-API-KEY: $N8N_API_KEY" "$URL"
```
**Windows 필수**: `-sk` 플래그 (SSL revocation check 실패 방지)

### CRUD Operations

```bash
# 전체 조회
GET /api/v1/workflows?limit=100

# 단일 조회
GET /api/v1/workflows/{id}

# 생성 (active 필드 포함 금지!)
POST /api/v1/workflows
Body: { name, nodes, connections, settings }

# 수정 (name 필드 필수!)
PUT /api/v1/workflows/{id}
Body: { name, nodes, connections, settings }

# 활성화/비활성화
POST /api/v1/workflows/{id}/activate
POST /api/v1/workflows/{id}/deactivate

# 삭제
DELETE /api/v1/workflows/{id}
```

### API 주의사항

| 규칙 | 설명 |
|------|------|
| POST 시 `active` 필드 | **포함 금지** → 400 `active is read-only` |
| PUT 시 `name` 필드 | **필수** → 400 `must have required property 'name'` |
| Windows SSL | `curl -sk` 필수 (`CRYPT_E_NO_REVOCATION_CHECK`) |
| Python subprocess | cp949 인코딩 에러 → 파일로 출력 후 `rb` + `decode('utf-8')` |
| 응답 크기 | 큰 워크플로우 (50+ nodes) → 파일로 저장 후 처리 |

## Migration Patterns

### Pattern 1: 신규 복제 (PROD → WJ TEST)

```python
import json

# 1. PROD 워크플로우 다운로드
# curl -sk -o prod.json "$BASE/api/v1/workflows/$PROD_ID"

with open('prod.json', 'rb') as f:
    src = json.loads(f.read().decode('utf-8'))

# 2. 페이로드 정리 (필수 필드만, active 제외)
payload = {
    'name': '[WJ TEST] ' + src['name'],
    'nodes': src['nodes'],
    'connections': src['connections'],
    'settings': src.get('settings', {})
}

# 3. Airtable base 교체
payload_str = json.dumps(payload)
payload_str = payload_str.replace('appNPVxj4gUJl9v15', 'appT2gLRR0PqMFgII')

# 4. POST 생성
# curl -sk -X POST -d @payload.json "$BASE/api/v1/workflows"
```

### Pattern 2: 노드 머지 (PROD 노드 → 기존 WJ TEST에 추가)

```python
# 1. 양쪽 다운로드
# 2. PROD-only 노드 식별 (Sticky Note 제외)
prod_only = prod_node_names - wj_node_names
prod_only = {n for n in prod_only if 'Sticky Note' not in n}

# 3. 새 노드 위치 오프셋 (+800px, 겹침 방지)
for node in new_nodes:
    node['position'][0] += 800

# 4. 커넥션 머지
# - PROD-only 소스 노드: 전체 커넥션 복사
# - 공유 소스 노드: PROD-only 타겟 커넥션만 추가

# 5. Airtable base 교체
# 6. PUT 업데이트 (name 필수!)
```

### Pattern 3: 환경 비교

```python
# 전체 워크플로우 가져와서 분류
for w in all_workflows:
    if '[WJ TEST]' in w['name']:
        wj_test.append(w)
    else:
        prod.append(w)

# 이름 기반 매칭으로 페어 구성
# 노드 이름 set 차이로 PROD-only / WJ TEST-only 식별
```

## Credential References

| ID | 이름 | 타입 | 환경 |
|----|------|------|------|
| `rIJuzuN1C5ieE7dr` | Shopify Admin API (Gifting) | httpHeaderAuth | PROD + WJ TEST |
| `59gWUPbiysH2lxd8` | Airtable PAT (WJ Test) | httpHeaderAuth | WJ TEST |

## Server Management

### 상태 확인
```bash
# SSH 접속
ssh ubuntu@<n8n-ec2-ip>

# 컨테이너 상태
docker ps

# 로그 확인
docker logs n8n-n8n-1 --tail 50
docker logs n8n-caddy-1 --tail 20
```

### 클린 재시작
```bash
cd /home/ubuntu/n8n && docker compose down && docker compose up -d
```

### 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| webhook 200 + 빈 body | Task Runner "Offer expired" | 클린 재시작 |
| webhook HTTP 000 | Caddy trust proxy 미설정 | `N8N_PROXY_HOPS=1` 추가 |
| EC2에서 자기 도메인 curl 실패 | 루프백 불가 | `curl -sk https://127.0.0.1/ -H "Host: n8n.orbiters.co.kr"` |
| API 응답 인코딩 깨짐 | 한글 워크플로우 이름 | 파일 저장 후 `utf-8` 디코딩 |

## PROD Workflow Inventory (17, as of 2026-03-13)

| # | ID | 이름 | 상태 | WJ TEST 대응 |
|---|------|------|------|-------------|
| — | — | (PROD 워크플로우 목록을 `GET /api/v1/workflows` 로 조회해 채울 것) | — | — |

> **TODO**: PROD 인벤토리를 실제 API 조회로 채워야 함. `curl -sk -H "X-N8N-API-KEY: $KEY" https://n8n.orbiters.co.kr/api/v1/workflows?limit=100` 실행 후 업데이트.

## WJ TEST Workflow Inventory (18, as of 2026-03-13)

| # | ID | 이름 | 노드 | 상태 |
|---|------|------|------|------|
| 1 | `0q9uJUYTpDhQFMfz` | Draft Generation | 49 | Active |
| 2 | `mmkBpmvhzbgmSayh` | Approval Send | 16 | Active |
| 3 | `nVtYmhU0InRqRn4K` | Reply Handler | 50 | Active |
| 4 | `4q5NCzMb3nMGYqL4` | Gifting | 12 | Active |
| 5 | `734aqkcOIfiylExL` | Gifting2 → Draft Order | 14 | Inactive |
| 6 | `UP1OnpNEFN54AOUn` | Fulfillment → Airtable | 37 | Active |
| 7 | `Vd5NiKMwdLT7b9wa` | Sample Sent → Complete | 7 | Active |
| 8 | `2vsXyHtjo79hnFoD` | Shipped → Delivered | 11 | Active |
| 9 | `82t55jurzbY3iUM4` | Delivered → Posted | 8 | Active |
| 10 | `FT70hFR6qI0mVc2T` | Syncly Metrics Sync | 5 | Inactive |
| 11 | `wyttsPSZJlWLgy86` | Customer Lookup | 5 | Active |
| 12 | `zKmOX0tEWi6EBT9h` | Content Tracking | 23 | Active |
| 13 | `6BNQRz57oCtdROlH` | Syncly Data Processing | 64 | Active |
| 14 | `CEWr3kQlDg07310Y` | Full Pipeline (archive) | 68 | Inactive |
| 15 | `YCZuTAsHK2Ja6kIs` | AI Outreach (archive) | 61 | Inactive |
| 16 | `5BG7Qe7HtsbD4iP0` | Docusign Contracting | 14 | Inactive |
| 17 | `k08R16VJIuSPdi6T` | ManyChat Automation | 13 | Inactive |
| 18 | `fJd4tZkBmmB2bdHJ` | Fulfillment (archive) | 26 | Inactive |

## PROD-WJ TEST Config Pattern Difference

| 패턴 | PROD | WJ TEST |
|------|------|---------|
| Config 소스 | Airtable Dashboard 테이블 (Fetch Dashboard + Fetch Today Config) | Google Sheets (Read Config Sheet) |
| 활성화 제어 | `Is Active?` IF 노드 (Config에서 on/off) | 없음 (항상 활성) |
| Config 대기 | `Wait for Config` Merge 노드 | 없음 (직접 읽기) |
| 에러 핸들링 | `Stop: No Email`, `Stop: Missing Email` StopAndError | 없음 (Notify만) |

PROD Config 패턴이 더 안정적 (중앙 제어 + 에러 차단). 2026-03-13 머지로 WJ TEST에도 추가됨.
