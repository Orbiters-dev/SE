# Tone

Talk casually like a coworker. Keep it short and conversational. No corporate speak, no filler. Just get to the point like you're on Slack.

---

# Session Startup

세션 시작 시 반드시 최근 60시간 git log를 확인하고, 주요 작업 맥락을 파악한 뒤 대화를 시작할 것.
명령: `git log --since="60 hours ago" --oneline --all`

---

# WAT Framework

**Workflows** (`workflows/`) → **Agents** (you) → **Tools** (`tools/`)

Rules:
- Always check existing `tools/` before building new scripts
- Final outputs go to `Data Storage/` — never `.tmp/`
- Secrets in `~/.wat_secrets` via `env_loader.py` — never in `.env`
- When errors occur: read trace → fix tool → retest → update workflow

---

# Data Keeper (Always-On Rule)

For ANY advertising/sales data (Amazon, Meta, Google Ads, GA4, Klaviyo, Shopify):

```python
from data_keeper_client import DataKeeper
dk = DataKeeper()
rows = dk.get("shopify_orders_daily", days=30)
```

- ALWAYS use `data_keeper_client.py` — never call APIs directly
- NEVER write to `gk_*` tables
- Fallback chain: PG API → NAS cache → local `.tmp` (automatic)

---

# Auto-Load: Influencer DM

일본어/한국어 DM이 컨텍스트 없이 오거나 인플루언서 아웃리치 언급 시:
→ `workflows/grosmimi_japan_influencer_dm.md` 읽고 단계 파악 후 답변 초안 작성

---

# Agent Routing

트리거 키워드 감지 시 → 해당 SKILL.md 먼저 읽고 실행

| 트리거 | SKILL.md | 주요 도구 |
|--------|----------|---------|
| 쇼피파이 테스터 | `workflows/shopify_tester.md` | `tools/shopify_tester.py` |
| 메타 테스터 | `workflows/meta_tester.md` | `tools/meta_tester.py` |
| 아마존 PPC 테스터 | `workflows/amazon_ppc_tester.md` | `tools/amazon_ppc_tester.py` |
| 구글 애즈 테스터 | `workflows/google_ads_tester.md` | `tools/google_ads_tester.py` |
| 그로미미 컨텐츠 트래커, 컨텐츠 트래커, SNS 탭, Syncly 동기화 | `.claude/skills/syncly-crawler/SKILL.md` | `tools/fetch_syncly_export.py` → `tools/sync_syncly_to_sheets.py` → `tools/sync_sns_tab.py` |
| 차앤맘 컨텐츠 트래커, chaenmom SNS | `.claude/skills/syncly-crawler/SKILL.md` | `tools/sync_sns_tab_chaenmom.py` |
| 아마존퍼포마, 퍼포마, Amazon PPC, PPC 분석, 입찰 최적화, ACOS | `.claude/skills/amazon-ppc-agent/SKILL.md` | `tools/amazon_ppc_executor.py` |
| 골만이, DCF, LBO, Comps, 피치덱, CIM, M&A, 밸류에이션 | `.claude/skills/golmani/SKILL.md` | `tools/generate_fin_data.py` |
| CFO야, 재무검토, 숫자검토, 감사관, 크로스체크, 재무감사, audit | `.claude/skills/cfo/SKILL.md` | `tools/cfo_harness.py` |
| 감사해줘, 회계감사, AICPA, KICPA, 내부감사 | `.claude/skills/auditor/SKILL.md` | `tools/cfo_harness.py --audit-file` |
| UI테스터야, 쇼피파이 UI, Checkout Extension, Liquid, n8n 웹훅 | `.claude/skills/shopify-ui-expert/SKILL.md` | `tools/deploy_*.py` |
| n8n 워크플로우, 워크플로우 복제, PROD WJ TEST, n8n 서버, n8n 재시작 | `.claude/skills/n8n-manager/SKILL.md` | n8n API |
| KPI 리포트, KPI 할인율, run_kpi_monthly, 월간 KPI, KPI 엑셀 | `.claude/skills/kpi-monthly/SKILL.md` | `tools/run_kpi_monthly.py` |
| 커뮤니케이터, 상태 이메일, 데이터 현황 이메일 | `.claude/skills/communicator/SKILL.md` | `tools/run_communicator.py` |
| 자료 찾기, 파일 찾아줘, 문서 검색, Gmail 검색, 카카오톡 파일 | `.claude/skills/resource-finder/SKILL.md` | `tools/send_gmail.py` |
| 앱스터, ONZ APP, onzenna app, Vercel 배포, EC2 onzenna | `.claude/skills/appster/SKILL.md` | `tools/deploy_onzenna.py` |
| 워크플로우 분석기, orphan tool, GitHub Actions 분석 | — | `tools/run_workflow_analyzer.py` |
| ppc시뮬이, 백테스팅, PPC 시뮬, 낭비절감 시뮬 | — | `tools/amazon_ppc_simulator.py` |
| 파이프라이너, 이중테스트, dual test, Maker-Checker | `.claude/skills/pipeliner/SKILL.md` | `tools/dual_test_runner.py` |
| 크롤러, Apify, content pipeline | — | `tools/fetch_apify_content.py` |
| 효율가 | — | `tools/run_skill_optimizer.py` |

Python 경로: `C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe`
