---
type: moc
domain: pipeline
agents: [pipeliner, syncly-crawler, n8n-manager, creator-evaluator, deep-crawler, social-evaluator]
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [pipeline, creator-collab, n8n, syncly]
---

# MOC_파이프라인

## 에이전트
- **pipeliner** — E2E 이중테스트 (Maker-Checker)
- **syncly-crawler** — 콘텐츠 메트릭 수집 (US + JP)
- **n8n-manager** — n8n 워크플로우 관리
- **creator-evaluator** — LT/HT 2-Tier 크리에이터 품질 평가
- **deep-crawler** — Apify IG/TikTok 프로필 + 포스트 크롤러
- **social-evaluator** — CI sub-score 백테스트 + 가중치 최적화

## n8n Workflow IDs
| WF | ID | 용도 |
|----|----|----|
| Draft Gen | fwwOeLiDLSnR77E1 | AI 이메일 생성 + 발송 |
| Syncly Data | l86XnrL1JPFOMSA4GOoYy | Creator/Content sync |
| Reply Handler | K99grtW9iWq8V79f | 회신 처리 |
| Fulfillment | ufMPgU6cjwuzLM0y | Shopify 주문 + 가이드라인 |

## 파이프라인 흐름
```
Poll (Not Started) → Batch Extract
  → US Only filter → Business Account filter
  → Apify Autofill → RAG Email Dedup
  → Build Claude Prompt → Claude Generate Draft
  → Parse + CC1-4 → Cross-Check Gate
  → Send Email / Gmail → Update RAG Contact
```

## Error Logs
- [[errlog_conversations_api_filter]] — `?email=` vs `?creator_email=` 불일치
- [[errlog_auto_email_send_incident]] — n8n 자동발송 사고 (321건)
- [[errlog_hashtag_classification_tautology]] — `t in tag_set` 항등식 버그

## Feedback
- [[feedback_pipeline_accuracy]] — 1-form pipeline, Gifting2 금지
- [[feedback_n8n_at_pg_migration]] — AT→PG 전체 한번에. 37개 규칙
- [[feedback_propose_execute_ux]] — Syncly 메트릭 필수, 자동발송 금지
- [[feedback_n8n_gmail_node]] — Gmail Send 노드는 PG 교체 금지
- [[feedback_email_draft_structure]] — EmailReplyConfig 기반 구조화

## 브랜드 매핑
| 브랜드 | 담당자 | 발신자 | Form URL |
|--------|--------|--------|----------|
| Grosmimi | Jeehoo | Jane Jeon | /influencer-gifting |
| CHA&MOM | Laeeka | Laeeka | /influencer-gifting-chamom |
| Naeiae | Soyeon | Selina | /influencer-gifting-naeiae |

## Projects
- [[project_creator_evaluator]] — LT/HT 2-Tier 크리에이터 품질 평가 (2026-04-08~)
- [[project_social_deep_crawler]] — Apify IG/TikTok 소셜 딥크롤러 + enricher
- [[project_social_evaluator]] — CI 서브스코어 백테스트 + 가중치 최적화

## Architecture
- [[pipeline_data_architecture]]
- [[pipeline_dashboard_ui]]
