# Export Document Management

수출 서류 (CI/PL) 파싱, 정리, 레퍼런스 관리 워크플로우.

---

## Objective

컴퓨터 내 흩어진 CI (Commercial Invoice), PL (Packing List) 파일들을 자동 파싱하여 구조화된 데이터로 정리하고, 레퍼런스 파일을 buyer/importer별 폴더로 관리한다.

---

## Key Terms

| 용어 | 의미 | 비고 |
|------|------|------|
| **Buyer** | = **Importer** | 동일 의미. 수입자/구매자 |
| **Exporter** | 수출자 (한국 측) | ORBI, LFU, 브랜드사 등 |
| **Final Consignee** | 최종 수하인 | WBF, CGETC, Shipbob, DTrans 등 |

---

## Entity Abbreviations

| Full Name | Abbreviation | Role |
|-----------|-------------|------|
| LittlefingerUSA Inc. | **LFU** | Exporter or Buyer/Importer |
| Orbiters CO., LTD | **ORBI** | Exporter |
| Fleeters Inc. | **FLT** | Buyer/Importer |
| Walk by Faith | **WBF** | Final Consignee |
| CGETC Inc. | **CGETC** | Final Consignee |
| Shipbob | **Shipbob** | Final Consignee |
| DTrans (Dream Trans) | **DTrans** | Final Consignee |
| Klemarang (Nature Love Mere) | **NLM** | Exporter (brand) |

---

## Tools

### 1. `tools/parse_export_documents.py`

CI/PL 파일 탐색 및 파싱.

**Input**: Z: 드라이브 내 CI/PL 소스 폴더들
**Output**:
- `Data Storage/Export Document/Export_Document_Summary.xlsx` (3 시트)
- `Data Storage/Export Document/Export_Document_Data.json` (구조화 JSON)

**추출 필드**: date, brand, shipping, total_amount, currency, exporter, importer, destination, items, price_terms, invoice_no

**소스 폴더**:
- `Z:\Orbiters\CI, PL, BL\` — 브랜드별 PDF (Grosmimi, Alpremio, BabyRabbit 등)
- `Z:\Orbiters\발주 서류 관리\` — 브랜드별 Excel (LFU발주, 꼬메모이, 내아이애 등)

---

### 2. `tools/reorganize_export_references.py`

레퍼런스 파일 정리 및 폴더 분류.

**Input**: `Export_Document_Data.json` (Step 1 결과)
**Output**: `Data Storage/Export Document/reference/` 하위에 buyer/importer별 폴더

**폴더 구조**:
```
reference/
  LFU/    ← buyer/importer가 LFU인 건
  FLT/    ← buyer/importer가 FLT인 건 (기본)
```

**파일명 형식**: `년월_브랜드_운송방식_Exporter_Importer_FinalConsignee_Destination.ext`

예시: `2024-10_Grosmimi_SEA_LFU_FLT_WBF_USA.xlsx`

---

## Deduplication Rules

- 중복 기준: **(date, brand, shipping)** 조합이 동일하면 같은 건
- Excel과 PDF 무관 — 같은 내용이면 무조건 1개만 유지
- 숫자가 살짝 다른 건도 같은 건으로 취급 → **최신 파일(mtime 기준)** 유지
- shipping이 다르면 (AIR vs SEA) 별도 건으로 유지

---

## Workflow Steps

### Step 1: 파싱
```
python tools/parse_export_documents.py
```
- 모든 CI/PL 소스 폴더를 스캔
- Excel과 PDF 양식 모두 파싱
- 중복 제거 (같은 건이 PDF와 Excel로 존재하는 경우)
- JSON + Excel로 출력

### Step 2: 중복 제거 (필요 시)
- JSON 데이터에서 (date, brand, shipping) 기준으로 그룹핑
- 같은 그룹 내 여러 파일 → 최신 mtime 파일만 유지
- 나머지 삭제 후 JSON 재저장

### Step 3: 레퍼런스 정리
```
python tools/reorganize_export_references.py
```
- JSON 데이터 기반으로 원본 파일 복사
- 축약된 이름으로 파일명 생성
- Final Consignee 추출 및 추가
- buyer/importer별 폴더 분류

---

## Brands Covered

Grosmimi, Naeiae, Conys, Nature Love Mere, Alpremio, BabyRabbit, BambooBebe, Commemoi, BeeMyMagic, Hattung, Cha&Mom, Orbiters Direct

---

## Data Location

```
Data Storage/Export Document/
  Export_Document_Summary.xlsx   ← 요약 Excel (3 시트)
  Export_Document_Data.json      ← 구조화 JSON (Claude 참조용)
  reference/
    LFU/                         ← LFU buyer 건
    FLT/                         ← FLT buyer 건
```

---

## Future Task

유저가 발주 제품, 대상지, 수입자, 수출자를 알려주면 레퍼런스 파일 기반으로 CI, PL, CO 문서를 자동 생성해야 함.

---

## Edge Cases & Lessons Learned

- cmd.exe / PowerShell에서 한글 인코딩 문제 → Python 스크립트로 해결
- Excel CI/PL 양식이 브랜드마다 다름 (10+ 레이아웃) → 여러 패턴 지원
- PDF에서 회사명 대신 날짜가 추출되는 경우 있음 → 날짜 패턴 필터링
- "Total PKG" 행의 수량이 금액으로 잡히는 경우 → PKG 키워드 제외
- 같은 shipment가 PDF + Excel로 존재 → normalize_shipment_key()로 중복 제거
- Z: 드라이브는 매핑 드라이브 → git bash에서 `/z/` 불가, Windows 경로 사용
