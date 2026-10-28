---
name: Notion multi-source DB는 2025-09-03 API + data_source 엔드포인트 사용
description: GET /v1/databases/{id} 400 + `multiple_data_sources_for_database` 에러 시 신규 API 버전으로 data_source 엔드포인트 사용.
type: reference
---
Notion DB가 multi data source 구조면 (예: `additional_data.error_type = "multiple_data_sources_for_database"`) 2022-06-28 API에서 GET/POST 둘 다 400. `Notion-Version: 2025-09-03` + `data_source` 엔드포인트 사용.

## 에러 식별
```json
HTTP 400 {"code":"validation_error",
  "message":"Databases with multiple data sources are not supported in this API version.",
  "additional_data":{"error_type":"multiple_data_sources_for_database",
    "child_data_source_ids":["...","..."],
    "minimum_api_version":"2025-09-03"}}
```

## 작동 패턴

**스키마 조회 (2022-06-28 ❌ / 2025-09-03 ✅):**
```
GET /v1/data_sources/{data_source_id}
```

**페이지 query (2022-06-28의 `/v1/databases/{id}/query` 대체):**
```
POST /v1/data_sources/{data_source_id}/query
```

**페이지 생성 (parent → data_source_id):**
```json
POST /v1/pages
{
  "parent": {"data_source_id": "23f86c6d-..."},
  "properties": {...}
}
```

**페이지 update (변경 없음):**
```
PATCH /v1/pages/{page_id}  body: {"properties": {...}}
```

## Ads Campaign List (Grosmimi)
- Parent DB id: `f4586c6d-c046-83e4-bd0a-01cfbdd39771`
- Data source id (main): `23f86c6d-c046-8393-ac65-078ed9ebee05` ("Ads Campaign List")
- Data source id (보조 — empty name): `6a786c6d-c046-8209-a64c-87b91efb10fe`

## 헤더 set 예시 (Python urllib)
```python
H = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json",
}
```
