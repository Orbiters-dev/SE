# Teams Notification Workflow

## Objective
Teams Incoming Webhook을 통해 트리거별 자동 알림을 전송한다.

## Prerequisites
- Microsoft Teams 채널 접근 권한
- `.env`에 `TEAMS_WEBHOOK_URL` 설정 완료

---

## Setup: Teams Webhook 생성

1. Teams에서 알림 받을 **채널** 열기
2. 채널 이름 옆 **"..."** 클릭 → **"워크플로"** 선택
3. **"웹후크 요청을 받을 때 채널에 게시"** 템플릿 선택
4. 워크플로 이름 입력 (예: "WAT Alerts") → **다음**
5. 게시할 채널 확인 → **워크플로 추가**
6. 생성된 **Webhook URL** 복사
7. `.env` 파일에 붙여넣기:
   ```
   TEAMS_WEBHOOK_URL=https://prod-xx.westus.logic.azure.com:443/workflows/...
   ```

---

## Tool
`tools/send_teams_message.py`

---

## Trigger Types

### 1. tool_success (도구 실행 성공)
초록색 카드. 도구가 정상 완료됐을 때 사용.

```bash
python tools/send_teams_message.py \
  --type tool_success \
  --title "CIPL 생성 완료" \
  --body "25개 아이템, 총 50 CTN 처리" \
  --detail "Tool=generate_cipl.py" \
  --detail "Output=Data Storage/export/2026-02_Grosmimi_SEA.xlsx"
```

### 2. tool_error (도구 실행 에러)
빨간색 카드. 도구 실행 중 에러 발생 시 사용.

```bash
python tools/send_teams_message.py \
  --type tool_error \
  --title "Notion 동기화 실패" \
  --body "API rate limit 초과" \
  --detail "Tool=sync_influencer_notion.py" \
  --detail "Error=429 Too Many Requests"
```

### 3. weekly_report (주간 리포트 생성)
파란색 카드. 주간 리포트 생성 완료 시 사용.

```bash
python tools/send_teams_message.py \
  --type weekly_report \
  --title "Week 9 Performance Report" \
  --body "Notion 주간 리포트 생성 완료" \
  --detail "Period=2026-02-17 ~ 2026-02-23" \
  --detail "Revenue=$45,230"
```

---

## 다른 도구에서 연동

```python
from send_teams_message import notify_teams

# 성공 알림
notify_teams("tool_success", "작업 완료", "25개 처리됨",
             details={"Tool": "my_tool.py"})

# 에러 알림
notify_teams("tool_error", "작업 실패", str(error),
             details={"Tool": "my_tool.py", "Step": "API call"})

# 주간 리포트
notify_teams("weekly_report", "Week 9 Report", "Notion 페이지 생성됨",
             details={"URL": "https://notion.so/..."})
```

---

## Dry Run (테스트)

실제 전송 없이 메시지 미리보기:

```bash
python tools/send_teams_message.py --dry-run --type tool_success --title "Test" --body "Preview"
```

---

## Edge Cases
- `TEAMS_WEBHOOK_URL` 미설정 시 에러 메시지 출력 후 종료
- Teams API rate limit 시 자동 재시도 (최대 3회, exponential backoff)
- 네트워크 에러 시 재시도 후 실패 반환
- Webhook URL 만료 시 Teams에서 워크플로 재생성 필요
