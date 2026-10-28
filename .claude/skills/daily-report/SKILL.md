---
name: daily-report
description: 일일 업무 보고 PDF 생성 에이전트. CRM 개발 진척 + 메타 광고 (JP) + 기타 작업을 정리한 한국어 PDF를 만든다. 트리거 — "일일 보고", "데일리 리포트", "오늘 리포트", "daily report", "오늘 한 거 정리해", "오늘 보고서 만들어".
type: skill
---

# Daily Report 스킬

매일 세은이 외부 보고용으로 쓰는 일일 리포트를 자동 생성한다.

## ⚠️ 산출물 = 노션 (PDF 절대 X) — 2026-05-15 강한 교정 재발 반영
- 노션 페이지: **Seeun Daily Report** `35a86c6d-c046-800c-b3a8-fd2baa8cbdf4`
- 형식: 페이지 안에 **toggleable heading_2** 한 개 append (`{"type":"heading_2","heading_2":{"is_toggleable":true,...}}`)
- 토글 title: `YYYY-MM-DD (요일)` (예: `2026-05-15 (금)`)
- 위치: 페이지 children **끝에 append** (오름차순 = 최신이 아래). TEMPLATE 토글은 항상 최상단.
- PDF/child_page 만들지 않는다. `tools/build_daily_report_pdf.py` 는 더 이상 사용 X.

세부 룰: `memory/feedback_daily_report_notion_toggle.md` (이 SKILL 호출 시 먼저 Read).

---

## 호출되면 즉시 할 것

1. **오늘 날짜 확인** + git log + 최근 세션 메모리 + 트랜스크립트 스캔으로 오늘 한 일 파악
2. 부족한 정보(특히 기타 작업·인플루언서 시딩 등)는 세은에게 묻기 — 단, 직접 파악할 수 있는 건 절대 묻지 말 것 (CLAUDE.md 절대 룰)
3. 노션 페이지 `35a86c6d-c046-800c-b3a8-fd2baa8cbdf4` 에 `PATCH /v1/blocks/{page_id}/children` 로 새 토글 append

---

## 섹션 구조 (v2 — 2026-05-22~, 마스터 노션 「📋 TEMPLATE v2」 토글 기준)

v1 → v2 핵심 변경 (Jiah PPC 보고 형식 차용):
- **0. Headline 신설** — 한 단락에 「오늘 끝낸 것 + 큰 결과 + blocker 위치 굵게 (예: §4 참고)」 압축
- **메타에 ◆/■ 위계 + ◆ Active experiments 표** 추가 (운영 중 가설·룰을 표로 트래킹 — CRM·기타엔 안 박음)
- **4) 의문 사항 / 결정 요청** — 「# / 항목 / 사유·컨텍스트 / 회신란」 4컬럼 표. 가장 우측 회신란은 비워둠 (원기·calvin·세은이 표 셀에 직접 채우는 방식). 표 아래 「**Default if no response: …**」 한 줄 명시 (침묵 시 진행 방침)
- **CRM 항목은 「배경 → 작업 → 결과 → 잔여」 4-단 nested bullet 고정**

owner 태깅(섹션 헤더 끝 괄호 결정자 명시)은 **안 함** — 2026-05-22 세은 지시.

### 표현 의무 (2026-05-22 추가, v2 작성 시 강제)

모든 항목은 **숫자 + 타임라인 + 좁힘 기준** 3박자로. 추상·애매 표현 자동 위반.

| 위반 (X) | 준수 (O) |
|---|---|
| 「곧 마무리」 | 「2026-05-24 EOD」 / 「내일 AM」 |
| 「범위가 크다」 | 「현재 대상 N=120건 → A 조건(spend ≥₩30K) + B 조건(D+14+)으로 N=18건까지 좁힘. 기준 = 학습 완료 풀 + 절대 임계 KPI」 |
| 「많이 줄었다」 | 「-37% (₩820K → ₩516K)」 |
| 「개선됨」 | 「CTR 4.2% → 6.8% (+2.6pt)」 |
| 「당분간 보류」 | 「2026-06-02 (Day-14) 재평가까지 보류」 |

- **모든 작업 항목에 「마무리 예정일」 한 줄 의무** — 「잔여 — 2026-05-25 AM」 형식. 「잔여 — TBD」 / 날짜 없는 「잔여」 = 위반.
- **「범위가 광범위/크다」 표현 시 4축 동반 의무**: (a) 어떤 점에서 광범위 / (b) 어떻게 좁힐 / (c) 얼마나 (숫자) / (d) 좁힘 기준 (룰·임계). 4축 중 하나라도 빠지면 X.
- **수치 1개 이상 인용 안 된 결론·관찰 항목** 금지 (5/13 기존 룰 재강조).

자세한 블록 구조는 노션 마스터 페이지 「📋 TEMPLATE v2 (복제용)」 토글 참조. v1 → v2 마이그레이션 PATCH 스크립트: [tools/notion_template_v2_append.py](tools/notion_template_v2_append.py)

---

## 섹션 구조 (v1 — 폐기, 참고용)

```
1) CRM 개발 진척 (주요/부수 분리 X + 줄글 X)
   - 형식: 1단 블랙닷 = 프로젝트 명 / 2단 블랙닷 (들여쓰기) = 라벨 — 한 줄
     · 라벨 = 배경 / 오늘 확인 / 작업 / 결과 / 검증 / 잔여 fix 등 (작업 성격에 따라 자유)
     · 한 줄 한 줄 간결. 한 줄 = 한 사실.
     · 비기술자 이해 우선 — fallback/dry-run/lookup 같은 작업자 용어 풀어쓰기
   - 무엇을 적는가:
     · **그날 완료된 큰 프로젝트** = [완료] 라벨로 강조 (며칠 짜리 시스템 작업이 production 동작 확인된 시점)
     · 진행 중 작업
     · 블로커 / 대기 항목 (외부 의존)
     · 원기님께 부탁한 것 (별도 1단 블랙닷)

2) 메타 광고 (JP)
   - 전체 성과 — **두 윈도우 항상 같이**:
     · 일 단위: 어제 24h (D-1) vs 그저께 24h (D-2) — 오늘은 진행 중이라 빼야 형평성 맞음
     · 주 단위: D-1 기준 역산 rolling 7일 (D-1~D-7) vs 그 전 7일 (D-8~D-14)
       — 달력 주(월~일) 끊긴 윈도우 X. 항상 어제부터 역산.
     각각 표 (지표 / 값 / 변동). 헤더에 정확한 날짜 범위 명시.
   - 캠페인별 — 블랙닷
   - 이번 주 신규 광고 — 표 (등록일/유형/광고/캠페인·Adset/URL)
   - BEST 광고 (CTR + CPC 종합) — 표 (순위/광고/CTR/CPC/URL)
   - WORST 광고 (CTR + CPC 종합) — 표 (광고/CTR/CPC/지출/URL)
   - 공부 중 — 본문
   ※ 권장 액션 / 한 줄 요약 X — 절대 넣지 말 것

3) 기타 작업
   - JP 박람회 카탈로그 / 틱톡 / 인플루언서 리치아웃·시딩·스케줄 조정 등
   - 인플루언서는 시딩 발송 → 신규 스케줄 조정 순서
   - 캘린더 이미지 받으면 마지막에 헤더 없이 이미지만 첨부
```

---

## 데이터 수집 절차

### CRM 개발 진척
1. `git log --since="today 00:00" --oneline` (SE 리포)
2. orbitools-code-edit MCP 통한 PR: `mcp__orbitools-code-edit__list_recent_prs`
3. 오늘 트랜스크립트(`C:\Users\orbit\.claude\projects\C--Users-orbit-Desktop-SE\*.jsonl`)에서 CRM/WONGI/JP CRM/intelligence_next/django_phases 키워드 검색 — 제갈량 호출은 트랜스크립트에서만 잡힘
4. 원기님 부탁 항목: 트랜스크립트에서 "원기" / "wongi" / "원기님께 추가 통보" / "운영자 통보" 검색 + 이전 세션 메모리에서 미해결 부탁 누적

### 메타 광고
1. `PYTHONIOENCODING=utf-8 python tools/meta_jp_quick_analyze.py` — 14일/7일 누적 + 캠페인·광고 정렬
2. **5/X 일일 ad-level 데이터** 별도 fetch (Meta API `time_range`):
   ```python
   params = {'fields': 'ad_id,ad_name,campaign_name,spend,impressions,clicks,ctr,cpc,frequency',
             'level': 'ad',
             'time_range': json.dumps({'since': 'YYYY-MM-DD', 'until': 'YYYY-MM-DD'})}
   ```
3. **신규 광고**: `created_time` 필드로 최근 7일 등록 광고 + creative.instagram_permalink_url 함께
   - **표에 성과 컬럼 필수 (2026-07-09 세은 지시)**: 등록일 / 광고 (인플루언서) / 캠페인 / **지출(누적) / CTR / CPC / CPLPV** / URL — 각 광고 등록일~보고 당일 누적 (ad-level insights, 윈도우 시작=등록 컷오프면 단일 쿼리로 충분)
4. **BEST/WORST 산정 (asset type별 풀 내 종합 ranking, 5/21 재설계 v3)**:
   - **학습단계 제외 (시간 기준)**: 광고 생성일 기준 **D+14+** 만 진입. spend 임계 폐기 (5/21 합의 — budget 작아서 잘 못 굴러가는 광고도 ₩30K 못 넘을 수 있음. 시간이 더 정확).
   - **추가 필터**: ACTIVE 상태 + 윈도우 내 spend ≥ ₩1K (데이터 없는 광고 제외용 최소 임계)
   - **asset type별 풀 분리**: 이미지 / 영상·WL 따로 산정 (CTR KPI 자체가 다름 — 이미지 4% / 영상·WL 8%)
   - **종합 ranking = 4지표 풀 내 rank 평균**: CTR(높을수록 좋음) + CPC(낮을수록 좋음) + clicks(많을수록 좋음) + LPV(많을수록 좋음). 각 지표 풀 내 rank(1=best ~ N=worst) 매긴 후 평균. 작을수록 좋음.
   - **BEST**: 풀 내 종합 ranking 상위 1~2개
   - **WORST**: 풀 내 종합 ranking **꼴찌 1~2개**. 단순 풀 내 상대 비교. 절대 임계·percentile 게이트 X.
   - **자동 제외 룰**: graduation 후보 (PROVEN 졸업 추천된 광고 — triple share ≥50%)는 WORST 후보에서 무조건 제외. PROVEN 추천과 WORST가 같은 광고면 정면 충돌. 풀 1등은 ranking 자체로 BEST 자리라 별도 제외 명시 불요.
   - **"고지출 비효율" 슬롯 영구 폐기**: ad 단위 예산 없음. ad set 내 고지출은 알고리즘이 그 광고를 1등으로 판단해 노출 몰빵한 결과 = 잘 돌고 있다는 증거. 고지출 자체를 WORST 진입 신호로 삼는 건 광고 메커니즘 무시 (memory/feedback_meta_no_ad_level_budget.md). 부활 X.
   - **풀 1개뿐인 asset type**: 풀 내 ranking 불가. 그 광고가 절대 임계 KPI 미달(이미지 CTR<2% / 영상 CTR<4%)이면 단독 WORST로 표시. 통과하면 해당 asset type WORST 행 없음.
5. URL: 인스타 permalink (creative.instagram_permalink_url) — Facebook 페이지 링크 X

### 기타 작업 (세은이 알려줌)
- JP 박람회 카탈로그 수정 등 단발 작업
- 틱톡 차단 해결 작업 (게시물·좋아요·리포스트)
- 인플루언서:
  - **리치아웃**: "신규 N명 리치아웃 → M명 답신" 형식
  - **시딩 발송**: `@핸들 (성씨様) — sku` 블랙닷
  - **신규 스케줄 조정**: `@핸들 (성씨様) — sku` 블랙닷
- 인플루언서 메모리(`memory/influencers/influencer_*.md`)에서 핸들 → 호칭·SKU 자동 매핑

---

## 보고 기준 룰 (2026-05-13 신규)

### Leveling (정렬·등급 표시 의무)

| 영역 | 룰 |
|---|---|
| **인플루언서 나열** | 좌측에 **등급 배지 (A/S/B/C)** + 1차 정렬 = **CPLPV peer% 오름차순**. CTR/Spent는 sanity 보조 컬럼 (정렬 키 X). 등급 미부여 신생(D+7 미만)은 "노출 누적 중" 라벨로 별도 묶음. |
| **작업 leveling** | 본문에 **진행 중 / 완료 / 막힘** 3단 헤더 분리. 각 항목 형식: `[주제 — 진척 NN%] 자연어 한 줄 + (timeline)`. 진척은 추측 X — 명시적으로 알 때만. |

### 비교 윈도우 (Best/Worst·전체 성과)

| 윈도우 | 용도 | 갱신 주기 |
|---|---|---|
| 7일 누적 평균 | **메인** 비교 지표 | 매주 월요일 갱신 (peer 값 그 주 고정) |
| 30일 누적 평균 | 보조 — 안정성 검증 | 매월 1일 갱신 |
| 일일 (D-1 vs D-2) | **참고만** — "변동성 큼" 라벨 강제. 본문 하단 작은 표. | 매일 |

→ **일일 단위 peer 산출 금지.** peer 값 = 윈도우 갱신 시점에만 변동.

### Best/Worst·기준 라벨 의무

표 상단에 **"기준: [지표]"** 명시 강제.
- 메인 기준 = **CPLPV peer 대비 (Testing/Proven 분기)**
- 다른 기준 사용 시(예: CTR + CPC 종합) 그 기준 라벨도 함께 표시
- 라벨 없는 best/worst 표 = 룰 위반

### 지출 두 용도 분리

| 용도 | 사용 수치 |
|---|---|
| 등급 분기 트리거 | **절대 누적 spend ≥₩30K / ₩50K / ₩100K** (3단 손절 임계) — 5/11 정립 |
| 추세 보고 | **7일 평균 + 30일 평균** 별도 표시. 일일 spend 단독 X. |

### Peer 정의 (5/11 + 5/13 보강)

| 차원 | 정의 |
|---|---|
| 단계 | Testing / Proven 분리 |
| 풀 | 같은 인플루언서 풀 |
| **asset type** (5/13 신규) | 이미지 / 영상 / WL 분리. CTR KPI 자체가 다름(이미지 4% / 영상·WL 8%). |
| 시간 | Testing peer = D+1~D+7 누적 / Proven peer = 7일 누적 (주 1회 갱신) |
| 일일 | **금지** |

### RSL 보정 (calvin 답 대기)

- 5/8 오후 RSL 도입 시점 전후 비교 시 **"RSL 이전 — 직접 비교 X" 라벨** 강제
- 잠정 배수 적용 X (calvin 답 받기 전까지 anchoring 위험)
- calvin 답 받으면 배수 곱해서 보정 후 비교 활성화

### 결론 섹션 (3분할 + 4축)

리포트 끝부분 결론 = 3분할 헤더로 분리:

1. **의사결정** — 오늘 확정한 액션
2. **관찰 사실** — 데이터에서 본 패턴 (수치 인용 의무)
3. **미해결 안건** — calvin/원기/세은 결정 대기

각 항목 본문은 **Who · What · When · Why** 4축으로. "느낌상 / 추세 같다" 같은 정성 표현 금지 — 수치 1개 이상 인용 의무.

---

## 표기 규칙 (위반 시 세은 강한 교정 받음)

### SKU 표기 — 3종으로만 (`reference_sku_simplified_naming.md`)
| 원래 제품 | 단순 표기 |
|---|---|
| ステンレスストローマグ (모든 색상·용량) | **stainless** |
| PPSU トレーニングマグ / ストローマグ | **ppsu** |
| ワンタッチ式ストローマグ / 원터치 | **fliptop** |

색상·용량은 절대 안 적음.

### 톤
- **이모지 절대 금지** (특히 🔴🟢📊📈 등 — 세은 명시 교정)
- "권장 액션" / "한 줄 요약" 문구 금지 (메타 광고 섹션)
- 추측·"가능성" 라벨 표현 금지 (검증 안 된 건 빼라)
- 친구톤 X — 비즈니스 톤, 한국어, 간결

### 가독성
- H1 spaceBefore=22, spaceAfter=14
- H2 spaceBefore=16, spaceAfter=8
- BULLET spaceAfter=7
- 본문 leading=17
- 표 셀 패딩 8pt
- 링크 색상 `#1a73e8`
- BEST 표 헤더 배경 `#e8f5e9` / WORST `#ffebee` / 신규 `#fff8e1`

### 캘린더 이미지
- 세은이 캘린더 이미지 주면 PDF 마지막에 **헤더 없이 이미지만** 첨부
- 체크 표시 / 박스 강조는 세은이 명시 요청한 경우에만
- 추출: 트랜스크립트의 base64 image source → PNG 저장 (`.tmp/calendar_input.png`)

---

## 빌드 절차

```bash
# 1. 템플릿 복사
cp tools/build_daily_report_pdf.py .tmp/build_daily_report_pdf.py

# 2. 데이터 채워넣기 (Edit 도구로 섹션별 수정)
#    - 1) CRM: 주요 작업 / 부수 작업 / 원기님 부탁
#    - 2) 메타: 전체 성과 표 / 캠페인 / 신규 광고 / BEST / WORST / 공부
#    - 3) 기타: 박람회 / 틱톡 / 리치아웃 / 시딩 / 스케줄 / 캘린더

# 3. 빌드
PYTHONIOENCODING=utf-8 python .tmp/build_daily_report_pdf.py

# 4. 띄우기
start "" "C:\Users\orbit\Desktop\SE\.tmp\daily_report_YYYYMMDD.pdf"
```

---

## 세은 자주 하는 교정 (사전 차단)

| 교정 | 대응 |
|---|---|
| "이상한 거 적지 마" | CRM 개발 = JP CRM/US CRM/pipeline-crm/WONGI/orbitools 코드 작업만. 자동 agent 코드 push는 X |
| "쓸데없는 이모지 치워" | 이모지 0개. 절대 |
| "내용 간 간격이 너무 좁아" | spaceBefore/After 위 명시 값 |
| "어렵게 말하지 말고" | 기술 용어 풀어쓰기, 초등학생도 이해되게 |
| "원터치는 fliptop이라니까" | 원터치/ワンタッチ → fliptop. ppsu 아님 |
| "체크 표시는 지우고 이미지만" | 캘린더 강조는 명시 요청 있을 때만 |
| "권장 액션·한 줄 요약 치워" | 메타 광고 섹션에 절대 안 넣음 |
| 신규 광고 표에 "효과도 같이" (7/9) | 성과 4컬럼(지출누적/CTR/CPC/CPLPV) 기본 포함 |
| 세은이 토글 수동 편집한 후 수정 지시 (7/9) | 지시받은 블록만 DELETE + after 삽입. 재작성 X. 메타몽 앱·게이트 작업 블록은 §2 메타 광고 하위 ◆로 배치 (세은 7/9 편집 관찰) |
| "장난하나 표로 만들어" (7/10) | 다항목×다속성 구조 요약(문서 구성·PART별 내용 등)은 수치 아니어도 bullet 아닌 표로 삽입 |
| 플레이북·핸드오버 산출물 위치 (7/10 편집 관찰) | 개발자 핸드오버용 문서 작업은 §3 기타가 아니라 §1 CRM 개발 진척 하위 ◆로 배치 (세은이 직접 이동) |
| 분석·해석 블록 대폭 삭제 (7/28 편집 관찰) | §2는 성과 표 + 캠페인별 bullet까지만. 잔존 시청률 해석 같은 분석 ◆·신규 광고 0건 줄·산출물의 배경/가정값 상세 bullets 전부 세은이 삭제. 산출물 블록은 확정 기준 + 핵심 결과 1~2줄로 얇게 |
| 동시 진행 세션 확정값 (7/28) | 다른 세션에서 논의 중인 기준값(Good CPLPV 등)은 append 직전 그 세션 마지막 발화까지 재확인 — 110 썼다가 세은이 115로 직접 교정 |

---

## 산출물 위치

- PDF: `C:\Users\orbit\Desktop\SE\.tmp\daily_report_YYYYMMDD.pdf`
- 빌드 스크립트(매일 새로): `C:\Users\orbit\Desktop\SE\.tmp\build_daily_report_pdf.py`
- 영구 템플릿: `C:\Users\orbit\Desktop\SE\tools\build_daily_report_pdf.py`
- 캘린더 입력(있을 시): `C:\Users\orbit\Desktop\SE\.tmp\calendar_input.png`