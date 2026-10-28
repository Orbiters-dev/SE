---
name: reference-wl-ad-turnon-precheck-issues
description: "WL 광고 ON 전 issues_info 선점검 의무 — WITH_ISSUES는 ON으로 해결 안 됨. 3867026=크리에이터 권한 미부여(외부 승인 필요), 3867111=크리에이티브 dual identity 누락(재생성)"
metadata:
  type: reference
---

# WL 광고 ON 전 review 선점검 (2026-09-18 켠 3건 중 2건 사후 WITH_ISSUES)

WL(파트너십) 광고를 ON 하기 전 **`issues_info` 를 먼저 조회**해 review-clean 인지 확인한다. `WITH_ISSUES` 상태는 ON 으로 해결되지 않는다 — ON 해도 Meta 심사에서 다시 PAUSED/WITH_ISSUES 로 떨어짐.

## 9/18 사고 경위
세은 "켜" 지시로 D16/D17/D18 3건 ON. D18만 ACTIVE 정착, D16·D17은 심사에서 걸림(9/21 확인):
- **D17 EMAA 은 켜기 전 이미 `PAUSED/WITH_ISSUES`** 였음 — 플래그만 하고 켰으나 ON 으로 해결 안 되는 권한 문제였음. ON 전 issues_info 를 봤어야 함.

## 주요 에러코드 (WL 파트너십)
| error_code | 의미 | 조치 |
|---|---|---|
| `3867026` | 크리에이터가 파트너십 광고 권한 **미부여/만료** | **외부 승인 필요** — 게시 시 크리에이터에 IG DM 권한요청 자동 발송, 승인 전까지 pending. 리공이/인플루언서 매니저 루트. 메타몽이 못 고침. |
| `3867111` | 크리에이티브에 **두 신원(광고주+크리에이터) 중 하나 누락** ("select both first and second identities") | **크리에이티브 재생성** — `instagram_user_id`(크리에이터) + `instagram_branded_content={sponsor_id:GROS_IG}` 둘 다 있어야 함. 재생성 시 고쳐질 수 있음. |

- 조회: `GET /{ad_id}?fields=name,effective_status,issues_info,ad_review_feedback`.
- IH(자사) 광고는 파트너십 아님 → 이 에러 해당 없음(9/18 IH 260915 정상 ACTIVE).

관련: [[reference_meta_wl_branded_ad_api_creation]] · [[reference_meta_wl_url_swap]] · [[feedback_wl_ad_create_then_on]] · [[reference_ih_video_source_drive_naming]]
