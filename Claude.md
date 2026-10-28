# 절대 룰: orbitools / CRM 작업은 orbitools-code-edit MCP 우선

ORBITOOLS / WONGI 리포의 코드 (Django dashboard, Next.js intelligence_next,
JP CRM, US CRM, pipeline-crm) 를 **조회/수정** 하는 작업이면 무조건 먼저
`orbitools-code-edit` MCP 도구를 사용한다. GitHub API 직접 호출 / clone /
gh CLI 우회 금지.

트리거 키워드 (자동 발동):
- CRM (JP CRM / US CRM / pipeline-crm)
- orbitools / WONGI / intelligence dashboard
- pipeline_status / influencer status / conversation status
- "대시보드 고쳐" / "CRM 고쳐" / "status 변경 안 됨"

만약 등록된 MCP 도구로 해결 불가능한 경우에만 fallback (gh API / git).

---

# 절대 룰: 직접 파악할 수 있는 건 묻지 마

내가 직접 파악할 수 있는 정보(코드/로그/API/n8n execution/git/메모리/시트 등)는
**무조건 직접 조사**한다. 세은한테 (a)/(b)/(c) 식으로 객관식 묻기 금지.
세은한테 묻는 건 "조사해도 알 수 없는 것" + "정책/의도/판단" 뿐.

# 절대 룰: 세은 말이 틀렸으면 틀렸다고 냉정하게 말해

세은 의견에 무조건 동조하지 마라. 틀렸으면 근거 들고 "틀렸다"고 직설로 말한다.
맞장구 듣자고 대화하는 게 아니다 (세은 직접 지시 2026-07-21).
동의할 때도 세은이 말해서가 아니라 내 독립 근거로 판단한 결론이어야 한다.
"현 유지가 맞다" / "그 방향은 틀렸다" 둘 다 자유롭게 말할 것.

# 절대 룰: 검증 못 한 건 말하지 마라

검증 안 된 정보는 답변에서 **빼라**. "추정", "가능성", "~로 보입니다", "~인 듯" 라벨 붙여도 금지.
모르면 "확인 못 함" 한 줄로 끝. 절대 추측을 답변 본문에 섞지 마.

**검증 한 번 = 도구 한 개로 끝나면 안 됨.** 빈 결과/0건/오류는 "없음" 단정 근거가 아니라 "도구 실패 가능성" 신호. 반드시 두 번째 도구로 교차검증.

특히 Windows 자원(Task Scheduler/레지스트리/이벤트 로그/서비스):
- **PowerShell 우선** (`Get-ScheduledTask`, `Get-ItemProperty`, `Get-EventLog`)
- bash의 `schtasks`/`reg`/`sc`는 **cp949 출력**이라 `| grep` 매칭 깨짐 — 빈 결과 = 도구 실패
- bash + 한국어 도구 출력은 신뢰 X

---

# Session Startup

세션 시작 시 반드시:
1. 최근 60시간 git log: `git log --since="60 hours ago" --oneline --all`
2. `memory/` 의 가장 최근 `session_*.md` 읽어 이전 세션 맥락 파악
3. 미완료 작업 있으면 세은에게 먼저 알림

# Session End (자동)

세션 끝나기 전 (compact 전 / 세은이 마무리할 때):
1. `memory/session_YYYYMMDD.md` 에 오늘 요약 저장 (작업, 미완료, 피드백)
2. 인플루언서 메모리 중 상태 변경된 건 업데이트
3. MEMORY.md 세션 요약 섹션에 링크 추가/갱신

**세은이 "세션 정리해" 안 해도 알아서 저장한다. 절대 빼먹지 마.**

---

# WAT Architecture

확률적 AI = orchestration, 결정적 코드 = execution. 그 분리가 신뢰성을 만든다.

| 레이어 | 위치 | 역할 |
|---|---|---|
| **Workflows** | `workflows/*.md` | Markdown SOPs (목적/입력/도구/출력/예외) |
| **Agents** (너) | — | workflow 읽기 → 도구 시퀀스 실행 → 실패 처리 → 의도-실행 연결 |
| **Tools** | `tools/*.py` | API/데이터/파일/DB. 결정적, 테스트 가능 |

**도구 있으면 절대 직접 수동 실행 X.**

---

# Operating Principles

1. **기존 도구 먼저** — `tools/` 검색. 없을 때만 신규.
2. **실패에서 학습** — 에러 trace → tool fix → retest (유료 API는 사전 확인) → workflow 업데이트.
3. **워크플로우 갱신** — 더 나은 방법/제약/반복 이슈 발견 시 워크플로우 업데이트. 명시 허락 없이 덮어쓰기 X.

# File Structure

| 위치 | 용도 |
|---|---|
| `tools/` | Python 실행 스크립트 |
| `workflows/` | Markdown SOPs |
| `.tmp/` | 처리용, 폐기 가능 |
| `.env` | 시크릿 (다른 곳에 보관 X) |
| `credentials.json` / `token.json` | Google OAuth (gitignored) |

**최종 산출물은 Sheets/Slides/Cloud로**. 로컬 파일은 처리용만.

# Auto-Load Rule

DM (JA/KR) 또는 인플루언서/インフルエンサー 멘션 시:
1. `workflows/grosmimi_japan_influencer_dm.md` 즉시 읽기
2. 현재 STEP 식별
3. 답장 초안 (일본어 원문 + 한국어 번역)

---

# Harness (Builder ↔ Auditor 2-Loop)

모든 산출물 → OpenAI Codex Auditor 2회 루프 검사 후 보고.

| 업무 | type | 시점 |
|---|---|---|
| 인플루언서 DM | `dm` | 초안 후 보여주기 전 |
| Python 코드 | `code` | 새 스크립트/큰 수정 후 |
| n8n 워크플로우 | `workflow` | 생성/수정 시 |
| IG 기획안 | `ig_plan` | 주간 기획안 후 |
| KPI/리포트 | `report` | 데이터 생성 후 |
| PPC 실행 | `ppc` | 입찰/예산 변경 시 |

```
Builder → Auditor Loop 1 → (위반 시) 자동 수정 → Auditor Loop 2 → 세은 보고
```

CLI:
```bash
PYTHONIOENCODING=utf-8 python tools/harness.py --type dm --file draft.txt
PYTHONIOENCODING=utf-8 python tools/harness.py --status
```

규칙:
- DM은 반드시 Harness 통과 후 세은에게 보여줌
- PASS(80+) 즉시 / FAIL이면 위반사항 + 수정본 함께
- 결과 `.tmp/harness_results/`, 로그 `.tmp/auditor_logs/`
- `PYTHONIOENCODING=utf-8` 필수 (cp949 방지)

---

# 에이전트 (스킬 anchor)

호출 시 `.claude/skills/<name>/SKILL.md` 읽고 진행.

| 트리거 | 스킬 | 영역 |
|---|---|---|
| 쿠텐이, 라쿠텐, KSE, 발송메일, 주문확인, 송장번호 | `쿠텐이` | Rakuten JP 주문 운영 |
| 마존이, Amazon JP, 아마존 주문 | `마존이` | Amazon JP 운영 |
| 인획이, IG 기획 | `인획이` | IG 콘텐츠 기획 |
| 리공이, DM 자동화, 계약서 발송, DocuSeal, ManyChat | `리공이` | DM/계약 n8n 파이프라인 |
| 인플루언서 매니저, 계약서, 협상 | `influencer-manager` | DM 답장 + 계약서 DOCX |
| ツイッター부대, 트위터 부대, 총감독, 감독, 기획맨, 코멘터, 조사맨 | `twitter-squad` | @grosmimi_jp 통합 운영 |
| 골만이, DCF, LBO, 피치덱, IB, M&A | `golmani` | Investment Banker |
| CFO, 재무검토, 골만이 감사 | `cfo` | CFO orchestrator |
| 감사관, 회계감사, AICPA | `auditor` | 감사 (Evaluator) |
| 자료 찾기, 파일 찾아줘, 카톡 파일, 인보이스 정리 | `resource-finder` | 내부 파일 + Gmail 검색 |
| 커뮤니케이터, 상태 이메일, 리포트 발송 | `communicator` | 12h 상태 이메일 |
| 깍두기 | `깍두기` | 잡무 전담 |
| 제갈량, 갈량이, CSO, 전략회의, 우선순위 | `제갈량` | 시스템 총괄 전략 |
| 아인슈타인 | `아인슈타인` | 효율/창의성 감사 |
| 리포터 | `리포터` | KPI/광고 리포트/대시보드 |
| 삐삐, RPP, JP PPC, 키워드 입찰, 키워드CPC, 目安CPC | `삐삐` | JP 유료검색 (RPP·AMZ JP SP) 입찰·키워드·예산 |
| 틱톡이, 틱톡 광고, 틱톡 ads, TikTok Ads, GMV Max, Spark Ads, VSA, LSA, 틱톡샵, TikTok Shop, TTS, 틱톡 어필리에이트 | `틱톡이` | TikTok 광고 + 틱톡샵 통합 어드바이저 (근거 제시 의무) |
| 릴스 번역, 번역 | `reel-translator` | EN→JA 자막 번역 |
| 데이터크롤러, 추출, 필터, 뽑아줘 | `data-crawler` | 시트/엑셀 추출 |
| firecrawl, 웹 검색, 웹 작업 | `firecrawl` | 모든 웹 작업 (WebFetch/Search 대체) |
| reflect | `reflect` | 세션 자동 학습 |
| /장보고, 일일 보고, 데일리 리포트, 오늘 한 거 정리해 | `daily-report` | CRM 진척 + 메타 광고 + 기타 작업 PDF |
| 주간 덱, JP 주간 덱, 주간 발표 덱, weekly deck | `jp-weekly-deck` | JP Meta 주간 발표 덱 (Weekly Performance Read) |

Python 경로 (전역): `/c/Users/orbit/AppData/Local/Programs/Python/Python314/python`

---

# Data Keeper (Team Data Rules)

광고/매출 데이터 (Amazon, Meta, Google Ads, GA4, Klaviyo, Shopify) → MUST Data Keeper.

```python
from data_keeper_client import DataKeeper
dk = DataKeeper()
rows = dk.get("amazon_ads_daily", days=30)
rows = dk.get("meta_ads_daily", brand="Grosmimi", date_from="2026-03-01")
```

Fallback (자동): **PG API → NAS Cache → Local Cache**.

규칙:
1. ALWAYS `data_keeper_client.py` — API 직접 호출 금지
2. PG `gk_*` 테이블 쓰기 금지 (Data Keeper만 writer)
3. `../Shared/datakeeper/latest/` 수정 금지 (read-only)
4. 채널 부재 시 `../Shared/datakeeper/data_signals/` 에 signal YAML

채널 18개:
| Table | 내용 |
|---|---|
| amazon_ads_daily / search_terms / keywords / campaigns / brand_analytics | Amazon Ads |
| amazon_sales_daily | Amazon Sales (3 sellers) |
| meta_ads_daily / meta_campaigns | Meta Ads |
| google_ads_daily / search_terms | Google Ads |
| ga4_daily / klaviyo_daily / shopify_orders_daily / gsc_daily | GA4/Klaviyo/Shopify/GSC |
| dataforseo_keywords | SEO 랭킹 |
| content_posts / content_metrics_daily / influencer_orders | 인플루언서 콘텐츠/D+60/주문 |

PST 0:00 + 12:00 자동 갱신 (GitHub Actions). NAS 캐시는 Task Scheduler 동기화.

---

# 서버매니저 (Server Manager)

ORBI 인프라: Local SSD + NAS hybrid + EC2 + GitHub Actions.

| 컴포넌트 | 위치 | 용도 |
|---|---|---|
| **Local SSD** | `C:\Users\orbit\Desktop\SE` | 코드 편집, git, Claude Code |
| **NAS (Z:)** | `Z:\` | Data Storage, REFERENCE, credentials, .tmp |
| **GitHub** | `Orbiters-dev/SE` | 코드 + Actions |
| **EC2 orbiters_2** | `13.124.157.191` | DataKeeper Django + ONZ APP + PG |
| **EC2 n8n** | `n8n.orbiters.co.kr` | 워크플로우 엔진 |
| **Vercel** | ONZ APP (Next.js) | 프론트엔드 |
| **Supabase** | Free tier | ONZ APP 인증 |

### GitHub Actions 스케줄

| 워크플로우 | 시간 | 설명 |
|---|---|---|
| Data Keeper / Communicator | PST 0:00 + 12:00 | 18채널 수집 + 상태 이메일 |
| Twitter Slot Notify | X:55 (정각 부하 회피) | 트위터 슬롯 알림 |
| ツイッター部隊 (총감독/감독/기획맨/투고/코멘터) | JST 09:00 / 10:00 / 12-16 / 19:00 | 트위터 자동 운영 |
| 그로미미 컨텐츠 트래커 | KST 08:00 | Syncly 크롤링 + SNS 탭 |
| WL Codes Sync | 매시간 | Notion 인플루언서 코드 매칭 |

명령:
```bash
gh run list -R Orbiters-dev/SE --limit 10
curl -sk -u admin:PASS https://orbitools.orbiters.co.kr/api/datakeeper/status/
curl -sk https://n8n.orbiters.co.kr/healthz
```

규칙: `.tmp/`는 처리용만 — 최종 → `Data Storage/`. `.wat_secrets`는 `C:\Users\orbit\.wat_secrets`.

---

# kazuki 도구 (Rakuten / Amazon / Polar)

쿠텐이/마존이가 보조로 사용:

| 도구 | 역할 |
|---|---|
| `tools/rakuten_daily_report.py` / `rakuten_review_workflow.py` / `rakuten_rms_client.py` / `rms_review_playwright.py` / `rakuten_order_report.py` | Rakuten 일일/리뷰/RMS/주문 |
| `tools/send_rakuten_review_emails.py` / `send_approved_from_sheet.py` | 라쿠텐 리뷰 이메일 |
| `tools/amazon_daily_report.py` | Amazon 일일 리포트 |
| `tools/track_delivery.py` / `selector_notify.py` | 배송 추적/알림 |
| `tools/export_labels.py` / `generate_rakuten_banner.py` | 라벨/배너 |
| `tools/classify_polar_ads.py` / `polar_dashboard_builder.py` / `polar_financial_model.py` | Polar (광고 분류/대시보드/재무) |
| `tools/create_exhibition_schedule_notion.py` | 전시 스케줄 Notion |

추가 워크플로우: `workflows/grosmimi_monitor_recruitment.md`, `polar_dashboard_builder.md`, `polar_financial_model.md`

---

# 쇼피파이 테스터

"쇼피파이 테스터" 명령 시:
1. `workflows/shopify_tester.md` 읽기
2. 큐 상태: `python tools/shopify_tester.py --status`
3. pending 있으면 즉시: `python tools/shopify_tester.py --run`

큐 `.tmp/test_queue.json` / 결과 `.tmp/test_results.json`
