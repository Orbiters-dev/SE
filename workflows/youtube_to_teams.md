# YouTube to Teams — 유튜브 채널 영상 순차 공유

## 목적

지정된 유튜브 채널의 전체 영상을 오래된 순으로 정렬하고,
평일 오전 8시마다 1개씩 Microsoft Teams 채널에 자동으로 공유한다.
API 키 없이 yt-dlp로 영상 목록을 수집한다.

## 발송/저장 정보

- 입력 소스: YouTube (yt-dlp, API 키 불필요)
- 출력 대상: Microsoft Teams (Incoming Webhook)
- 실행 주기: 평일(월~금) 오전 8시
- 채널: https://www.youtube.com/@nateherk

---

## 초기 설정

### .env / .wat_secrets 필요 항목

```
TEAMS_WEBHOOK_URL=...                                          # Teams 채널 Webhook
YOUTUBE_CHANNEL_URL=https://www.youtube.com/@nateherk         # 채널 URL
```

### Teams Webhook URL 설정 방법

1. Teams에서 대상 채널 선택
2. 채널 우클릭 → 채널 편집 → 커넥터 (또는 앱 → Incoming Webhook)
3. Incoming Webhook 추가 → 이름 지정 → URL 복사
4. `.wat_secrets`에 `TEAMS_WEBHOOK_URL=복사한URL` 저장

### 패키지 설치

```bash
pip install yt-dlp requests
```

---

## 상태 파일

```
.tmp/youtube_queue.json
```

구조:
```json
{
  "channel_url": "https://www.youtube.com/@nateherk",
  "last_fetched": "20260313",
  "videos": [
    {
      "video_id": "abc123",
      "title": "영상 제목",
      "published_at": "2020-01-01T00:00:00Z",
      "upload_date": "20200101",
      "url": "https://www.youtube.com/watch?v=abc123",
      "sent": false,
      "sent_at": null
    }
  ]
}
```

- `sent: false` → 아직 미발송
- `sent: true` → 발송 완료
- 큐는 `upload_date` 기준 오름차순 (오래된 것 먼저)

---

## 워크플로우 단계

### Step 1: 큐 초기화 (최초 1회)

채널 전체 영상을 yt-dlp로 가져와 큐 파일에 저장한다.

```bash
python tools/run_youtube_daily.py --init
```

- 채널 URL에서 전체 영상 목록 수집 (수백 개면 1~2분 소요)
- `upload_date` 기준 오름차순 정렬
- `.tmp/youtube_queue.json` 생성

---

### Step 2: 일일 발송 (평일 오전 8시)

```bash
python tools/run_youtube_daily.py
```

1. `.tmp/youtube_queue.json` 로드
2. `sent: false` 중 가장 오래된 영상 1개 선택
3. Teams에 메시지 발송:
   - **제목**: 📺 새 영상 공유
   - **본문**: 새 영상이 업로드되어 공유드립니다.
   - **상세**: 영상 제목, 링크, 업로드일
4. 발송 성공 시 `sent: true`, `sent_at` 기록
5. 대기 영상 없으면 Teams에 경고 알림 발송

---

### Step 3: 신규 영상 동기화 (선택)

채널에 새 영상이 추가되었을 때 큐에 자동 추가:

```bash
python tools/run_youtube_daily.py --sync
```

- 마지막 `last_fetched` 이후 업로드된 영상만 가져와 큐 끝에 추가
- 기존 발송 내역은 유지

---

### Step 4: 실패 처리

| 상황 | 동작 |
|------|------|
| yt-dlp 수집 실패 | 에러 출력 후 종료 |
| Teams Webhook 오류 | 재시도 3회 (send_teams_message.py 내장) → Teams tool_error 알림 |
| 큐 파일 없음 | `--init` 먼저 실행 안내 메시지 + Teams 에러 알림 |
| 미발송 영상 없음 | Teams에 경고 알림 발송 |
| 주말 실행 | 자동 스킵 (토/일 감지 후 종료) |

---

## 실행 명령

```bash
# 최초 큐 초기화
python tools/run_youtube_daily.py --init

# 일일 발송 (평일 8시 자동 실행)
python tools/run_youtube_daily.py

# 드라이런 (발송 없이 어떤 영상이 선택되는지 확인)
python tools/run_youtube_daily.py --dry-run

# 큐에 신규 영상 동기화
python tools/run_youtube_daily.py --sync

# 큐 현황 확인
python tools/run_youtube_daily.py --status
```

Claude에게:
```
"유튜브 팀즈 공유 실행해줘"
"유튜브 큐 초기화해줘"
"유튜브 큐 상태 확인해줘"
```

---

## 실행 흐름

```
[최초 1회]
Step 1: yt-dlp → 채널 전체 영상 수집
Step 2: upload_date 오름차순 정렬
Step 3: .tmp/youtube_queue.json 저장

[평일 오전 8시 자동]
Step 1: youtube_queue.json 로드
Step 2: 미발송 영상 중 가장 오래된 1개 선택
Step 3: send_teams_message.py → Teams 발송
Step 4: sent: true 기록 → 큐 저장
```

---

## GitHub Actions 설정 (PC 없이 자동 실행, 권장)

GitHub에 push하면 평일 오전 8시 자동 실행된다. 아이폰 GitHub 앱에서 수동 트리거도 가능.

### 1회 설정 순서

**① GitHub에 리포지토리 push**
```bash
git add .github/workflows/youtube_to_teams.yml data/
git commit -m "feat: youtube to teams github actions"
git push
```

**② GitHub Secrets 등록**
- 리포지토리 → Settings → Secrets and variables → Actions → New repository secret
- `TEAMS_WEBHOOK_URL` : Teams Incoming Webhook URL
- `YOUTUBE_CHANNEL_URL` : `https://www.youtube.com/@nateherk`

**③ Actions 권한 허용**
- 리포지토리 → Settings → Actions → General
- Workflow permissions → **Read and write permissions** 체크

완료. 이후 자동 실행됨.

### 아이폰에서 수동 트리거

GitHub 앱 → 리포지토리 → Actions → YouTube to Teams Daily → Run workflow

### 큐 파일 위치

GitHub Actions 환경에서는 `data/youtube_queue.json` (git에 자동 커밋됨)
로컬 실행 시에는 `.tmp/youtube_queue.json` (기존 동일)

---

## Windows 작업 스케줄러 등록

```
작업 이름: youtube_to_teams_daily
트리거:   매일 08:00
조건:     평일(월~금)만 실행 — 스크립트 내부에서도 토/일 자동 스킵
동작:     python "C:\Users\user\Desktop\동균 테스트\tools\run_youtube_daily.py"
```

---

## 알려진 한계 및 주의사항

1. **yt-dlp 수집 속도**: 채널 영상이 많을수록 --init 시간 증가 (500개 기준 약 2~3분)
2. **비공개/멤버십 영상**: 수집 불가, 큐에 포함되지 않음
3. **Teams 채널 미확정**: `TEAMS_WEBHOOK_URL` 설정 후 사용 가능
4. **yt-dlp 업데이트**: YouTube 정책 변경 시 `pip install -U yt-dlp` 로 갱신

---

## 향후 개선

- 썸네일 이미지를 Adaptive Card에 포함
- 발송 이력을 Google Sheets에 기록
- 채널 복수 지원
- 주간 진행 현황 알림 (남은 영상 수 등)