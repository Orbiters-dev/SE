# 아마존퍼포마 — Amazon PPC Agent (Shared)

Amazon PPC 분석, 최적화, 실행 에이전트. Naeiae (Fleeters Inc) 전용 executor + 전체 브랜드 분석.

---

## 위치

이 폴더는 팀 공유 폴더입니다.
- **Skill 정의**: `SKILL.md`, `references/`
- **실행 도구**: `tools/` (WJ Test1 프로젝트 기준)

실제 실행은 WJ Test1 프로젝트에서:
```
python tools/amazon_ppc_executor.py --propose
python tools/amazon_ppc_executor.py --execute
```

---

## 브랜드 & 프로파일

| Profile | Brand | Executor |
|---------|-------|---------|
| Orbitool | CHA&MOM | 분석만 |
| GROSMIMI USA | Grosmimi | 분석만 |
| Fleeters Inc | Naeiae | 분석 + 실행 |

---

## DataKeeper 연동

Amazon Ads 데이터는 DataKeeper에서 가져옴:

```python
from data_keeper_client import DataKeeper
dk = DataKeeper()
rows = dk.get("amazon_ads_daily", days=30, brand="Naeiae")
```

또는 Shared/datakeeper/latest/amazon_ads_daily.json 직접 참조.

### ⚠️ 필드명 주의 (CRITICAL)

`amazon_ads_daily` 필드명은 `spend` (cost 아님):

| DataKeeper 필드 | 의미 | 사용법 |
|----------------|------|--------|
| `spend` | 광고비 (cost) | `cost = float(row["spend"])` |
| `sales` | 광고 매출 (14d) | `sales = float(row["sales"])` |
| `campaign_id` | 캠페인 ID | `campaignId = row["campaign_id"]` |
| `campaign_name` | 캠페인명 | - |
| `purchases` | 전환수 | - |

**"DataKeeper has no cost"는 잘못된 판단** — `spend` 필드를 cost로 사용할 것.

---

## ROAS Decision Framework

| 7d ROAS | Action | Bid | Budget |
|---------|--------|-----|--------|
| < 1.0 | pause | - | - |
| 1.0~1.5 | reduce_bid | -30% | - |
| 1.5~2.0 | reduce_bid | -15% | - |
| 2.0~3.0 | monitor | - | - |
| 3.0~5.0 | increase_budget | - | +20% |
| > 5.0 | increase_budget | +10% | +30% |

Budget caps (Naeiae): $120/day total, $50/campaign max, $3.00 bid max

---

## 실행 이력 (Naeiae)

| 날짜 | 변경 내용 | 결과 |
|------|----------|------|
| 2026-03-08 Batch 1 | 네거티브 4개 + 하베스팅 5개 | 성공 9/9. 낭비 $100/14d 차단 |
| 2026-03-08 Batch 2 | 네거티브 6개 + 하베스팅 3개 + B0BMJCWYB6 입찰 -20% | 성공 16/16. 30d 분석 기반. ASIN 타겟 $0.80→$0.64 |

---

## 참고

- `references/amazon-execution-rules.md` — 입찰/키워드 규칙 상세
- `references/amazon-query-patterns.md` — 자연어 질의 패턴
- WJ Test1: `workflows/amazon_ppc_executor.md`
