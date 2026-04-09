---
type: moc
domain: home
status: active
created: 2026-04-06
updated: 2026-04-06
tags: [home, moc, top-level]
---

# ORBI Knowledge Vault — 홈 MOC

> Claude + Obsidian 연동 지식 베이스. 에이전트별 진입점.

## 도메인 MOC

| MOC | 도메인 | 핵심 에이전트 |
|-----|--------|--------------|
| [[MOC_광고]] | Amazon PPC, Meta Ads, Google Ads | amazon-ppc-agent, meta-ads-agent |
| [[MOC_파이프라인]] | Creator Collab Pipeline, n8n | pipeliner, syncly-crawler, n8n-manager |
| [[MOC_재무]] | KPI, Margin, Golmani, Audit | golmani, auditor, cfo, kpi-monthly |
| [[MOC_인프라]] | EC2, DataKeeper, LightRAG, DocuSeal | data-keeper, communicator |
| [[MOC_앱]] | ONZ APP, Shopify UI | appster, shopify-ui-expert |
| [[MOC_운영]] | 제갈량 CSO, Mistakes, WAT | 제갈량, resource-finder |

## 빠른 링크

### Error Logs
- [[errlog_ppc_config_override]]
- [[errlog_search_term_timeout]]
- [[errlog_autocomplete_wrong_metric]]
- [[errlog_conversations_api_filter]]
- [[errlog_auto_email_send_incident]]
- [[errlog_hashtag_classification_tautology]]

### Feedback
- [[feedback_pipeline_accuracy]]
- [[feedback_n8n_at_pg_migration]]
- [[feedback_propose_execute_ux]]
- [[feedback_n8n_gmail_node]]
- [[feedback_nodata_datakeeper]]
- [[feedback_email_draft_structure]]

### Projects
- [[project_lightrag]]
- [[project_docuseal]]
- [[project_pathlight_n8n_migration]]
- [[project_ppc_sku_golmani]]
- [[project_search_ranking]]
- [[project_creator_evaluator]]
- [[project_social_deep_crawler]]
- [[project_social_evaluator]]

### Architecture
- [[attribution_url_classification]]
- [[pipeline_data_architecture]]
- [[pipeline_dashboard_ui]]
- [[mistakes]]

## Key Architecture

- **WAT Framework:** Workflows → Agents → Tools
- **Skills:** `.claude/skills/{name}/SKILL.md`
- **Python:** `C:/Users/user/AppData/Local/Programs/Python/Python314/python.exe`
- **Credentials:** `~/.wat_secrets` (primary), `.env` (fallback)
