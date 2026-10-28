---
name: 메타몽 app 대시보드 수정 지시 = prod 배포까지 한 세트 (배포할까요 금지)
description: 세은이 메타몽 app(대시보드) 화면 수정을 명시 지시하면 로컬 수정 후 vercel prod 배포까지 실행하고 보고. "배포할까요?" 되묻기 금지
type: feedback
---

세은이 **메타몽 app(intelligence dashboard) 화면 내용을 수정·기재하라고 명시 지시**하면, 로컬 Edit 후 **`vercel --prod`(cwd=meta-app) 배포까지가 지시 이행의 일부**다. 로컬 수정만 하고 "배포할까요?" 되묻지 말 것 → 배포 실행 후 prod 반영 결과로 보고.

**Why:** 2026-10-02 재콜라보 랭킹 대시보드에 등급 채점 산식(percentile→점수) 패널을 "기재해야지" 지시받고, 로컬 수정 후 "prod 반영하려면 배포 필요한데 배포할까요?"로 되물음 → 세은 "해야지 임마". 대시보드는 배포 안 하면 화면에 안 보여 무의미 → 수정 지시의 의도 자체가 prod에서 보이게 하는 것. 되묻는 건 당연한 걸 미루는 떠넘김.

**How to apply:**
- 대시보드 화면 수정/기재/정정 지시 → 로컬 Edit → `vercel --prod` 배포 → prod URL·빌드 성공·READY 확인 후 보고
- [[feedback-fix-obvious-bugs-without-asking]]의 "배포면 승인 요청" 단서는 **세은이 명시 지시하지 않은 자발적 배포**에 한함. 명시 지시받은 대시보드 수정 배포는 승인 불요
- 단, 되돌리기 어렵거나 외부 발송성(이메일·DM·결제) 액션은 여전히 승인 필요 — 내부 대시보드 vercel 배포는 그 범주 아님
- 메타몽 app 배포 = SE repo gitignore라 git push 아님, `vercel --prod` 전용 (prebuild status 가드 통과해야 빌드 성공)
