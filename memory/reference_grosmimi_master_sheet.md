---
name: Grosmimi Master 시트 구조 (운영기간/Creator ID/Deal Type 등)
description: 시트 1wkue4G7... Grosmimi 탭은 row 1 빈줄 + row 2 카테고리 헤더 + row 3 실제 컬럼 헤더 + row 4부터 데이터.
type: reference
---
시트 ID: `1wkue4G7FP_fiVeqSmMp7Z6IsIMmvOIc93TBb0NwcAmU`
탭: `Master DB` / **`Grosmimi`** / `influencer List` / `Influencer Search`

## Grosmimi 탭 헤더 구조

| Row | 내용 |
|---|---|
| 1 | 빈 행 (`row_values(1)` → `[]`) |
| 2 | 카테고리 헤더 (`Workflow Management` / `Content` / `Commercial Terms` / `Performance Evaluation` / `Notes`) |
| 3 | **실제 컬럼 헤더** (운영기간 / Internal ID / Creator name / Creator ID / Platform / ...) |
| 4+ | 데이터 행 |

→ Python에서는 `headers = rows[2]` / 데이터 루프 `rows[3:]`.

## 주요 컬럼 (row 3 헤더, 줄바꿈 포함된 것 있음)

| 컬럼 | 내용 | 노션 매핑 |
|---|---|---|
| `Creator ID` (줄바꿈 포함 `Creator\nID`) | 인스타 핸들 (no `@`) | `instagram handle ` (앞에 `@` 붙임) |
| `Deal Type` | `Paid` / `Unpaid` | `paid?` (`paid` / `gift`) |
| `Product` | 예: `stain300-bear`, `ppsu300-pink`, `fliptop-Unicorn`, `PPSU 200ml White` | `SKU명` (파싱) |
| `Status` | Uploaded / Delivered / Shipping / Guideline Sent / ... | `진행 상태` (수동 매핑) |
| `WL code` | `adcode-...` | `WL code` |
| `URL` | IG 게시물 URL | `링크` |
| `PIC` | Kazuki / Seeun / Kasumi / heo seeun | `Person`/`담당자` (people 매칭 어려움 — skip) |
| `Ad code` | 별도 광고 코드 | (필요 시) |
| `Expected Upload` | 예상 게시일 | `Post Date` (대부분 비어있음) |

## Product → SKU명 파싱 룰

| 시트 product 패턴 | SKU명 옵션 |
|---|---|
| `stain*`, `Stainless *` | `Stainless` |
| `ppsu*`, `PPSU *` | `PPSU` |
| `fliptop*`, `Flip top *` | `Flip top` |
| `빨대` | `빨대` |

## Deal Type → paid? 매핑
- `Paid` → `paid`
- `Unpaid` → `gift`

## 컬럼 헤더 룩업 패턴 (줄바꿈 안전)
```python
def find_col(headers, needle):
    for i, h in enumerate(headers):
        if needle.lower() in (h or "").lower().replace("\n", " "):
            return i
```
