# Pipeliner Troubleshooting Guide

## n8n Server Issues

### Webhook 무응답 (HTTP 000 or timeout)

**증상**: POST to webhook returns connection error or times out.

**원인**: n8n Docker 컨테이너 내부 이상, webhook 등록 실패, 또는 Caddy reverse proxy 문제.

**해결**:
```bash
# SSH to EC2
ssh ubuntu@<n8n-ec2-ip>

# Clean restart (단순 restart로는 부족할 수 있음)
cd /home/ubuntu/n8n
docker compose down && docker compose up -d

# Check logs
docker logs n8n-n8n-1 --tail 50
docker logs n8n-caddy-1 --tail 20

# Verify containers running
docker ps
```

### Task Runner "Offer expired"

**증상**: n8n 실행 로그에 "Task runner: Offer expired" 에러.

**원인**: JS Task Runner가 task offer를 시간 내 수락하지 못함. n8n latest 이미지 불안정 가능.

**해결**: Clean restart. 재발 시 n8n 버전 고정 검토 (`n8nio/n8n:1.xx.x`).

### Caddy ERR_ERL_UNEXPECTED_X_FORWARDED_FOR

**증상**: Caddy 로그에 X-Forwarded-For 관련 에러.

**해결**: `.env`에 `N8N_PROXY_HOPS=1` 추가 후 재시작.

### EC2에서 자기 도메인 curl 실패

**증상**: EC2 내부에서 `curl https://n8n.orbiters.co.kr` 시 HTTP 000.

**해결**:
```bash
# 내부 루프백 사용
curl -sk https://127.0.0.1/ -H "Host: n8n.orbiters.co.kr"
# 또는 외부에서 테스트
```

## Airtable Issues

### 429 Rate Limit

**증상**: Airtable API 응답 429 Too Many Requests.

**원인**: 초당 5회 제한 초과.

**해결**: `dual_test_runner.py`에 내장된 0.2s delay. 대량 작업 시 `time.sleep(0.25)` 추가.

### Select 옵션 추가 불가

**증상**: API로 새 select/multi-select 옵션 추가 시 에러.

**해결**: `typecast: true`로 레코드 생성하면 자동 생성됨. 불필요한 레코드는 삭제.

## Shopify Issues

### Customer Not Found (Expected)

**증상**: Verifier가 Shopify customer를 찾지 못함.

**원인**: n8n은 `mytoddie.myshopify.com`에 고객 생성, 테스트는 `toddie-4080.myshopify.com` 확인.

**해결**: 이것은 expected behavior. Shopify 검증은 `critical: False`로 설정됨.

### Draft Order Verification

**증상**: Draft Order ID가 Airtable에 있지만 Shopify에서 조회 불가.

**원인**: 두 개 Shopify 스토어 간 데이터 불일치.

**해결**: Airtable의 Draft Order ID 값으로 간접 검증. Shopify API 직접 조회는 mytoddie 스토어에서만 가능.

## PostgreSQL Issues

### No DELETE Endpoint

**증상**: 테스트 데이터 PG 클린업 불가.

**원인**: onzenna Django API에 DELETE 엔드포인트 미구현.

**해결**: 수동 클린업 또는 API 엔드포인트 추가 필요. 현재는 warn 로그만 출력.

### orbitools API 접속 불가

**증상**: `curl https://orbitools.orbiters.co.kr` 실패.

**해결**:
```bash
# 인증 확인
curl -u admin:PASSWORD https://orbitools.orbiters.co.kr/api/onzenna/tables/

# EC2 상태 확인
# orbiters_2 인스턴스 SSH 접속 후
sudo systemctl status export_calculator
```

## Test Flow Issues

### FlowContext State Mismatch

**증상**: `--step N` 실행 시 변수 누락.

**원인**: 이전 step의 state가 저장되지 않았거나 다른 flow의 state 파일이 로드됨.

**해결**: `.tmp/influencer_flow_state.json` 삭제 후 step 1부터 재실행.

### n8n Schedule Trigger 수동 실행 불가

**증상**: schedule-trigger 워크플로우를 API로 트리거하면 405 에러.

**원인**: n8n API v1은 schedule-trigger 워크플로우의 수동 실행 미지원.

**해결**: webhook-triggered WF만 API로 실행 가능. Schedule WF는 구조 검증(`verify_n8n_workflow`)만 수행.

## Report Issues

### HTML 리포트가 열리지 않음

**증상**: `start ""` 명령이 작동하지 않음.

**해결**:
```bash
# 수동으로 열기
start "" "Z:\Orbiters\...\WJ Test1\.tmp\dual_test\dual_YYYYMMDD_HHMMSS\merged_report.html"

# 또는 경로 확인
python tools/dual_test_runner.py --results
```

## Pre-Flight Checklist

Before running dual test, verify:

1. **Environment variables**: `python tools/test_influencer_flow.py --status`
2. **n8n server**: `curl -sk https://n8n.orbiters.co.kr/healthz`
3. **Airtable API**: Check `AIRTABLE_API_KEY` in `~/.wat_secrets`
4. **orbitools API**: `curl -u admin:PW https://orbitools.orbiters.co.kr/api/onzenna/tables/`
5. **WJ TEST webhooks active**: Check n8n UI for gifting WF (`4q5NCzMb3nMGYqL4`) active status
