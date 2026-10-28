---
name: reference-metaapp-gitignored-vercel-deploy
description: 메타몽 app(meta-app) 배포 경로 — SE git에서 gitignore 제외, Vercel 직배포(vercel --prod)가 정본
metadata:
  type: reference
---

메타몽 app(`meta-app/`)은 SE 리포 `.gitignore` 31번 줄(`meta-app/`)로 **통째 제외**돼 있고 자체 `.git`도 없다. 즉 SE 리포에 추적 파일 0개 → **git 커밋으로 배포 못 함**.

- 배포 정본 경로 = **`cd meta-app && vercel --prod --yes`** (Vercel 프로젝트 `meta-app`, projectId prj_BgTVzO3zHdAegDGfJWN6zzeaUlSx, team_Gi2FdtDzUnhOJZhd0lETQmQF). 원격 빌드(iad1), prebuild `scripts/check-status-source.mjs`(Graph status-source 가드) 통과 필수.
- 프로덕션 URL = **meta-app-one.vercel.app** (alias). 배포 시 자동 alias 갱신.
- 로컬 확인 = `npx next dev`(세은이 :3000에 상시 띄워둠). 파일 수정은 HMR로 즉시 반영.
- "메타몽 app 커밋해" 요청이 와도 git add/commit 하지 말 것 — gitignore라 no-op. 실제 반영은 vercel --prod(외부/프로덕션 액션 → 세은 명시 승인 후).

빌드 로그 `Failed to set Next.js data cache ... items over 2MB`는 DataKeeper 응답이 2MB 초과라 캐시만 스킵되는 **기존 경고**(에러 아님).

관련: [[reference-metamong-app-5tab-ih-dashboard]] · [[reference-jp-review-autopublish-pipeline]]
