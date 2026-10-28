---
name: reference-weekly-funnel-data-sources
description: 주간/월간 인플루언서 퍼널·채널 성과 실측 데이터 소스 정본 (DocuSeal 계약·DK content_posts·심사시트·Amazon JP SP·TikTok) — 재집계 재삽질 방지
metadata:
  type: reference
---

주간 리포트 덱 / 인플루언서 퍼널 집계 시 재사용하는 **실측 소스 + 분리 규칙** (2026-10-02 확립).

## 계약 (DocuSeal)
- API: `DOCUSEAL_BASE_URL`(https://docuseal.orbiters.co.kr) `/api/submissions` (⚠️ `/submissions` 아님) · 헤더 `X-Auth-Token: DOCUSEAL_API_KEY` · 페이징 `after=<last id>`.
- submission 목록 payload에 **template명은 없음**. 대신 `name`(예 "JP Contract - 小野尚華 (2026-10-01)") + `submitters[].external_id`/`application_key`(예 "GROSMIMI_JP_...") 로 **JP 그로미미 계약 분리**.
- **JP 필터** = `name.startswith("JP Contract")` OR external_id/application_key startswith "GROSMIMI_JP". **서명완료** = `completed_at` 존재(or status=='completed'). **중복제거** = `submitters[].email` 기준(인플루언서별 재발송·검수 중복 제거).
- ⚠️ raw 카운트(162 생성·82 완료)는 검수·재발송·US 등 섞임 → 반드시 JP필터+email dedup 후 보고.

## 업로드 콜라보 (DataKeeper content_posts)
- orbitools `/query/?table=content_posts&region=jp&limit=10000` + `Authorization: Bearer DK_SE_READ_TOKEN`. post_date 는 응답에서 파이썬으로 월필터(API date필터는 탐지일 기준이라 왜곡).
- **콜라보 판별** = `brand=='grosmimi'` OR `content_type=='partnered'`, `content_type=='owned'`(자사 @grosmimi_japan) 제외, platform=='instagram'. (review.ts 정본과 동일) [[reference-review-queue-partnered-and-metrics-cap]]

## 정량 (content_metrics_daily)
- D+3 오가닉 좋아요 ≥ **10**(D3_LIKES_GATE). post_date+3 ±7일 내 가장 가까운 likes 행. likes=-1=크롤실패 제외.

## 정성 심사 (Google Sheet)
- 시트 `13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE` 탭 **"JP Content Review"**. 컬럼: shortcode·post_date·ai_verdict·ai_scored_at·verdict(인간)·reviewed_at. 집행/미집행 = 인간 `verdict`. ⚠️9월 심사는 **소급**([[mistakes-20261002-retroactive-gate-as-sequential]]).

## Amazon JP SP 성과 (DataKeeper amazon_ads_daily)
- `dk.get("amazon_ads_daily", days=30)`. ⚠️**US·JP 혼재** — `brand` 필드 불신(JP 캠페인도 brand="Grosmimi"로 섞임). **분리 = `currency=='JPY'`**(JP profile_id=3736142261021843). 필드: spend·sales·clicks·impressions·purchases·campaign_name.

## TikTok Ads 성과
- API 없음 → 브라우저 수집. [[reference-tiktok-marketing-api-rejection-domain-security]] 참조(계정·URL·드라이버).

## 산출물
- 덱: `operations/jp_weekly_deck_20261002.html`(탭형 9개: 개요·RPP키워드·Overview·정성심사·9월퍼널·Meta·RPP·PPC·TikTok). Meta 성과 ssot = `.tmp/jp_meta_deck/ssot.json`. 빌더 스크립트 `.tmp/weekly_deck_1002/`.
