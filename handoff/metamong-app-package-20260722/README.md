# 메타몽 앱 (meta-app) 핸드오버 패키지

Grosmimi JP Meta 광고 운영 대시보드 **"메타몽"** 을 아무것도 없는 상태에서 100% 동일하게
재구현하기 위한 전체 패키지. 회사 intelligence 플랫폼 이식용.

- 패키지 생성일: 2026-07-22
- 소스 스냅샷: `C:\Users\orbit\Desktop\SE\meta-app` (로컬 최신, Vercel prod 배포본과 동일 코드)
- 라이브 URL: https://meta-app-one.vercel.app (비밀번호 게이트)

## 패키지 구성

| 경로 | 내용 |
|---|---|
| `meta-app/` | 앱 전체 소스 (Next.js 16). `node_modules`/`.next`/`.vercel` 만 제외 — `npm install` 후 즉시 빌드 가능 |
| `meta-app/.env.local` | **실제 환경변수 값 (동봉)** — 내부 전달 전제. 그대로 복사해 즉시 구동 가능 |
| `meta-app/.env.handoff.template` | 변수별 출처·발급 방법 설명 (값 문서화용) |
| `pipeline-tools/` | 앱에 데이터를 공급하는 SE 파이썬 도구 11개 (시드 갱신·DK 적재·태깅·메일 발송 포함) |
| `pipeline-tools/.env` | **파이프라인용 실제 크레덴셜 동봉** (SE 루트 .env 에서 필요 키 11개만 추출) |
| `pipeline-tools/credentials/` | Gmail OAuth 2종 + Rakuten RMS config — 도구가 그대로 참조 |
| `github-workflows/` | 9시 메일·주간 메일 GitHub Actions 정의 (`meta_jp_daily.yml`, `meta_jp_weekly.yml`) |
| `schedules/` | 로컬 Windows Task Scheduler 작업 4개의 XML 원본 (트리거·커맨드 그대로) |
| `docs/01_ARCHITECTURE.md` | **메인 문서** — 아키텍처·데이터 소스·흐름·판정 로직·운영 스케줄·재구현 가이드 |
| `docs/02_PAGES_AND_ROUTES.md` | 프론트엔드 라우트별 상세 (화면 구성·컬럼·계산·API 스키마) |
| `docs/03_COMPONENTS.md` | 컴포넌트 레이어 상세 (props·상태·색상 규칙·팝업 체인) |
| `docs/04_PIPELINE_TOOLS.md` | 파이프라인 도구 7종 상세 (데이터 소스·CLI·시드 스키마·스케줄) |

## 읽는 순서

1. `docs/01_ARCHITECTURE.md` — 전체 그림 (필수)
2. `docs/02` → `docs/03` — 프론트엔드 재구현 시
3. `docs/04` + `schedules/` + `github-workflows/` — 데이터 파이프라인 재구현 시

## 즉시 실행 (현행 그대로 돌려보기)

```bash
cd meta-app        # .env.local 동봉 — 그대로 사용
npm install
npm run dev        # prebuild 가드(check-status-source.mjs) 자동 실행
```

## ⚠️ 보안 주의

- **이 패키지는 완전 자급자족 — 실제 시크릿 전부 동봉.**
  (`meta-app/.env.local`, `pipeline-tools/.env`, `pipeline-tools/credentials/*`, `lib/datakeeper.ts` 내 DK 토큰 fallback)
  내부 전달 전제 — 외부 서비스(공개 드라이브·외부 메일 등) 업로드 금지, 공용 레포에 커밋 금지.
- 이식 완료 후: datakeeper.ts 하드코딩 fallback 제거 + env 단일화, 토큰 로테이션 권장.
- 변수별 출처·발급 방법은 `.env.handoff.template` 과 `docs/01_ARCHITECTURE.md` §9 참조.
