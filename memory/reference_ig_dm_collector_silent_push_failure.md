---
name: IG DM KPI 과소집계 = 수집 파이프라인 무음 정지 (push 실패 삼킴)
description: IG DM KPI 리치아웃/계약 과소집계 = ig_dm_collector 수집이 멈춘 것. 근본원인=daily 워크플로우 커밋스텝 `git push || echo` 가 실패 삼켜 잡 성공처리→경보·워치독 둘 다 무음. 수동복구+CI 수리 완료(2026-09-10).
type: reference
---

## 증상 → 원인 (2026-09-10 규명)

**증상**: KPI 탭 9월 리치아웃·계약서 수령 수 과소집계. (9월 리치아웃 152 표시, 실제 252)

**원인 체인**:
1. `ig_dm_kpi_daily.yml` 자동수집이 **2026-09-07 15:50 이후 중단** (원장 자동커밋 9/8~9/10 전무, 원장 최신 메시지 9/8 00:08).
2. 근본: 커밋 스텝이 `git push || echo "[WARN] Push failed"` → **푸시 실패해도 잡이 "성공"으로 종료**.
   - `alert-failure`(needs 잡 실패 시만 발동) 안 울림.
   - `ig_dm_kpi_watchdog.yml`(오늘 "성공 런 존재" 여부만 체크) 도 "성공했네" 넘어감.
   - = **완전 무음 3일**.
3. 이중 타격: 수집 멈춘 사이 활발한(=전환되는) 스레드가 **20메시지 캡** 초과 → 리치아웃 첫 발신 메시지가 창 밖으로 유실 → 리치아웃·계약 **둘 다** 과소. (capped 79스레드 중 계약 69건이 소급불가)

## 복구 절차 (재현용)
```bash
PYTHONIOENCODING=utf-8 python tools/ig_dm_collector.py         # 토큰 자동갱신+수집 (994→1094 스레드 복구)
PYTHONIOENCODING=utf-8 python tools/ig_dm_kpi_aggregate.py     # 시트 재집계 (9월 리치아웃 152→252)
git add data/ig_dm_ledger.json && git commit && git push       # 원장 영속화 (리모트 충돌 시 내 복구본이 superset → checkout --theirs)
```
- 충돌 시 검증: 리모트 vs 로컬 peer 집합 차 = 0 확인 후 로컬(누적 superset) 채택. (`git show :2:/:3: 파일 | 스레드수 비교`)

## CI 수리 (2026-09-10 커밋 921a57e7)
- 커밋 스텝 → **push 5회 재시도 후 실패 시 `exit 1`(잡 fail)** 로 승격 → alert-failure/watchdog 발동.
- 동시 슬롯 경합: `git rebase -X theirs origin/main`(누적 superset 우선) 후 재시도.

## 남은 확인 (미완)
- GH Actions 9/7~9/8 **실행 자체가 죽은 건지 / 푸시만 죽은 건지** 런 로그 확인 필요 — 로컬엔 gh 인증 없음(세은 gh auth 또는 GH_TOKEN).

관련: [[reference_ig_dm_kpi_pipeline]] · 20메시지 캡 = Meta API 하드제약(graph.instagram.com conversations-api). 코호트 정의 [[session_20260908]].
