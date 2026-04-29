---
name: Team Claude Guardrails (ORBI Shared Repo)
description: WJ-Test1 + ORBI 공유 리포에서 Claude가 따라야 할 규칙. no-touch zones, git hygiene, scope discipline, 원준 승인 필요 케이스.
type: reference
---

# Team Claude Guardrails — ORBI Shared Repo

WJ-Test1 / Orbiters-dev 리포에서 작업할 때 필수 준수. SE 로컬 리포에도 정신 적용.

## 1. No-touch zones (원준 wonjunchoi22@gmail.com 승인 필수)

### DataKeeper / Pipeline (owner: 원기/희찬)
- `tools/data_keeper.py` — PG `gk_*` 테이블 sole writer
- `tools/database.py` — `_normalize()` 12 필드 매핑. 컬럼 rename 하면 전체 파손
- `tools/config.py` — DB auth
- `onzenna/` — gunicorn port 8001 Django 앱
- `onzenna/views.py` — `/api/datakeeper/query/` + auto-sync hooks
- `onzenna/models.py` — `gk_content_posts`, `ContentPosts.post_id UNIQUE`
- `onzenna/migrations/*` — add/edit/run 전부 금지
- **PG 스키마**: `gk_content_posts`, `gk_content_metrics_daily`, `gk_pipeline_*` — column rename, index drop (특히 `comments_30d`), auth alter 금지
- **고정값**: `content_source='legacy'`, `analysis_tier`

### 활성 workflows (절대 트리거 금지)
- `.github/workflows/deploy_ec2.yml` — EC2 프로덕션 배포
- `.github/workflows/data_keeper.yml` — 일 2회 18채널 ingest
- `.github/workflows/run_migration.yml`

**판단 기준**: `grep gk_content_posts | gunicorn | ContentPosts | data_keeper` 매칭되면 read-only.

## 2. Safe zones
- `tools/*.py` (위 no-touch 제외)
- `docs/financial-dashboard/`, `docs/jp-amazon-dashboard/`, `docs/ppc-dashboard/`, `docs/content-dashboard/`, `docs/pipeline-dashboard/`
- `.claude/`, `.github/workflows/` (위 3개 제외)
- `memory/`, `workflows/`, `CLAUDE.md`

## 3. Git hygiene (매 세션 시작)

```bash
git fetch origin
git status --short
git stash list                        # 이전 Claude parked work 확인
git log --oneline origin/main -5
```

Push 전:
```bash
git pull --rebase --autostash origin main
```

**금지:**
- `git push --force` / `-f` on main
- `git reset --hard` with uncommitted
- `git checkout -- <file>` 확인 없이
- `git stash drop` / `git stash clear` (stash에 recovered work 있을 수 있음 — 2026-04-20 사고)
- 남의 auto-generated 큰 파일 (`fin_data.js`, `lightrag/rag_storage/*`) 함께 커밋

**예기치 못한 파일 보이면**: `git stash push -m "parking-$(date +%s)" -- <files>` 로 보관, 원준에게 문의.

## 4. Scope discipline
one commit = one owner. 커밋 전에 매 파일 → 담당자 매핑. 불명확하면 물어봄.

## 5. Deploy awareness

| Dashboard | 서빙 | 반영 시점 |
|-----------|------|---------|
| Financial KPIs | GitHub Pages + EC2 scp | Pages 2분 / EC2 financial_dashboard.yml 08:30 KST |
| PPC | EC2 scp | ppc_dashboard_action.yml 2시간 주기 |
| Django API (/api/datakeeper/*) | EC2 gunicorn | **deploy_ec2.yml — 허가 없이 절대 트리거 금지** |

## 6. Pre-commit checklist

```bash
# 문법
python -c "import ast; ast.parse(open('tools/FILE.py', encoding='utf-8').read())"
# Harness (선택)
PYTHONIOENCODING=utf-8 python tools/harness.py run --type code --file tools/FILE.py --gate build
# No-touch 확인
git diff --cached --name-only | grep -E "^(tools/data_keeper|tools/database|tools/config|onzenna/)" && echo "BLOCKED" || echo "OK"
# 스코프
git diff --cached --stat
```

## 7. Communication

| 상황 | 연락 |
|------|------|
| 파괴적 git 작업 전 (reset, force-push, branch -D, stash drop) | 원준 |
| DataKeeper / onzenna / gk_* 터치 | 원기 or 희찬 |
| 파일 owner 불명확 | 원준 |
| 이전 Claude work 잃어버린 게 발견됨 (stash, reflog) | 복구 먼저 → 사후 보고 |

**원준 이메일**: wonjunchoi22@gmail.com

## 8. 관련 사고 이력
- `memory/mistakes.md` #10 (EC2 freeze pattern)
- `memory/mistakes.md` #11 (Pipeline protection, 2026-04-20 원기)
- `memory/session_20260420.md` — CFO work auto-rebase stash 손실 사고

## TL;DR
- **No-touch**: DataKeeper, `onzenna/`, migrations, `deploy_ec2.yml`, `run_migration.yml`, PG 스키마
- **Always**: `git fetch + status + stash list` 먼저, push 전 `pull --rebase --autostash`
- **Never**: force-push main, stash drop, 남 파일 commit
- **Always**: one-owner-per-commit, 불명확 시 원준에게 문의
