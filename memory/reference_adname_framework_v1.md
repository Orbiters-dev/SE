---
name: reference-adname-framework-v1
description: Meta 광고명 7토큰 규칙 (AdName Framework V1, 2026-07-01 확정)
metadata:
  type: reference
---

# AdName Framework V1 (2026-07-01 확정)

파일: `Desktop\s\パポマ\META ADS 관리용\AdName_Framework_V1_260618.md` (+부모폴더 동일 카피).
포맷: `{날짜}_{브랜드}_{채널}_{소재출처}_{크리에이터}_{제품}_{콘텐츠코드}` (구분자 `_`)

| # | 토큰 | 규칙 / 소스 |
|---|---|---|
| 1 | Y26M06D19 | 출시일 = **Meta 광고 등록일(ad.created_time)**. Graph/캐시 |
| 2 | Grosmimi | 고정 |
| 3 | **RKT** | 라쿠텐 랜딩 전부 RKT 고정 (확장 AMZ/ONZ/TP+) |
| 4 | WL-**G**/WL-**P**/IHM/IHV | **G=무상(gift) / P=유상(paid)**. 계약정보 기준 수기 |
| 5 | 크리에이터 핸들 | content_posts.username **원문 그대로**(알파벳시작·밑줄포함 OK, 치환 X) |
| 6 | ASIN | RKT·AMZ→PASIN / ONZ→SKU88 / 멀티→GENERAL. Product SSOT(`ProductSSOT-TEST_0612_임시Filled.xlsx`) |
| 7 | CT-##### | **= content_posts.id** (조인키). 문서 예시 C0051은 오표기, CT-가 정답 |

**파싱 = 앵커 기반** (위치 count X): 앞4 고정 + 뒤2 패턴(ASIN `B0`+8 / `CT-`), 그 사이 전부 크리에이터. **핸들 밑줄 치환 불필요** (알파벳시작 전제라 SKU숫자·구분자 충돌 없음). → [[mistakes-20260701b-metamong]]

ASIN→제품라인: B0G6CCJ24K=Stainless FLIPTOP / B08TZY1TFY=PPSU Straw 10oz / B0B9GLVWYN=PPSU Straw 6oz / B0DJNXD66N=PPSU FLIPTOP 10oz.
분류탭(`meta_content_classification_*_v2.xlsx` 콘텐츠분류 탭): 유형(PAID/GIFT)·제품이 광고명 토큰4·6과 일치해야 함(7/7 검증). subject/focus/hook/angle 태깅 = 세은 구글시트 작업.
