---
name: reference-wl-autoupload-cloud-dk-cred-missing
description: "WL D+3 자동집행이 클라우드에서 집행 0 이던 근본원인 — wl_auto_upload.yml 에 DataKeeper 크레덴셜(ORBITOOLS_USER/PASS) 미주입 → DK 원장 공백 → 핸들 실명화 → 제품매핑 전멸(제품미상). + 제품미상은 실제론 폼 투고완료탭에 제품 있음(핸들↔제품 조인 버그)."
metadata:
  type: reference
---

# WL 자동집행 클라우드 집행 0 근본원인 (2026-10-07 메타몽)

## 증상
정성심사 통과분이 WL 세팅 안 됨. 클라우드 run(GitHub Actions `wl_auto_upload.yml`)은 매일 success 지만 **집행 0 · 전건 보류**. cloud run 로그엔 32건 핸들이 **전부 일본 실명**(水野栞奈 등). 로컬 dry-run은 일부가 IG핸들로 would_upload.

## 근본원인 (멀티소스 교차검증)
1. `wl_d3_watchdog.ledger_dk()` 가 `DataKeeper().get("content_posts")` 로 IG username 을 가져옴 (원장의 handle 소스).
2. DK 클라이언트 인증: `ORBITOOLS_USER`/`ORBITOOLS_PASS`(basic) 또는 `DK_SE_READ_TOKEN`(bearer). 없으면 PG 401 → NAS(Z:)·로컬캐시 폴백도 **클라우드 러너엔 없음** → `[]` 반환(예외 아님, graceful empty → WARN도 안 뜸).
3. `wl_auto_upload.yml` 의 `.env` 작성 블록에 **ORBITOOLS 크레덴셜 누락** (META/TEAMS/GMAIL 만 주입). 다른 10개+ 워크플로우(data_keeper·apify·financial)는 `secrets.ORBITOOLS_USER/PASS` 정상 주입 중 → 시크릿 실존.
4. ⇒ 클라우드 ledger_dk = {} → 모든 게시물이 `ledger_form`(투고완료탭, **u=성명/실명**)으로만 잡힘 → 제품매핑 `wishes.get(hnorm(handle))`(통합탭=**IG핸들 키**)이 실명과 불일치 → 제품 None → `제품미상` 보류 → **집행 0**.

## 수정
- `wl_auto_upload.yml` `.env` 블록에 2줄 추가 (commit 1f20de97, push 완료):
  ```yaml
  ORBITOOLS_USER=${{ secrets.ORBITOOLS_USER }}
  ORBITOOLS_PASS=${{ secrets.ORBITOOLS_PASS }}
  ```
- 내일 무인 run 자동 복구. 멱등(covered_sets)이라 중복 생성 없음.

## ⚠️ 제품미상 ≠ 제품 정보 없음 (핸들↔제품 조인 버그)
`제품미상` 으로 보류된 건들도 **폼 투고완료탭 col11「お受け取りいただいた商品」에 제품이 기재돼 있음**. 파이프라인이 통합탭을 IG핸들 키로만 조회해서, 실명으로 잡힌 건(또는 DK 미크롤 건)은 제품을 못 찾을 뿐.
- 핸들 역추적법: `GET /{GROS_IG}/branded_content_advertisable_medias?permalinks=[sc]` → media id → `GET /{media_id}?fields=username` (SYS토큰). advertisable 반환=WL권한 OK 동시 확인.
- 재발방지 후보(미적용·세은 검토): 통합탭 핸들매칭 실패 시 **투고완료 폼 제품(col11)로 폴백**.

## 2026-10-07 수동 보강 결과 (총 7건 생성+ON)
- would_upload였으나 음악블록 3건(rarayuyu·kani_fam·azustagram=subcode 2875030, 광고불가).
- 집행 7: somatoma_mama·sana_ikuzi(둘 다 3867026 권한대기 DM발송)·miku730mom(유상)·pichi_nyonyoneko(平井もも 스텐200)·izuki__log(深田満妃 스텐300)·sakubo__diary(長谷部愛梨 PPSU300)·unichan_uniuni7(渋谷彩七 원터치300). 후 4건 IN_PROCESS 클린.
- pipirara_baby_77 = WL권한없음(advertisable 미반환).

[[reference_wl_d3_auto_upload_pipeline]] · [[reference_jp_autoupload_cloud_migration]] · [[reference_wl_ad_turnon_precheck_issues]] · [[reference_wl_partnership_ad_permission]]
