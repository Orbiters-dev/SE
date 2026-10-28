---
name: 가이드라인 카테고리 매칭 룰 — 영상 컨셉 우선, 제품 라인 단독 매칭 X
description: 가이드라인 링크는 영상 컨셉 기반 매칭. 일상/외출/생활/持ち歩き 컨셉 = natural_sp. 제품 라인만으로 sus_category_A / ppsu_X 자동 매칭 X.
type: reference
---

## 카테고리 가이드라인 링크 (6+1)

| 코드 | 컨셉 | 링크 |
|---|---|---|
| natural_sp | **일상·외출·持ち歩き·생활** (디폴트) | https://orbiters-dev.github.io/KAZUKI/grosmimi_guideline_natural_sp.html |
| categories_sp | 카테고리 전체 안내 | https://orbiters-dev.github.io/KAZUKI/grosmimi_guideline_categories_sp.html |
| A: ppsu_category_A | PPSU 소재 강조 | .../grosmimi-guidelines/ppsu_category_A.html |
| B: ppsu_category_B | PPSU 새지 않는 (逆流防止) | .../grosmimi-guidelines/ppsu_category_B.html |
| C: ppsu_category_C | PPSU 발달 (Stroke Stage) | .../grosmimi-guidelines/ppsu_category_C.html |
| D: ppsu_category_D | PPSU 손질 편함 | .../grosmimi-guidelines/ppsu_category_D.html |
| E: ppsu_category_E | PPSU 위생/곰팡이 | .../grosmimi-guidelines/ppsu_category_E.html |
| F: sus_category_A | ステンレス 의료 그레이드 | .../grosmimi-guidelines/sus_category_A.html |

## 매칭 룰

1. **영상 컨셉 우선**. 인플루언서가 「持ち歩き・외출 사용」「日常で使う」「育児の様子」 같은 일상 컨셉 합의 시 → `natural_sp`.
2. **제품 라인 (ステンレス / PPSU) 만으로 자동 sus_category_A / ppsu_X 매칭 X**. 라인 정보는 메인 테마 추천 단락에만 활용.
3. 인플루언서가 「PPSU 소재」「漏れない」「발달」 같은 특정 포인트 명시 → 해당 ppsu_X 또는 sus_A 매칭.
4. 컨셉 정보 부족 시 → 디폴트 `natural_sp`.

**Why:** 2026-05-22 長尾様 케이스에서 ステンレス 라인 → `sus_category_A` 자동 매칭. 세은 강한 교정 「이거 말고 / 일상 가이드라인 말야」. 長尾様 영상 컨셉 = 「持ち歩き・외출」 = 일상 = `natural_sp`. 제품 라인 단독 매칭은 오답.

**How to apply:**
- STEP 5/10.5 영상 방향 합의 후 가이드라인 송부 시 컨셉 키워드 먼저 추출
- 일상/외출/生活/持ち歩き/おうち/お出かけ → `natural_sp`
- 제품 특장점 메인 테마 합의 시에만 ppsu_X / sus_A
- 모르면 `natural_sp` 디폴트 (오답률 최소)
