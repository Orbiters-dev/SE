---
name: Meta JP 영구 토큰 = System User 토큰 (재발급 재발 종료, 2026-09-08)
description: WL branded resolve용 GROSMIMI_JP_API 단기토큰 매세션 재발급 지옥 종료. claude_meta_jp 시스템유저 만료없는 토큰을 .env META_JP_SYSUSER_TOKEN에 영구 저장.
metadata:
  type: reference
---

# Meta JP 영구 토큰 (System User) — 2026-09-08 세은 발급

7/7~9/2 내내 GROSMIMI_JP_API(1456998555820600) **단기 유저토큰(1~2h)**을 Graph Explorer로 매세션 재발급 → 죽음 반복 (세은 "오천번은 했겠다" 폭발). **근본 해결 = System User 토큰(만료 없음).**

- **저장 위치**: `.env` `META_JP_SYSUSER_TOKEN=` + `.tmp/jpapi_token.txt` (기존 wl_complete/watchdog 호환). 값 debug: `expires_at:0`·`type:SYSTEM_USER`·app=GROSMIMI_JP_API·스코프에 `instagram_branded_content_ads_brand` 포함 → resolve 영구 작동.
- **발급 경로**: business.facebook.com → Business Settings → System Users → **claude_meta_jp**(ID 61589460020744, 우리 JP 자동화용. Conversions API/LEE는 딴 용도) → Generate New Token → App=GROSMIMI_JP_API → **Expiration=Never** → 스코프 6개(ads_management·business_management·instagram_basic·instagram_branded_content_ads_brand·pages_show_list·pages_read_engagement).
- **역할 분리 유지**: resolve·business_discovery·advideos = **SYS 토큰**. 크리에이티브·광고 생성 = **LIVE**(META_JP_ACCESS_TOKEN, claude connection, dev모드 우회). [[reference_meta_wl_branded_ad_api_creation]] 레시피 그대로.
- **메모리 오기 정정**: "앱시크릿 로컬 부재/대체루트 전멸"은 claude connection 앱 기준일 뿐. FB_APP_SECRET(.env)=claude connection(1570) 것(GROSMIMI 1456 아님, client_credentials로 확정). claude connection 앱은 IG branded 권한 자체가 없어 유저·Page(만료없음)·앱 토큰 전부 resolve `(#1)`/`(#10)` 死 — 그래서 GROSMIMI_JP_API System User가 유일 해법.
- **Page 토큰 부산물**: LIVE로 `GET /880831635120245?fields=access_token` → grosmimi Page 토큰(`expires_at:0` 만료없음) 획득 가능. 단 IG 스코프 없어 resolve엔 무용. (`/me/accounts` 빈배열이라도 Page 직접조회는 됨.)

관련: [[reference_meta_wl_branded_ad_api_creation]] · [[reference_meta_wl_testing_gate_criteria]]
