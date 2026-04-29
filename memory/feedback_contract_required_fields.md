---
name: 계약서 생성 시 deliverables_detail + product_type 항상 필수
description: generate_influencer_contract.py 호출 시 반드시 두 필드 채워야 함. 누락하면 플랫폼·해시태그가 원본 템플릿 문구("いずれか" / "例：") 그대로 남음
type: feedback
---

계약서 생성할 때 **매번 인플루언서에 맞춰 아래 두 필드 반드시 지정**:

| 필드 | 역할 | 값 예시 |
|------|------|---------|
| `deliverables_detail` | 투고 플랫폼 지정 | `"Instagram Reels 1本"` (다른 플랫폼 지정 시 `"Instagram Reels 1本・YouTube Shorts 1本"` 등 합의 내용 명시) |
| `product_type` | 제품별 해시태그 맵 선택 | `"ppsu_straw"` / `"ppsu_onetouch"` / `"stainless"` 중 하나 |

**누락 시 증상:**
- 제1조 납품물: `"動画コンテンツ 1本（TikTok／Instagram Reels／YouTube Shorts いずれか）"` (원본 template 문구) 그대로 남음
- 제3조 해시태그: `"明示すべき広告表記（例：#grosmimi #グロミミ #ストローマグ）"` (例시 문구) 그대로 남음
- 세은이 "왜 안 바뀌어" 지적. 재생성 필요

**Why:** 2026-04-22 세은 지시 — "항상 넣도록 기억해 둬 줄 수 있을까? 항상 계약서 만들 때 이렇게 만들어지는 거 같아서". 베비몽 계약서(IC-202604-C67C66) 생성 시 두 필드 누락 → 원본 문구 그대로 PDF 생성 → 세은 발견.

**How to apply:**
- `generate_influencer_contract.py --manual '{...}'` 호출 시 반드시 이 두 필드 포함
- 제품 매핑:
  - PPSU ストローマグ → `product_type: "ppsu_straw"`
  - PPSU ワンタッチ式ストローマグ → `product_type: "ppsu_onetouch"`
  - ステンレスストローマグ → `product_type: "stainless"`
- 플랫폼은 인플루언서 합의 내용 기준. 대부분 `"Instagram Reels 1本"`
- 계약서 생성 직후 PDF 직접 열어 제1조·제3조 치환 확인 권장 (세은 재점검 전 스스로 체크)

**코드 보강 TODO:** `generate_influencer_contract.py` `required_common` 필드에 `deliverables_detail`, `product_type` 추가 — 누락 시 에러로 강제
