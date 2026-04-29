---
name: GitHub Actions cron 정각 부하 회피 패턴
description: 정각(0 X * * *) cron은 5~15분 지연 흔함. X:55 패턴으로 정각 5분 일찍 발동 + 메시지엔 정각 표시.
type: reference
---

GitHub Actions schedule cron은 [공식 문서 인정](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule)대로 정각 부하 시간엔 5~15분 지연이 흔함. 정시 알림이 중요하면 cron을 정각 5분 일찍으로 옮기고, 메시지에서는 슬롯 시간(정각)을 표시.

**적용 사례:** `.github/workflows/twitter_slot_notify.yml` (2026-04-29 도입).
- JST 11:00 정확히 알림 필요 → cron `0 2 * * *` (UTC 02:00 = JST 11:00)는 11:09에 도착하는 등 지연.
- 변경: cron `55 1 * * *` (UTC 01:55 = JST 10:55)로 5분 일찍 발동, 알림 메시지엔 `--slot 11`로 받아 "11:00 업로드 시간이에요" 표시. 5분 일찍 와도 본인이 무슨 슬롯인지 명확.

**JST → UTC 매핑 (X:55 패턴):**
| 슬롯 | cron (UTC) | 발동 (JST) |
|---|---|---|
| 10시 | `55 0 * * *` | 09:55 |
| 11시 | `55 1 * * *` | 10:55 |
| 13시 | `55 3 * * *` | 12:55 |
| 17시 | `55 7 * * *` | 16:55 |
| 19시 | `55 9 * * *` | 18:55 |

**case 매칭 (워크플로우 안):**
정각 5분 전 발동이므로 UTC 시 = (JST 슬롯 - 9 - 1).
```bash
HOUR=$(date -u +%H)
case "$HOUR" in
  00) echo "slot=10" ;;
  01) echo "slot=11" ;;
  03) echo "slot=13" ;;
  07) echo "slot=17" ;;
  09) echo "slot=19" ;;
esac
```

**주의:** 새 cron schedule을 push해도 GitHub이 첫 cycle을 인식 못 하는 경우 흔함. 첫 발동 안 와도 다음 cycle부터 정상 가능. 즉시 검증은 `gh workflow run` 수동 trigger.
