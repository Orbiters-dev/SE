---
name: WL 파트너십 광고 권한 3종 + 3867026 진단 정본
description: WL 광고가 "hasn't shared permission to run partnership ads"(3867026)로 막힐 때 원인·해결. account-level 승인만으론 기존 게시물 부스팅 안 됨(태그 필수). 확실한 해결=파트너십 광고 코드.
metadata:
  type: reference
---

WL(화이트리스팅) 광고가 Meta에서 `effective_status=WITH_ISSUES` + `error_code 3867026`("{handle} hasn't shared permission with you to run partnership ads")로 막히는 건의 원인·해결 정본 (2026-09-29 harura 건 규명, Meta 공식문서 검증).

## 진단 (Graph read-only)
- 광고 상태: `GET {CAMPAIGN_ID}/ads?fields=name,effective_status,issues_info{error_code,error_message},creative{instagram_user_id,source_instagram_media_id}` (wl_auto_upload.py get/post 재사용, act_4117678028561958, sponsor GROS_IG=grosmimi_japan 17841473805016400)
- 부스팅 가능 여부(콘텐츠레벨 실효): `GET {GROS_IG}/branded_content_advertisable_medias?permalinks=[릴스URL]` (SYS 토큰). **빈 data = 우리 계정에서 그 게시물 부스팅 불가**(권한 미실효). 이게 최종 게이트.
- 진단 스크립트: .tmp/wl_perm_check.py (캠페인 광고 전량 스캔 + 3867026/3867111 분류)

## 권한 3종 (Meta 공식 — help/442108830566254)
1. **account-level 승인** (인플루언서: 프로필→메뉴→클리에이터/비즈니스→パートナーシップ広告→広告パートナー→承認待ちのリクエスト→承認) — help/647678660893116
   - ⚠️ **기존 게시물 부스팅엔 그 게시물이 우리를 태그(유료 파트너십 라벨·@멘션·피플태그·상품태그·Collab)해야만 적용.** 태그 없는 순수 오가닉 릴스는 account-level 승인해도 **안 풀림**(3867026 지속). ← harura 실측 근본원인.
2. **content-level 토글** (그 게시물에서 "ブランドパートナーが宣伝することを許可" ON + 유료 파트너십 태그) — help/606568693172555
3. **파트너십 광고 코드** — 인플루언서가 게시물에서 코드 생성→우리에게 공유→우리가 부착. **태그 여부 무관·어떤 게시물이든 부스팅 가능. 코드=동시 2 광고주까지.** ⇒ **바인딩 문제 우회하는 확실한 해결.**

## 해결 우선순위
- **광고 코드(3번)가 정답** — WL은 인플루언서 오가닉 릴스를 부스팅하는 구조라 대개 우리 태그가 없음 → account-level만으론 실효 안 됨. 코드 요청이 결정적.
- account-level "다시 승인" 재발송(A)은 태그 없는 게시물엔 무효(2026-09-29 harura 검증: 재게시해도 즉시 3867026 복귀).

## 2026-09-29 미해결 잔여 (4건, 같은 원인 가능성)
@emaa_331(유상)·@_musukono_kiroku·@mari__threelife·@boss_to_papa — 전부 3867026·advertisable 빈값. harura는 광고코드로 세은이 직접 부착(해결중). 나머지도 코드 방식 권장.

## 2026-09-30 업데이트 — @emaa_331 해소 확인
@emaa_331 인플루언서가 「設定させていただきました」 알림 → read-only 재검증: 광고 `Y26M09D17_..._WL-P_EMAA_331_...` = effective_status **ACTIVE**·adset ACTIVE·**issues null**. 게재 정상. ⚠️ **advertisable_medias는 여전히 빈값이나 코드/파트너십(WL-P) 광고엔 미반영** — 태그기반 계정승인 전용 엔드포인트라 코드 방식 광고의 실효 판정에는 부적합. 즉 **"advertisable 빈값=부스팅 불가"는 코드 방식엔 적용 안 됨** → 코드 방식 실효 판정은 **광고 effective_status(ACTIVE)+issues(null)**가 권위 신호. 진단 .tmp/emaa_perm_check.py. 집행기간=최대 6개월(세은).

## 2026-10-12 업데이트 — 인플루언서측 「パートナーシップのラベルと広告」 메뉴 자체 미표시 케이스 (西山れな @kirari_rmama7.7.7)
- **클리에이터 프로계정+최신앱인데도 게시물 「…」 메뉴에 항목 부재** (스크샷 실증). 공식·업계 가이드에도 「アカウントによっては表示されないこともあります」로만 명기 — **복구 절차 미문서화 → 메뉴 찾게 하는 건 막다른 길.**
- 신규 투고 화면 한정 우회(詳細設定→ブランドコンテンツ→タイアップ投稿ラベルON)는 기투고엔 부적용.
- **대체경로 = 1번(account-level) 활용**: 게시물을 공동투고(コラボ)로 설정(기투고: 編集→タグ付け→共同投稿者を招待) → 우리가 account-level 리퀘스트 발송 → 인플 승인 (設定とアクティビティ→パートナーシップ広告→承認待ちのリクエスト). コラボ=유효 태그(help/442108830566254 명기)라 광고코드 없이 집행 가능.
- 코드(3번)가 불가능한 상황에서의 차선. 실효 검증은 광고 effective_status ACTIVE + issues null.

## 2026-10-19 — 공동투고 설정 여부 판별 수단 주의 (片平 건 오판)
- **익명 공개 릴 HTML/og 메타데이터에는 공동투고자(collaborator)가 표시되지 않음** — HTML 전체에 우리 핸들 0회여도 미설정 단정 금지 (片平 건: 내가 "미설정" 오판 → 세은 앱 확인으로 설정 완료 정정).
- 현재 확실한 판별 = **세은 앱 육안** (우리 계정 프로필에 해당 릴 노출 여부). API: `{GROS_IG}/media`는 앱 권한 부족(code 10)·branded_content_advertisable_medias는 토큰 제약으로 로컬 확인 불가 (2026-10-19 실측).

관련: [[reference-meta-wl-branded-ad-api-creation]]·[[reference-meta-wl-url-swap]]·[[feedback-wl-ad-create-then-on]]·[[influencer-nishiyama]]
