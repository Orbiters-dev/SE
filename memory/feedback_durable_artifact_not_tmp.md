---
name: feedback_durable_artifact_not_tmp
description: 매일 누적·D+N 지켜볼 산출물은 처음부터 항구적 위치(app 탭/시트)에 적재. .tmp(gitignore·폐기용)에 넣지 마 (2026-09-23 「이거 어디에 적재되는 거야」).
metadata:
  type: feedback
---

2026-09-23 채널 CVR 실험 — 매일 자동 적재되는 리포트를 `.tmp/channel_cvr_experiment/`(gitignore, 폐기 가능)에 넣었다가 세은 「이거 어디에 적재되는 거야 근데?」 지적. 항구적 위치를 처음부터 잡았어야 함.

**Why:** `.tmp`는 CLAUDE.md 정의상 처리용·폐기 가능. 2주(D+14) 지켜볼 시계열/누적 산출물을 여기 두면 세은이 상시 열 수 없고 청소되면 사라짐. "최종 산출물은 Sheets/Slides/Cloud" 룰의 대상이 일회성 리포트뿐 아니라 **누적 대시보드성 산출물**에도 적용됨.

**How to apply:** 산출물 만들 때 수명을 먼저 판단 — (1) 이번 턴 처리용/검토 후 폐기 = `.tmp` OK. (2) 매일 갱신·기간 지켜볼·세은이 다시 볼 것 = **항구적 위치 먼저 정함**. 후보: metamong app 탭(대시보드성·기존 seed+vercel 패턴 재활용) > 구글시트(가벼운 누적) > 로컬 durable 폴더(공유 불가). 위치가 정책 판단이면 한 번 묻되(추천 제시), 명백하면 바로 항구적으로. 관련 [[project_meta_tiktok_channel_cvr_experiment]] · [[feedback_report_analytical_real_names]].
