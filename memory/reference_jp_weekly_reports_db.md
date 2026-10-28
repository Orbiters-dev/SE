---
name: JP Weekly Reports Notion DB + 인플루언서 관리 시트
description: 매주 Seeun/Kazuki/Jisun이 OKR 페이지 작성하는 DB ID + 인플루언서 데이터 baseline 시트 ID + 컬럼 매핑.
type: reference
---

# JP Weekly Reports DB + 인플루언서 관리 시트

## Notion DB
- **DB ID**: `2fc86c6dc0468000a671e3ed32083c8f`
- **DB title**: JP Weekly Reports
- **URL**: https://www.notion.so/2fc86c6dc0468000a671e3ed32083c8f
- **properties**:
  - `Report File` (title) — 페이지 제목 (예: "JP Weekly Report Template - Seeun")
  - `Report Date` (date)
  - `Member` (phone_number)
  - `Last Edited` (formula)
  - `Week` (formula)
- **페이지 작성자별**:
  - Seeun (JP 인플루언서·IG 운영) — 매주 Sun 작성
  - Kazuki (Rakuten·Amazon 운영)
  - Jisun (Meta 광고 운영)

## 인플루언서 관리 시트 (baseline)
- **Sheet ID**: `1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU`
- **URL**: https://docs.google.com/spreadsheets/d/1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU
- **탭**:
  - `Master DB` (gid=0)
  - `Grosmimi` (gid=386147805) ← JP 인플루언서 메인
  - `influencer List` (gid=2007940503)
  - `Influencer Search` (gid=1294482195)

### Grosmimi 탭 컬럼 매핑 (header at row 3)
- 0: 운영기간 (월/2026 또는 빈값)
- 2: Creator name (본명)
- 3: Creator ID (IG handle)
- 4: Platform / 5: Deliverable Type / 6: Product
- 7: PIC (Seeun / Kazuki / Kasumi)
- 8: Status (Uploaded / Shipping / Delivered / Guideline Sent)
- 9-13: 일정 (Brief Sent / Delivery Date / Draft Received / Final approved / Expected Upload)
- 16: URL (게시 URL)
- 23: Deal Type / 24: Fee(JYP) / 25: Commission Rate
- 31: Payment Status (Paid / Unpaid)
- 32: Payment Date
- 33: Views / 34: Likes / 35: Comments / 36: Saves

### 필터 패턴
- W18 활동 = `PIC=Seeun` AND (`운영기간 in ['5월/2026', '']`) AND `Status in ['Uploaded','Shipping','Delivered','Guideline Sent']`
- 4월/2026 entries는 W17 이전 보고 완료 → 이번 OKR에서 제외
- 빈 운영기간 = 진행 중 (Shipping/Delivered/Guideline Sent)

## 사용 도구
- Notion API: `NOTION_API_TOKEN` (.env)
- Sheets API: service account `credentials/google_service_account.json`
- IG followers: `tools/fetch_ig_profile.py --handle <handle>`
- IG posts: `tools/deep_crawler.py --handles <handle> --max-posts 30 --raw-json`

## OKR 표 KR (5개)
1. New SKUs PREP — Target 10
2. Produce 300 contents (paid+gifting) — Target 300
3. Build 100 reviews on Rakuten — Target 100
4. 시딩 운영 — Target 월 1,000
5. Achieve 10,000 IG Followers — Target 10,000
