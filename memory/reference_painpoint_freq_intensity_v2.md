---
name: reference-painpoint-freq-intensity-v2
description: "JP 페인포인트 리서치 증보 v2 정본 (2026-10-12 — 대표 피드백 3건 반영: 빈도×강도 분리·1년+ 시계열/연령/계절성·BSR USP 컬럼). 강도 정의 채택 + 핵심 반전 팩트"
metadata:
  type: reference
---

# JP 페인포인트 리서치 증보 v2 (2026-10-12)

산출 = `Desktop\s\contents\jp_mom_painpoint_keymessage_research_20261007.html` 에 §3(빈도×강도)·§4(시계열·연령·계절성)·USP 컬럼 증설 (10/7 원본 백업 `.tmp/painpoint_v2/backup_jp_painpoint_20261007.html`).

## 강도 정의 (채택)
- **A 감정·이탈 사전 동반율** (発狂/ストレス/怖い/トラウマ + 捨てた/買い替え/二度と買わない 등 43어) = 주지표
- **C 미해결 반복** (洗っても/毎回/結局) = 보조. B(장문+감탄 호소형)는 소스 형식에 휩쓸려 참고만.
- 백테스트 2중: 10/7 코퍼스 1,800문단 + ママリ 160건 — 両정의가 カビ≫漏れ 갭 재현.
- 스코어러 `.tmp/painpoint_v2/intensity.py`

## 핵심 실측 (전부 2026-10-12)
- **カビ = 감정 36.4%·미해결 45.5% (전테마 1위)** / **漏れ = 최다빈도(45건)인데 감정 20%·미해결 12% — 갭 최대 확정** (대표 가설 적중). 실증 인용: 누수 글 「プチストレスです👉👈」(2020 ママリ).
- **カビ는 리뷰에서 소멸(0.4% vs 커뮤니티 최강) = 지연형 페인** — 리뷰/별점 데이터론 안 보이는 사각, 선점 공간.
- 리뷰의 漏れ 17.3% = 불만 3.7% vs 안심형 8.4% → **리뷰에서 漏れ는 구매 체크리스트지 불만 아님**. 자사 스텐 리뷰 25건 불만 0·48% "타사는 다 샜는데 이건 안 샘".
- **계절성: 구매 4월(입원)·연습 2~4월·保冷 5~7월·カビ 6월(장마)·커뮤니티 호소 5·7·8월. 겨울 가설 기각(12월 전소스 최저)**.
- 연령: 고민 무게중심 6-11m(빨대 도입기, 65건 중 37) — 컵연습도 6-11m부터(입학 직전 아님).
- **무게 반전: 서모스 FJL/FJT-350 공식 0.2kg(350ml) — 우리 스텐 300ml 216g보다 가벼움. "서모스 대비 경량" 소구 불성립.** 차별화 축 = 保温保冷 양용(서모스·콤비 스텐은 保冷전용) + 원터치 + 전부품 분해. 무게 소구는 PPSU(118g)의 몫.
- 에어밸브류 표기는 리첼(空気弁)·피죤(バルブ)·b.box(スリット)도 있음 — **"에어밸브=우리만" 금지**, "눌러서 압력 해제 조작" 시연으로 차별화.
- BSR top100: 漏れない 타이틀 17/100·소모품(패킹/스페어) 21/100 랭크인·스텐 중위가 ¥3,564(전체 2.1배). 우리 가격 = PPSU ¥3,190·원터치 ¥4,200·스텐 ¥5,800(top100 최고티어 위).

## 데이터 자산 (재사용 가능)
- ママリ 질문 160건 JSONL (2015~2026 날짜·연령 파싱): `.firecrawl/painpoint_v2/mamari_ts/mamari_questions.jsonl`
- 라쿠텐 리뷰 990건 JSONL (2018~2026, 서모스422/bbox450/리첼75/콤비18/자사25): `.firecrawl/painpoint_v2/rakuten_ts/rakuten_reviews.jsonl`
- Google Trends 5년: `.tmp/painpoint_v2/trends_seasonality.json` (pytrends 작동 확인, hl=ja-JP geo=JP)
- BSR top100 파싱: `.tmp/painpoint_v2/bsr_mag_top100.json` (원본 xlsx 7/3, Weight/Sales칸은 Xray 전용이라 공란)
- 무게 공식 스펙: 서모스 FJT/FJL-350 0.2kg·콤비 스텐 370ml 256g/mini 192g·리첼 2WAY 180g·b.box 105g·자사 스텐 188/216g·PPSU 108/118g

## 함정
- momvoice DK 테이블 = MCP 전용인데 "datakeeper read failed" 지속(10/12, Bearer 전환 직후) + 로컬 클라이언트는 momvoice 미지원 → 이번엔 자체 크롤로 대체함
- 라쿠텐 리뷰 신착순 정렬 URL 불가(JS 전용) — 표준 정렬로 긁고 리뷰별 날짜 개별 파싱이 정답
- mamari 자체 검색 URL 파라미터 안 먹힘 — `site:qa.mamari.jp` 구글 경유가 정답. 최근 1년 글은 연도 생략 표기

관련: [[reference-jp-painpoint-keymessage-research]] · [[feedback-report-html-minimal-decision-doc]] · [[reference-jp-bsr-data-availability]]
