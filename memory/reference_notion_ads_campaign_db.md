---
name: Notion Ads Campaign List DB 스키마 (paid? / SKU명 / 유형 옵션)
description: 그로미미 광고 캠페인 노션 DB 컬럼 + select 옵션. Multi-source DB라 2025-09-03 API 필수.
type: reference
---
**Parent DB id:** `f4586c6d-c046-83e4-bd0a-01cfbdd39771` (page URL: notion.so/f4586c6dc04683e4bd0a01cfbdd39771)
**Main data source id:** `23f86c6d-c046-8393-ac65-078ed9ebee05` (name: `Ads Campaign List`)
**API:** Multi-source. `Notion-Version: 2025-09-03` 필수. data_source 엔드포인트.

## 컬럼 + type + 옵션

| Notion 컬럼 | type | 옵션 / 비고 |
|---|---|---|
| `메타광고제목(지선)` | title | 지선 영역. 비울 때 `" "` 공백 한 칸. |
| `instagram handle ` (끝에 space 주의) | email | 값은 `@핸들` 형태로 저장. |
| `Post Date` | date | 우리(메타 운영) 영역 — 시트 Expected Upload 매핑. |
| `유형` | select | `klaviyo`, `Google`, **`Meta \| JP`**, `Meta \| US`. JP 브랜드는 `Meta \| JP`. |
| `속성` | multi_select | `Image`, `Video`, `WL`. 기본 셋업은 `[WL]`. |
| `Person` | people | user ID 필요. 시트 PIC 문자열로 자동 매칭 어려움 — 보통 비워두고 세은이 수동. |
| `담당자` | people | 동상 — 자동 매칭 X. |
| `WL code` | rich_text | `adcode-...` 그대로. |
| `링크` | url | IG 게시물 URL. |
| **`paid?`** | select | **`paid`**, **`gift`** (시트 Paid → paid / Unpaid → gift). |
| `게시일(지선) ` (끝에 space) | date | 지선 영역. 우리는 건드리지 X (메모리 `feedback_notion_meta_ads_post_date_only`). |
| `카테고리` | multi_select | `video`, `image`, `WL`. |
| `SKU명` | multi_select | `Flip top`, `Stainless`, `PPSU`, `빨대`. |
| `마감일` | date | 보통 비어있음. |
| `진행 상태` | status | `예정 또는 진행중`, `대기 중`, `게시 완료(JS)`. 기본 셋업은 `예정 또는 진행중`. |

## 신규 페이지 생성 페이로드 (최소 셋)
```python
{
  "parent": {"data_source_id": "23f86c6d-c046-8393-ac65-078ed9ebee05"},
  "properties": {
    "메타광고제목(지선)": {"title": [{"text": {"content": " "}}]},
    "instagram handle ": {"email": f"@{handle}"},
    "유형": {"select": {"name": "Meta | JP"}},
    "속성": {"multi_select": [{"name": "WL"}]},
    "paid?": {"select": {"name": "paid"}},   # or "gift"
    "SKU명": {"multi_select": [{"name": "PPSU"}]},  # or Stainless / Flip top / 빨대
    "진행 상태": {"status": {"name": "예정 또는 진행중"}},
    "WL code": {"rich_text": [{"text": {"content": "adcode-..."}}]},  # optional
    "링크": {"url": "https://..."},  # optional
  }
}
```

## 컬럼명 함정
- `instagram handle ` 끝에 **공백** — 키 매칭 시 정확히 일치 필수.
- `게시일(지선) ` 끝에 **공백** — 동상.

## paid? 옵션 ID
- `paid`: 임의 — `{"select": {"name": "paid"}}` 으로 충분 (name 매칭).
- `gift`: 동상.

## 운영 룰
- `paid?` 일괄 sync는 시트 Grosmimi 탭 `Deal Type` → Paid/Unpaid → paid/gift.
- 시트엔 있고 노션엔 없는 인플루언서는 위 페이로드로 신규 페이지 생성 (Post Date·Person·담당자는 skip).
- 새 컬럼/옵션 만들지 않는다. 노션 UI에서 세은이 직접 추가.
