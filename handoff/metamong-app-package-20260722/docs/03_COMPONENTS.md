# 03. 컴포넌트 레이어 상세

> 원본 소스: `meta-app/components/**`. props·클래스명·키 이름·임계값은 코드에서 그대로 옮겼다.

## 1. AppShell.tsx (`"use client"`)

- Props: `{ children: React.ReactNode }`. `/login` 에서는 셸 없이 children 만.
- 네비 7탭:
  `/`(홈, Home) · `/products`(전환, Repeat) · `/ads`(광고, BarChart3) · `/budget`(예산, Wallet)
  · `/alerts`(알림, Bell) · `/influencers`(콘텐츠, Users) · `/codes`(코드, KeyRound)
- 활성 판정: `/` 는 정확 일치, 나머지 `pathname.startsWith(href)`
- 헤더: sticky top-0 z-30, `bg-background/70 backdrop-blur-md`, 좌측 Monkey(happy, 36) + "메타몽 / Grosmimi JP",
  중앙 데스크톱 네비(md 이상). 활성 링크 `bg-primary text-primary-foreground`.
- 메인: `max-w-6xl`, `pb-24 md:pb-10` (모바일 하단 네비 자리)
- 모바일 하단 네비: `fixed bottom-0 z-30 md:hidden`, flex-1 균등, 활성 표시 = 상단 `h-0.5 bg-primary` 바

## 2. AnnouncementStack.tsx — 팝업 체인 오케스트레이터 (`"use client"`)

- 상태: `stage: "none"|"settlement"|"newads"|"ops"|"operation"|"supersale"|"daily"`
- 체인 순서: **Settlement(6월 결산) → NewAds(신규 광고) → Ops(오늘 운영) → Operation(운영체계)
  → Supersale(슈퍼세일) → daily(DailyIssuesPopup)**
- 각 단계 표시 조건 = `Date.now() < SHOW_UNTIL_UTC` && `!sessionStorage.getItem(DISMISS_KEY)`.
  둘 중 하나라도 실패 → 다음 단계로 skip. 닫기(onClose) → sessionStorage 마킹 + 다음 단계.
- 레이아웃(app/layout.tsx) 에서 마운트 — 전 페이지 공통.

### 공지 팝업 6종 (전부 만료일 하드코딩 — 1회성 콘텐츠, §01 문서 기술부채 항목)

| 컴포넌트 | dismiss 키 (sessionStorage) | 만료 (UTC) | 내용 요지 |
|---|---|---|---|
| JuneSettlementAnnouncement | `june_settlement_20260701_dismissed` | 2026-07-02 10:30 | 6월 총결산 7카드 (총량 +75.7%/Total ROAS 1.14x/세일 2.74x vs 0.66x/BEST·WORST/7월 액션) |
| NewAdsAnnouncement | `new_ads_20260701_dismissed` | 2026-07-02 10:30 | 6/17 이후 신규 광고 12건 표 — CPLPV 색상: ≤₩110 초록 / ≤₩140 노랑 / >₩140 빨강 |
| TodayOpsAnnouncement | `today_ops_20260630_dismissed` | 만료됨 (2026-06-29 15:00) | Stainless 일예산 ₩160K 세팅·졸업 이동 등 당일 운영 3카드 |
| OperationModelAnnouncement | `operation_model_20260619_dismissed` | 2026-06-25 15:00 | 운영 체계: 3캠페인 체제, 명명 규칙 `YYMMDD_Grosmimi_RKT_WL-G/P_핸들_ASIN_CT코드`, Testing ₩8,000/개, 역할분담(세은=on/off·예산, 메타몽=세팅), 증액 계획 |
| SupersaleAnnouncement | `supersale_2026jun_popup_dismissed` | 2026-06-12 07:00 | 세일 성과 탭 2개 (들인 돈 대비 ROAS 2.64x / 평시 대비 매출 +443%) |
| PostSaleEfficiencyAnnouncement | (동일 패턴) | — | 세일 후 효율 관리 공지 |

공통 UI: `fixed inset-0 z-50` + `bg-black/40 backdrop-blur-sm`, max-w-md 카드, Monkey(rich/teacher, 48),
본문 `max-h-[60vh] overflow-y-auto`, 카드 태그 톤 — decision: `bg-emerald-100 text-emerald-700` /
info: `bg-secondary text-muted-foreground` / done: (완료 톤), Chip tone — bad `bg-rose-100 text-rose-700`,
good `bg-emerald-100 text-emerald-700`, flat `bg-secondary`.

## 3. DailyIssuesPopup.tsx (`"use client"`)

- 데이터: `GET /api/daily-issues` (스키마는 02 문서 §11)
- dismiss 키: `daily_issues_dismissed_${date}` (sessionStorage — 날짜별)
- 항목 0건이면 렌더 안 함.
- 신규 등록 섹션: Sparkles 아이콘 + 광고명/adset + [영상 바로가기] (permalink 있을 때)
- 졸업 섹션: GraduationCap + from_adset→adset, 누적·7d spend 배지,
  **점유율 게이지 3종**(Spend/Clicks/LPV — 50% 기준선 세로줄, 통과 시 초록 체크),
  CTR 게이트 (ctr_7d ≥ kpi_ctr 초록), 3축 모두 통과 시 "✓ Triple share + 성과 게이트 충족 → 졸업"

## 4. TagEditor.tsx / TagCell.tsx (`"use client"`)

- **TagCell**: 콘텐츠 풀 목록 셀. 요약 칩(수동 태그 = `--good-bg` 칩 / 자동 = muted "자동 S##_F## ..." /
  기각 = "— 미분류 (자동 기각)") 표시, 클릭 → 모달 (Escape/배경 클릭 닫기).
  모달 = @handle 헤더 + [영상 ↗] + TagEditor + 자동 태그 근거(kmPrimaryDesc/kmSub/hookPrimaryName/evidence/confidence)
  + 팁 문구("기각·수동 교정은 다음 자동 태깅부터 학습").
- **TagEditor**: KM(S##_F## — kmGroups 를 subject 별 optgroup) / 훅(HV/HC — group 별 optgroup) 드롭다운
  다중 선택 + 칩 × 삭제. 자동 태그 × = 기각(`value:"-"`), ↺ = 복원.
  저장: `POST /api/tags {shortcode, field, value: list.join(",") | "-" | ""}` — 옵티미스틱 업데이트,
  실패 시 롤백 + 오류 표시. saving 상태로 select disabled.

## 5. ScrollableTable.tsx / DragScroll.tsx (`"use client"`)

- **ScrollableTable**: 본문 div `.no-native-sb overflow-x-auto` (네이티브 바 숨김; globals.css 에서
  shadcn Table 내부 컨테이너 `[data-slot=table-container]` overflow:visible 강제) +
  하단 `sticky bottom-0 z-30 h-[18px] overflow-x-scroll` `.hbar` 바 (더미 div 로 본문 scrollWidth 미러).
  - 동기화: 양방향 onScroll, `syncing` ref 플래그 + rAF 로 루프 방지
  - 오버플로 판정: `scrollWidth - clientWidth > 2` (rAF + 400ms 타이머 + ResizeObserver + window resize)
  - 마우스 드래그 스크롤 내장 (5px 임계, 드래그 후 클릭 무효화)
- **DragScroll**: 범용 드래그 스크롤 (가로+세로). `a, button` 클릭은 통과, 5px 초과 이동 시 dragged,
  click capture 단계에서 preventDefault. 커서 grab/grabbing.

## 6. Monkey.tsx / GradeChip.tsx / StatusBadge.tsx / KpiCard.tsx / CopyButton.tsx / EnvWarning.tsx

- **Monkey**: `mood` 10종 = happy·dizzy·angry·shy·tongue·cry·ecstatic·joyful·rich·teacher →
  `/public/monkeys/{mood}.svg` (next/image, size≥60 이면 priority)
- **GradeChip / GradeBadge** (등급 S/A/B/C/NA):
  - MOOD 매핑: S=ecstatic, A=joyful, B=dizzy, C=cry, NA=dizzy
  - 라벨 스타일: S=`bg-[var(--good-bg)] text-[var(--good-fg)]` / A=accent / B=secondary /
    C=`bg-[var(--bad-bg)] text-[var(--bad-fg)]` / NA=muted
  - `GRADE_ROW_BG`(표 행 배경)·`GRADE_CARD_BG`(카드 배경) 상수 export — 같은 CSS 변수 계열
  - bump 표시: ▲(+1) / ▼(−1). GradeBadge 는 NA 면 null
- **StatusBadge**: `StatusPill` (tone: good/warn/bad/neutral — good/bad 는 CSS 변수, warn=accent),
  `SpendBar` (bg-muted h-1.5 + bg-primary/80 채움, pct=min(100, value/max*100)),
  `RankBadge` (h-6 w-6 원형, rank≤3 강조 — good=primary / bad=`var(--bad)`)
- **KpiCard**: `{label, value, deltaPct?, hint?, invertColor?}` — |Δ|<0.1% 중립, invertColor 로 방향 반전,
  ▲/▼/▬ + 퍼센트, 값 `text-2xl font-bold tabular-nums`
- **CopyButton**: clipboard.writeText + 1.5s "복사됨" (Check 아이콘)
- **EnvWarning**: Monkey(dizzy, 84) + "데이터를 불러오지 못했어요" + 에러 문자열 + env 체크 안내.
  각 페이지의 데이터 fetch 실패 fallback.

## 7. 차트 (Recharts, `"use client"`)

- **AdDailyCharts** `{data: DailyPoint[]}` — DailyPoint = date/spend/lpv/clicks/ctr/cplpv/frequency/
  impressions/cumLpv/cumCtr/cumCplpv.
  일별: Spend(Area)·LPV(Area)·CTR(Line)·CPLPV(Line)·Freq(Line)·노출(Area) /
  누적: LPV·CTR·CPLPV. 색: `var(--primary)` + `var(--chart-2, #8a6f4d)`, fill opacity 0.18,
  X축 "MM/dd" minTickGap 28, 높이 150~170px.
- **ContentCharts** `{organic: {date,daily,cum}[], paid?: {date,spend,spendCum,lpv,lpvCum,ctr,ctrCum,cplpv,cplpvCum}[] | null}`
  — Organic view 일별/누적 항상, Paid 4종(Spend/LPV/CPLPV/CTR) 일별/누적은 WL 콘텐츠만.

## 8. ui/* (shadcn 계열 — 특기사항만)

- base-ui(@base-ui/react) 프리미티브 + CVA. 표준 shadcn 과 대체로 동일.
- **table.tsx**: 래퍼 div `data-slot="table-container"` + `overflow-x-auto` — ScrollableTable 이
  이 내부 래퍼를 `.no-native-sb` CSS 로 무력화하는 구조 (가로 스크롤 이중화 방지의 핵심)
- **button.tsx**: size 8종 (default h-8 / xs h-6 / sm h-7 / lg h-9 / icon 4종), `active:translate-y-px`
- **card.tsx**: `--card-spacing` CSS 변수 (기본 4, `data-size=sm` 3), ring-1 테두리, container query 헤더
- **tabs.tsx**: variant default(인셋 muted 배경) / line(언더라인 `after:` 가상요소)
- badge/separator/skeleton: 표준

## 9. 색상·임계값 요약 (컴포넌트 레벨)

| 대상 | 규칙 |
|---|---|
| CPLPV 칩 (NewAds 팝업) | ≤₩110 초록 / ≤₩140 노랑 / >₩140 빨강 |
| 졸업 점유율 게이지 | ≥50% 통과 (기준선 + 체크) |
| KpiCard Δ | \|Δ\| < 0.1% 중립 |
| 드래그 판정 | 5px / 오버플로 판정 2px |
| tone 변수 | good=`--good(-bg/-fg)` 파스텔 민트 / bad=`--bad(-bg/-fg)` 파스텔 핑크 (globals.css OKLCH) |
