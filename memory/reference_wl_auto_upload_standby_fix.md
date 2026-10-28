---
name: WL D+3 자동 업로드 task 절전 킬 수리 (JPDash_WL_AutoUpload)
description: WL 자동 업로드가 09시에 안 도는 원인 = Task Scheduler 전원설정이 절전에 무방비. StopIfGoingOnBatteries True + 재시도 0 → 절전 진입 시 0xC000013A(^C)로 죽고 catchup 없음
type: reference
---

## 증상 (2026-09-10 세은 지적 「WL 자동 업로드 왜 안 하지? 3일 지나면 자동으로 하라 했는데」)

- 자동 업로드 파이프라인 = `tools/wl_auto_upload.py` (D+3 미부착 게시물 중 제품확정분만 PAUSED 생성. ON=세은 수동).
- 실행 = Task Scheduler `JPDash_WL_AutoUpload`, 매일 09:00 JST, wrapper `.tmp/ceo_ads_report/run_wl_auto_upload.ps1`, 로그 `.tmp/ceo_ads_report/logs/wl_auto_upload_YYYYMMDD.log`.
- `wl_d3_watchdog.py`는 **알림 전용(read-only)** — 자동 생성 안 함. 헷갈리지 말 것. 생성은 `wl_auto_upload.py`.

## 근본 원인

WL task 전원설정이 절전 생존하는 JPDash_Daily와 정반대:
| 설정 | WL(고장) | JPDash_Daily(정상) |
|---|---|---|
| StopIfGoingOnBatteries | True (배터리 전환 시 강제종료=0xC000013A ^C) | False |
| DisallowStartIfOnBatteries | True | False |
| WakeToRun | False | True |
| RestartCount | 0 (재시도 없음) | 3 / 30분 |

→ 절전 진입하면 09시 프로세스가 ^C로 죽고, JPDash처럼 catchup도 없어 그날 조용히 누락. 09-10 로그 `^C exit=-1073741510(0xC000013A)` 실측.

## 조치 (2026-09-10 적용)

`Set-ScheduledTask -TaskName JPDash_WL_AutoUpload -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -RestartCount 3 -RestartInterval 30m -ExecutionTimeLimit 1h -StartWhenAvailable)` → JPDash_Daily 설정과 동일화. StartWhenAvailable로 놓친 실행도 자동 재개.

## 검증된 사실 (오답 방지)

- 09-09 정상 완주(exit=0)·1건 업로드(@_non_____a NON_A). 09-10만 절전 킬. **과거 실제 누락 광고는 없었음** (킬된 날 업로드 가능분이 0이었을 뿐 — 구조적 구멍은 실재).
- dry-run은 제품매핑까지만 판정 → 「업로드예정」으로 보여도 라이브에서 **저작권 음악(error 2875030)** 이면 skip. 음악 판정은 advideos 단계에서만. dry-run 「would_upload」를 업로드 확정으로 보고하지 말 것.
- 보류(제품미상)=폼 매칭 실패. 세은이 제품 지정하면 즉시 업로드 가능.

[[reference-jpdash-catchup-selfheal]] · [[reference-meta-wl-branded-ad-api-creation]]
