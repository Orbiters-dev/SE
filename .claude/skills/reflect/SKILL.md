# reflect — 세션 자동 학습 스킬

세션 종료 시 대화 transcript를 분석하여 세은의 교정/피드백을 자동 감지하고 기록한다.

## 동작 방식

### Stop Hook (세션 종료 시 자동)
1. `hook-stop.sh` → Claude Code Stop 이벤트에서 자동 실행
2. stdin으로 `transcript_path` 수신
3. `reflect.py` 백그라운드 실행 → 세션 종료 블로킹 없음

### 학습 파이프라인
1. `extract_signals.py` — transcript에서 한국어 교정 패턴 감지
   - HIGH (0.85): "~하지마", "~금지", "~말고 ~해", "템플릿대로 해"
   - MEDIUM (0.65): "웅", "ㅇㅇ", "맞아" (승인)
   - DM (0.75): 톤 교정, 일본어 표현 수정
2. `reflect.py` — HIGH 신호 → `mistakes.md` 자동 추가

### 세션 브리핑 (/briefing)
세션 시작 시 `/briefing` 실행하면:
1. 최근 세션 요약 읽기 (session_*.md)
2. git 최근 변경 확인
3. 인플루언서 현황 정리
4. 오늘 해야 할 액션 알림

## 파일 구조

```
.claude/skills/reflect/
├── SKILL.md              ← 이 파일
├── .state/
│   ├── auto-reflection.json   ← 활성화 설정
│   ├── last-reflection.json   ← 마지막 실행 결과
│   ├── reflection.lock        ← 중복 실행 방지
│   └── signals_YYYYMMDD.json  ← 일별 신호 로그
└── scripts/
    ├── hook-stop.sh       ← Stop hook 엔트리포인트
    ├── reflect.py         ← 메인 오케스트레이션
    └── extract_signals.py ← 한국어 패턴 매칭
```

## 활성화/비활성화

```json
// .state/auto-reflection.json
{"enabled": true}   // 활성화
{"enabled": false}  // 비활성화
```

## 트리거

- **자동**: 매 세션 종료 시 Stop hook
- **수동**: `/briefing` 커맨드로 세션 시작 브리핑
