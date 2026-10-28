---
name: Windows 시스템 자원은 PowerShell
description: Task Scheduler / 레지스트리 / 이벤트 로그 / 서비스 조회는 PowerShell 우선. bash schtasks/reg/sc 는 cp949 출력이라 grep 깨짐.
type: reference
---

## Windows 시스템 자원 조회 도구 룰

| 자원 | PowerShell | 비고 |
|---|---|---|
| Task Scheduler | `Get-ScheduledTask`, `Get-ScheduledTaskInfo` | bash `schtasks /query` 는 cp949 |
| 레지스트리 | `Get-ItemProperty`, `Get-Item HKLM:\...` | bash `reg query` 는 cp949 |
| 이벤트 로그 | `Get-EventLog`, `Get-WinEvent` | bash `wevtutil` 는 cp949 |
| 서비스 | `Get-Service` | bash `sc query` 는 cp949 |
| 프로세스 | `Get-Process` | bash `tasklist` 는 cp949 |

### 왜

bash 환경(Git Bash/WSL on Windows)에서 위 명령들을 호출하면 출력이 **cp949 (한국어 인코딩)**로 나옴. UTF-8 기반 `grep`/`rg`는 cp949 한국어/특수문자 매칭 깨져서 빈 결과를 받음.

→ "결과 없음" 으로 단정 X. 도구 실패 가능성 의심 → PowerShell 재시도.

### 실수 사례

2026-05-07 — `schtasks /query | grep -iE "kse|amazon|rakuten"` 빈 결과 → "Task Scheduler 등록 없음" 단정. 실제로는 KSE 3개 + Rakuten 2개 등록돼 있었음. PowerShell `Get-ScheduledTask | Where-Object` 로 즉시 발견.

### How to apply

- Windows 자원 조회 작업이면 **첫 시도부터 PowerShell**
- 만약 bash 명령이 빈 결과 반환하면 무조건 PowerShell 교차검증 후 단정
- bash `| grep` + 한국어 도구 출력 조합은 신뢰 X
