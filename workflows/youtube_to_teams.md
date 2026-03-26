# YouTube to Teams — Nate Herk Claude 영상 자동 공유

## 목적

`@nateherk` 채널에서 **제목에 'Claude'가 포함된 영상**만 골라,
평일(공휴일 제외) 오전 8시마다 1개씩 Microsoft Teams 채널에 자동 공유한다.
큐가 소진되면 매일 채널을 확인하여 신규 Claude 영상이 올라오면 자동으로 추가 발송한다.

## 발송/저장 정보

- 입력 소스: YouTube (yt-dlp, API 키 불필요)
- 출력 대상: Microsoft Teams (Incoming Webhook)
- 실행 주기: 평일(월~금) 오전 8시 — 한국 법정공휴일·명절·근로자의 날 자동 스킵
- 채널: https://www.youtube.com/@nateherk
- 필터: 제목에 'Claude' 포함된 영상만

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
pip install yt-dlp requests holidays
```

---

## 상태 파일

```
data/youtube_queue.json     # GitHub Actions 환경 (git 자동 커밋)
.tmp/youtube_queue.json     # 로컬 실행 환경
```

구조:
```json
{
  "channel_url": "https://www.youtube.com/@nateherk/videos",
  "filter": "Claude in title, uploaded >= 2026-03-03",
  "last_fetched": "20260326",
  "videos": [
    {
      "video_id": "abc123",
      "title": "Claude Code ...",
      "published_at": "2026-03-03T00:00:00Z",
      "upload_date": "20260303",
      "url": "https://www.youtube.com/watch?v=abc123",
      "sent": false,
      "sent_at": null
    }
  ]
}
```

- `sent: false` → 미발송
- `sent: true` → 발송 완료
- 큐는 `upload_date` 기준 오름차순 (오래된 것 먼저)

---

## 워크플로우 단계

### Step 1: 큐 초기화 (최초 1회)

```bash
python tools/run_youtube_daily.py --init
```

- extract_flat으로 전체 목록 수집 → 제목에 'Claude' 포함 + 날짜 없는 영상은 플레이리스트 역순 인덱스로 정렬
- `data/youtube_queue.json` 생성

> **주의**: --init은 전체 채널 영상을 수집하므로 필터 없이 모든 영상이 들어갈 수 있다.
> 특정 날짜 이후 Claude 영상만 원하면, 초기화 후 큐 파일을 직접 필터링하거나 수동으로 구성한다.

---

### Step 2: 일일 발송 (평일 오전 8시, 공휴일 제외)

```bash
python tools/run_youtube_daily.py
```

1. 공휴일 체크 (주말·법정공휴일·명절·근로자의 날) → 해당 시 즉시 종료
2. 신규 Claude 영상 자동 sync (`last_fetched` 이후 업로드된 것만)
3. 미발송 영상 중 가장 오래된 1개 선택
4. Teams에 발송 (제목, 링크, 업로드일)
5. 발송 성공 시 `sent: true`, `sent_at` 기록
6. 미발송 영상 없으면 조용히 종료 (Teams 알림 없음)

---

### Step 3: 신규 Claude 영상 자동 감지 (매일 자동)

별도 실행 불필요. Step 2의 일일 실행 시 자동으로 포함된다.

수동으로 실행하려면:
```bash
python tools/run_youtube_daily.py --sync
```

- extract_flat으로 채널 전체 목록 → 제목에 'Claude' 포함 + 큐에 없는 것 추출
- 후보 영상만 개별 fetch로 upload_date 확인
- `last_fetched` 이후 업로드된 것만 큐에 추가 (과거 영상 재추가 방지)

---

### Step 4: 실패 처리

| 상황 | 동작 |
|------|------|
| yt-dlp 수집 실패 | 에러 출력 후 종료 |
| Teams Webhook 오류 | 재시도 3회 → Teams tool_error 알림 |
| 큐 파일 없음 | 자동으로 --init 실행 |
| 미발송 영상 없음 | 조용히 종료 (다음날 재확인) |
| 주말/공휴일 실행 | 자동 스킵 후 종료 |

---

## 공휴일 처리

`holidays` 패키지 기반 한국 공휴일 자동 감지:
- 법정공휴일 (삼일절, 광복절, 개천절, 한글날, 성탄절 등)
- 명절 및 대체공휴일 (설날, 추석 포함)
- 선거일 (예: 2026 대통령선거 6/3)
- **근로자의 날 (5/1)**: `holidays` 패키지 미반영으로 수동 추가

---

## 실행 명령

```bash
# 최초 큐 초기화
python tools/run_youtube_daily.py --init

# 일일 발송 (평일 8시 자동 실행)
python tools/run_youtube_daily.py

# 드라이런 (발송 없이 어떤 영상이 선택되는지 확인)
python tools/run_youtube_daily.py --dry-run

# 신규 Claude 영상 수동 sync
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
[평일 오전 8시 자동]
Step 1: 공휴일 체크 → 해당 시 즉시 종료
Step 2: sync — extract_flat으로 신규 Claude 영상 감지 → 있으면 큐 추가
Step 3: 미발송 영상 중 가장 오래된 1개 선택
Step 4: Teams 발송 → sent: true 기록 → 큐 저장 (git 커밋)
```

---

## GitHub Actions 설정 (PC 없이 자동 실행, 권장)

GitHub에 push하면 평일 오전 8시(KST) 자동 실행된다.

### 1회 설정 순서

**① GitHub Secrets 등록**
- 리포지토리 → Settings → Secrets and variables → Actions → New repository secret
- `TEAMS_WEBHOOK_URL` : Teams Incoming Webhook URL
- `YOUTUBE_CHANNEL_URL` : `https://www.youtube.com/@nateherk`

**② Actions 권한 허용**
- 리포지토리 → Settings → Actions → General
- Workflow permissions → **Read and write permissions** 체크

### 아이폰에서 수동 트리거

GitHub 앱 → 리포지토리 → Actions → YouTube to Teams Daily → Run workflow

### 큐 파일 위치

- GitHub Actions: `data/youtube_queue.json` (발송 후 자동 커밋)
- 로컬: `.tmp/youtube_queue.json`

---

## 알려진 한계 및 주의사항

1. **yt-dlp extract_flat**: upload_date를 반환하지 않음 — sync 시 Claude 후보 영상만 개별 fetch로 날짜 확인
2. **비공개/멤버십 영상**: 수집 불가
3. **yt-dlp 업데이트**: YouTube 정책 변경 시 `pip install -U yt-dlp` 로 갱신
4. **근로자의 날**: `holidays` 패키지에 미포함 — 코드에 수동 추가됨 (매년 유지 불필요)
