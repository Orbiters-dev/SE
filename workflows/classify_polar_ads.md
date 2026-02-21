# Polar Ads 카테고리 분류 워크플로우

## 목적
Polar Analytics에서 내보낸 광고 성과 데이터(`Polar Ads 카테고리 분류_Raw.xlsx`)의
**I열(Product Brand)** 과 **J열(Product Category Ads)** 를 자동으로 채운다.

## 필요 파일 및 전제조건

| 파일 | 역할 |
|------|------|
| `Data Storage/Polar Ads 카테고리 분류_Raw.xlsx` | 채워야 할 원본 파일 (Sheet: "ads Copy (1)") |
| `Data Storage/Product Variant New Number - Polar Analytics.xlsx` | SKU → Brand/Category 참조 (Sheet: "Custom Report", B열 SKU → E열 Category → F열 Brand) |
| `.tmp/facebook_ads.xlsx` | 캠페인별 랜딩 URL 참조 |
| `.env` | SHOPIFY_ACCESS_TOKEN, SHOPIFY_SHOP |

> **.tmp/facebook_ads.xlsx가 없거나 오래된 경우** → 먼저 `fetch_facebook_ads.py` 실행

---

## 실행 방법

```bash
"C:\Users\wjcho\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 tools/classify_polar_ads.py
```

매 실행 시 **전체 718행을 재처리** (덮어쓰기)

---

## 분류 로직 (행 단위, 우선순위 순)

> **핵심 원칙**: Ad명에 브랜드 키워드가 있으면 캠페인 URL보다 항상 우선 적용.
> 멀티브랜드 캠페인(예: Grosmimi PPSU 캠페인 안에 Easy Shower Ad가 섞여 있는 경우)에서
> Ad 단위가 가장 구체적인 정보이기 때문.

### 1순위: Ad명(E열) 키워드 추론
- Ad명에 브랜드 키워드가 있으면 캠페인 URL 분류보다 우선 적용
- 예: `easy shower support handle` → Easy Shower (캠페인이 Grosmimi PPSU여도 무시)
- 예: `commemoi adjustable book stand` → Comme Moi / Comme Moi Book Stand
- 예: `grosmimi ppsu straw cup | 1.24` → Grosmimi / PPSU Straw Cup
- 예: `wl_dentalmom_aug25_grosmimi_basic ppsu300` → Grosmimi / PPSU Straw Cup

### 2순위: Adset명(C열) 키워드 추론
- Ad명에서 브랜드를 못 찾은 경우 Adset명으로 재시도

### 3순위: Facebook Ads 랜딩 URL → Shopify 제품 API → SKU 매칭
- 캠페인 ID로 `.tmp/facebook_ads.xlsx`에서 랜딩 URL 조회
- URL 유형 분기:
  - `/products/[handle]` → Shopify API로 SKU 조회 → Product Variant 파일에서 Brand/Category
  - `/collections/[collection]` → 컬렉션명으로 브랜드 추론
  - `/discount/...`, Target.com, Amazon.com 등 외부 URL → Non-classified/Non-classified

### 4순위: 캠페인명(A열) 키워드 추론
- URL 분류 실패 시 캠페인명으로 브랜드 추론

### 최종 fallback
- 모두 실패 → **Non-classified / Non-classified**

---

## 브랜드 키워드 규칙

| 키워드 | 브랜드 | 비고 |
|--------|--------|------|
| grosmimi, grosm, grossmimi, gm | Grosmimi | gm = Grosmimi 약자 |
| ppsu | Grosmimi | PPSU는 Grosmimi 전용 제품군 |
| stainless steel, sls cup | Grosmimi | Grosmimi 전용 |
| straw, straw cup | Grosmimi | Grosmimi 전용 (단, PPSU vs Stainless 구분 불가 시 Category는 Non-classified) |
| beemymagic, beemy | Beemymagic | |
| naeiae | Naeiae | |
| rice snack, pop rice | Naeiae | Naeiae 전용 제품군 |
| babyrabbit, baby rabbit | BabyRabbit | |
| alpremio | Alpremio | |
| cha&mom, cha mom, cm | CHA&MOM | cm = CHA&MOM 약자 |
| skincare, lotion, hair wash, body wash | CHA&MOM | CHA&MOM 전용 제품군 |
| hattung | Hattung | |
| commemoi, comme moi, commemo | Comme Moi | |
| easy shower, shower stand | Easy Shower | |
| bamboobebe | BambooBebe | |
| ride & go, ridego | RIDE & GO | |
| zezebaebae (단독) | Non-classified | 스토어명이지 브랜드 아님 |
| dsh | Non-classified | 멀티브랜드 캠페인 → Ad명으로 분류 |

### 브랜드별 기본 카테고리 (제품 특정 불가 시)
| 브랜드 | 기본 Category |
|--------|--------------|
| Alpremio | Alpremio Seat |
| BabyRabbit | Non-classified |
| Beemymagic | Beemymagic |
| CHA&MOM | Non-classified |
| Grosmimi | Non-classified |
| Hattung | Hattung |
| Naeiae | Naeiae Pop Rice Snack |
| Easy Shower | Easy Shower |
| RIDE & GO | RIDE & GO |

---

## 제품군 계층 구조 (Product Variant 파일 기준)
- B열 (SKU) ⊂ D열 (Product_Variant_New) ⊂ E열 (Product_Category_Ads) ⊂ F열 (Product_Brand)
- J열에는 E열 값 (Category), I열에는 F열 값 (Brand)을 사용

---

## 데이터 업데이트 주기 및 재실행

1. Polar Analytics에서 새 데이터 export → `Data Storage/Polar Ads 카테고리 분류_Raw.xlsx` 교체
2. Facebook Ads 데이터 갱신이 필요하면 먼저 `fetch_facebook_ads.py` 실행
3. `classify_polar_ads.py` 실행 (전체 재처리)

---

## 엣지 케이스 처리

| 상황 | 처리 |
|------|------|
| 멀티브랜드 캠페인(dsh 등) | Ad명에서 브랜드 개별 분류 (1순위) |
| Grosmimi PPSU 캠페인 안에 타 브랜드 Ad | Ad명 우선 → Easy Shower, Comme Moi 등 정확히 분류 |
| Non-classified URL 캠페인 (AMZ, Target 등) | Ad명에 브랜드 있으면 Ad명 기준 |
| wl_[인플루언서]_[브랜드]_[제품] 형식 Ad명 | 브랜드+제품 키워드 파싱으로 정확히 분류 |
| 랜딩 URL 여러 개 (콤마 구분) | 첫 번째 유효 분류 사용 |
| Shopify API 오류 | 경고 출력 후 텍스트 키워드 fallback |
| zezebaebae 스토어 캠페인 | 단독이면 Non-classified, URL/Ad명으로 구체 브랜드 확인 |

---

## 현재 분류 결과 (v5 기준, 718행)

> **v5 변경사항** (2026-02-19):
> - General → Non-classified 전환 (Brand/Category 모두)
> - Tumbler fallback: PPSU Tumbler → Stainless Steel Tumbler (대부분 SS Tumbler 제휴)
> - 예외: 랜딩 URL에 "ppsu tumbler" 명시된 경우만 PPSU Tumbler 유지
> - "straw" 키워드 → Brand는 Grosmimi, Category는 Non-classified (PPSU vs Stainless 구분 불가)

| 분류 | 행 수 |
|------|-------|
| Non-classified | 140행+ (기존 General 포함) |
| Grosmimi / PPSU Straw Cup | 133행 |
| Grosmimi / Non-classified | 127행 (기존 General) |
| CHA&MOM / Non-classified | 43행 (기존 General) |
| Grosmimi / Stainless Steel Straw Cup | 35행 |
| Easy Shower / Easy Shower | 29행 |
| Alpremio / Alpremio Seat | 29행 |
| Hattung / Hattung | 27행 |
| Grosmimi / Stainless Steel Tumbler | 26행 (기존 PPSU Tumbler → SS Tumbler) |
| Beemymagic / Beemymagic | 22행 |
| Comme Moi / Comme Moi Book Stand | 15행 |
| 기타 브랜드 | 나머지 |
