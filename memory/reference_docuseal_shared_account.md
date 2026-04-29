---
name: DocuSeal 계정 구조 (docuseal.orbiters.co.kr 공유)
description: DocuSeal OSS Community는 인스턴스당 account 1개. 세은/ONZ가 같은 계정·API 키 공유 중. "user 이메일만 바꿔도 account는 그대로" 주의.
type: reference
---

## 핵심 사실 (2026-04-23 확인)

- **URL**: `https://docuseal.orbiters.co.kr`
- **등록 user**: 1명 (id=1, seeun heo, grosmimi.jpsns@gmail.com)
- **ONZ n8n 워크플로우 HeJt**에도 **동일한 API 키**가 하드코딩됨 → 세은 계정을 ONZ도 공유
- DocuSeal OSS Community는 `/api/accounts` 엔드포인트 자체가 없음 (HTTP 404). **인스턴스당 account 1개 구조**
- user 이메일 변경은 account 분리가 아님 — API 키/submissions/webhooks 모두 그대로

## 등록된 Webhook URL (2026-04-23 기준)

| id | URL | 용도 |
|----|-----|------|
| 1 | `https://n8n.orbiters.co.kr/webhook/docuseal-signed` | ONZ Contracting (HeJt) |
| 2 | `https://n8n.orbiters.co.kr/webhook/jp-docuseal-webhook` | Grosmimi JP Pipeline (ynMO) |

DocuSeal은 모든 submission 이벤트를 등록된 **전체 webhook URL**에 브로드캐스트 → ONZ와 JP가 서로의 이벤트를 교차 수신. **external_id 프리픽스로 구분 필수**.

## JP 수동 발송 도구 규칙

`tools/send_docuseal_contract.py` 는 submission 생성 시 **`external_id="GROSMIMI_JP_<timestamp>"`** 자동 삽입 (2026-04-23 수정).

ONZ 측 HeJt 워크플로우는 external_id 프리픽스 필터 미적용 상태 → William/ONZ팀에 수정 요청 보류.

## 향후 "계정 분리"를 요청받을 때 주의

- **같은 URL 안에서 user 이메일만 바꾸는 방식은 분리 아님** — 세은이 착각할 수 있는 포인트
- 진짜 분리는 **별도 DocuSeal 인스턴스**(docuseal-onz.xxx 등) 또는 **DocuSeal Pro 업그레이드** 필요
- ONZ 측 워크플로우의 API 토큰이 세은 것과 동일 → 세은이 API 키 rotate 시 ONZ도 즉시 고장남. rotate 전 ONZ팀 통보 필수
