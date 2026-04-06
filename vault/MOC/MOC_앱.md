---
type: moc
domain: app
agents: [appster, shopify-ui-expert]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [app, onzenna, shopify, nextjs, django]
---

# MOC_앱

## 에이전트
- **appster** — ONZ APP 풀스택 배포 + E2E 테스트 (Next.js + Django + Supabase)
- **shopify-ui-expert** — Shopify 4 UI domains (Checkout UI Extensions, Liquid, Polaris, Hydrogen)

## ONZ APP 아키텍처
- Frontend: Next.js 16 (Vercel)
- Backend: Django REST (EC2)
- Auth: Supabase

## API 엔드포인트 (Django)
| 엔드포인트 | 용도 |
|-----------|------|
| `/api/onzenna/pipeline/creators/` | 크리에이터 CRUD |
| `/api/onzenna/pipeline/creators/stats/` | 파이프라인 통계 |
| `/api/onzenna/pipeline/conversations/` | 대화 기록 |
| `/api/onzenna/pipeline/config/{date}/` | 일별 Config |
| `/api/onzenna/pipeline/email-config/` | 브랜드별 이메일 설정 |
| `/api/onzenna/gmail-rag/bulk-check/` | RAG 이메일 중복 확인 |
| `/api/datakeeper/query/?table=content_posts` | 콘텐츠 데이터 |

Auth: Basic `admin:admin` (ORBITOOLS_USER/ORBITOOLS_PASS)

## Shopify 데이터 흐름
```
폼 데이터 → n8n → PostgreSQL → Airtable → Shopify Metafields
```
