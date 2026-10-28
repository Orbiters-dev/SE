---
name: session-20260916-metamong-recollab
description: 세션 2026-09-16 메타몽 — 재콜라보 랭킹 대시보드 신규 구축·배포 + 다중 교정
metadata:
  type: project
---

메타몽 세션 2026-09-16. 세은 요청 = "재콜라보(1회 협업자와 재협업) 대상 선정 기준 세우고 대시보드 만들기". EnterPlanMode→ExitPlanMode 승인→구현→`vercel --prod` 배포 완주. [[reference-recollab-ranking-dashboard]] 정본.

**결과:** `/influencer/recollab` 신규 탭 + `재콜라보 기준` 서브탭. 랭킹 61명(로스터+시트미등록 26 전원)·deal type 전원 판별(Gifted78/Paid37/미상0)·광고 139건중 114 연결. 프로덕션 실렌더 200 검증.

**교정 다발:**
- (강) deal type 모르는 크리에이터 리스팅 제외 사고 → [[mistakes-20260916-exclude-unknown-dealtype]] (결측=제외 X·표기).
- (강) 리포트에서 수정이력·"왜 CPLPV" 상식 섹션 삭제 지시 → [[feedback-report-results-only-no-process]].
- (강) "미연결 전부 연결하라" → CT코드/permalink/닉네임 5단 귀속으로 56→114건 회복.
- (중) VTR 누적→오가닉 D+3 (나이편향). "DK에 데이터 있는 것만".
- collabCount 3회 오류(기획/빈 시트행 카운트)→게시 콜라보만 1회.

**미완:** CPLPV 시점 창(생애누적 vs 최근N일) 세은 선택 대기. 상위권 다수 시트 미등록→WL Code&Payment 시트 보강 필요(대외/데이터 hygiene). 리포트 v5 정본 .tmp/recollab_report/재콜라보_기준_대시보드_리포트.html.

**주의(도구):** PowerShell/Bash cwd가 meta-app↔SE루트 오락가락 — vercel은 Set-Location meta-app 후 실행하고 끝나면 SE루트 복귀(안 하면 Edit 훅 상대경로 깨짐). 세션쿠키 Secure라 로컬 http 검증은 next dev(NODE_ENV=dev)로 로그인. React가 {값} 사이 주석노드 넣어 괄호 안 숫자 regex 깨짐→단일 string prop("N명")만 신뢰.
