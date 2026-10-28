---
name: reference-recollab-ranking-dashboard
description: 메타몽 app 재콜라보 랭킹 대시보드 — 판정 모델·크리에이터 단위 광고 귀속·코드 앵커
metadata:
  type: reference
---

메타몽 app 인플루언서 탭 3번째 서브탭 `/influencer/recollab` (2026-09-16 신규). 과거 콜라보 크리에이터를 "다시 광고 자산으로 쓸 가치"로 랭킹. prod meta-app-one.vercel.app.

**코드 앵커:** `meta-app/lib/influencer-recollab.ts` (buildRecollabRanking) · `app/influencer/recollab/{page,RecollabClient}.tsx` · `app/influencer/layout.tsx` 서브탭 · 디버그 `app/api/debug-recollab/route.ts`(?h=핸들 상세). 배포 `vercel --prod`(git push 아님), cwd=meta-app.

**판정 모델:** 순위=광고 3지표 복합 CPLPV 50%(spend÷LPV) + CTR 30% + VTR 20%(**오가닉 D+3÷팔로워**). percentile→티어 S≥80(+CPLPV효율 상위30% 게이트)/A≥60/B≥25/C. 최소노출 게이트=WL노출≥200&지출>0(미달=표본부족). 비용=순위 미반영·배지만(S/A+Gifted🟢최우선·+Paid🟡검증). 광고의존⚠️=광고상위인데 오가닉ER 하위25%.

**VTR 소스 = content_posts.views_30d ÷ 팔로워 (2026-09-16 수정).** 원래 organicVtr=organicViewD3(content_metrics_daily D+3)/팔로워인데, content_metrics_daily가 2026-02 이전 미수집이라 옛 콜라보 VTR 전멸(0/60). `influencer-aggregation.ts` organicVtr 에 `vtrView = organicViewD3 ?? post.views_30d` fallback 추가 → 48/60 복구. **VTR은 순위 percentile 엔 반영, 절대 커트라인엔 부적합**(views/팔로워라 소팔로워 바이럴이 264배까지 튐).

**등급 판정 = 3지표 복합 점수 (VTR 포함, AND 아님·보완 가능).** 각 지표 절대값→점수(0~100, 기존 61명 분포 percentile)→가중합 `복합=CPLPV점×0.5+CTR점×0.3+VTR점×0.2`→ S≥75·A≥60·B≥30·C<30. **재콜라보=A(복합≥60) 이상.** 신규 WL광고 1건도 이 방식으로 판정(점수변환표: CPLPV ¥45→95·¥85→75·¥120→52·¥150→30 / CTR 15%→95·11%→75·8%→46 / VTR 10→74·3→51·1→29). VTR은 팔로워편향(median B최고)이라 단독은 티어와 안 맞지만 20%가중+점수변환으로 복합에 포함(세은 지시 2026-09-16 — "VTR 왜 산정 안 하냐"). ⚠️CPLPV·CTR AND 커트라인표(≤¥120&≥8%)는 폐기(등급을 AND로 오표현해 혼란). 티어분포 61명: S11(18%)·A13(21%)·B22(36%)·C15(25%), S+A=24(39%). 제외기준(참고)=회당¥20k↑&성과pct<40.

**⚠️ 시점 = 상대 시점 정규화 (게재 후 D+14, 2026-09-16 세은 지시 전환).** CPLPV·CTR은 각 광고의 **게재일(min date_start) 기준 첫 14일 구간만** 집계 — 생애 누적은 집행 시기(계절·CPM·경쟁)가 다른 크리에이터를 섞어 비교하는 편향이 있어 폐기. `influencer-recollab.ts` §3에 adLaunch(min date_start)+REL_WINDOW_DAYS=14 윈도우 필터. VTR도 D+3라 3지표 모두 상대 시점. N 바꾸려면 REL_WINDOW_DAYS만 수정.

**⚠️ 광고→크리에이터 귀속 (재콜라보 전용·다른 페이지 영향 X):** 기존 콘텐츠풀 wl-attribution 은 "광고 게시물 shortcode↔시트 URL 일치" 의존이라 시트 URL 누락 시 광고 통째 누락(139건 중 83 미연결 실증). 재콜라보는 크리에이터 단위로 직접 귀속 — ① CT코드(CT-#####=content_posts.id)→username ② permalink→content_posts.username ③ 광고명 프레임워크 핸들(WL-[GP]_핸들_B0…) ④ 구형 닉네임=로스터 **유일 prefix**만(모호=스킵·오귀속 방지). usKey(언더스코어 앞뒤)로 로스터 정본 흡수. 결과 114/139 연결(잔여 25=인하우스/제네릭 광고·크리에이터 없음).

**deal type:** 시트 정본→없으면 광고명 WL-G/WL-P 토큰 추론→그래도 없으면 "미상"(제외 X·표기만). 시트 미등록 크리에이터는 "시트 미등록" 표기로 리스팅 유지([[mistakes-20260916-exclude-unknown-dealtype]]). collabCount=실제 게시 콜라보(shortcode 있는 행)수·기획/빈 시트행 제외·광고 있으면 최소 1.

**시트 소스 = 세은 원장 JP Influencer Tracker `13S1cST2ukuNN…` (2026-09-16 전환).** 이전 앱은 별개 `1wkue4G7FP…`를 봐서 세은이 채운 fee가 반영 안 됐음(이원화). `sheets.ts`: SHEET_ID→13S1cST·GID_MASTER→1589913586(Master DB)·GID_GROSMIMI→751080099(**WL Code & Payment** 탭)·fetchCollabs 컬럼 전면 재매핑(Deal25·Fee26·WLcode17·URL18·Adcode29 등). Vercel prod는 SHEET_ID env 삭제→코드 기본값 SSOT. 앱은 익명 CSV export라 시트 링크공개 필수.

**parseFee 버그 수정 (2026-09-16):** fee칸 텍스트 메모("7500*2번째 올리면 송금")를 구 로직이 숫자만 이어붙여 75002로 오파싱 → 첫 숫자 그룹만 취하도록 `/\d[\d,]*(?:\.\d+)?/` 수정. sheets.ts parseFee.

**교훈(도구):** gspread `append_rows(table_range="A1")`는 최상단 삽입 사고 유발 → 명시 범위 `ws.update("A{last+1}:…")` 써라. buildContentPool은 unstable_cache revalidate 300초(Vercel Data Cache 배포간 유지) → 배포 직후 검증은 캐시 만료 폴링 필요, 로컬은 .next 삭제.

미완/후속: 상위권 일부 콜라보행 미등록(yucchi_mum류 Master엔 있으나 WL C&P 행 없으면 fee 미상)→세은 WL C&P 보강·D+60 귀속 매출축·REL_WINDOW N값 튜닝 여지.

**정적 배포본(HTML+PDF) 보강 (2026-09-17 세은 요청).** 정본 `s\performance marketing\Social KPI\재콜라보_랭킹_비용정리.{html,pdf}`. 빌더 `.tmp/recollab_report/build_report3.py`(build_report2 + 업로드일/보낸SKU 2컬럼 + stale 하이라이팅). 조인 데이터 `.tmp/recollab_report/enrich.json`(핸들→prod·dates·src). **보낸 SKU** = WL Code & Payment 탭(gid 751080099) Product 컬럼(col6). **업로드일** = content_posts.post_date를 **시트 URL shortcode로 조인**(URL 없으면 해당 username의 grosmimi 브랜드 게시물). 복수 콜라보=개행 나열. **stale 하이라이팅** = 최신 업로드일이 (오늘−1달)보다 이전이면 주황+배지("1달+ 경과") — 최근 1달 신규 콜라보 없는 크리에이터(9/17 기준 45/61명). PDF는 Playwright chromium print(A4 landscape·print_background). 검증 룰: grosmimi 콜라보 게시물 특정 불가(riono류 시트 URL 無 + content_posts 전부 non_partnered)면 organic 게시물 날짜 대입 금지·공란(세은이 수동 제공한 날짜만 채움).

**DK content_posts 조인 도구 팁 (2026-09-17):** ① `data_keeper_client.py` `_read_pg`는 서버 **10000행 하드캡**(limit 크게 줘도)·offset 없음 → JP grosmimi 5,656건만 와서 옛 콜라보 shortcode 누락. ② 우회 = `/query/` 엔드포인트가 **문서에 없는 `username`/`username__iexact` 필터를 honor** → `requests.get(ORBITOOLS_BASE+'/query/', params={'table':'content_posts','username':h,'limit':50}, auth/token)` 로 핸들별 직접 조회(shortcode 매칭). ③ 이 엔드포인트 간헐 실패(순차 61콜 중 ~2 타임아웃) → 재시도 4~6회+sleep 필수. content_posts.url=`instagram.com/{p|reel}/{shortcode}/`·brand는 소문자 'grosmimi'+상당수 공란이라 브랜드 필터보다 username/shortcode 조인이 안전.

## 2026-09-30 업데이트 (메타몽 — 정성 컬럼 + D+30 창 + 대표영상 URL 검증)
세은 확정: **재협업 판단(파트너 선정)=광고 성과 정본, 콜라보별 평가=광고 성과+정성 병치.** 정성 단독 게이트는 반대(잘 만든 영상≠잘 파는 자산·집행 게이트를 파트너 게이트로 전용 오용). 시계열 개선 추적은 방향 맞으나 baseline 부재(심사 9월 신설·크리에이터당 1건뿐)라 축적 후 가능.
1. **정성 컬럼 추가** — `influencer-recollab.ts` `fetchReviews()`(review-store) 조인, usKey로 핸들 매칭. RecollabRow에 `qualLatestTotal/Verdict/ReviewedCount/Delta/IsAiOnly`. RecollabClient 티어 옆 `점수/9+집행/미집행`, 심사 2건↑ ▲▼ 추세, AI 미검수 배지, 심사 전=`—`. 순위·게이트엔 미반영(표시만). prod 검증 18/26명 표시·조인 5/5 정확.
2. **D+30 창 통일** — `REL_WINDOW_DAYS` 14→**30**. 근거=Meta 전환 지연 온전 포착 + VTR(views_30d=30일)과 창 통일(세 지표 동일 관측창). "재협업 간격 1달"은 측정창과 별개 개념(세은 근거 정정). ⚠️창 확대는 노출 단조증가라 population 절대 못 줄임 → 배포직후 -7은 `buildContentPool` 캐시 미가열 노이즈(재측정 74로 복귀).
3. **대표영상 URL 검증 (버그수정)** — 기존 `bestContentUrl = r?.url ?? cp?.url`이 콜라보 시트 URL을 **무검증 노출** → 시트 오입력분(komugiko_126: shortcode가 본인 게시물 아님·DB부재)이 타인 영상으로 링크(세은 "완전 무관 영상" 실증). 수정 `pickBestUrl()`: ①시트 URL shortcode가 `cpByShortcode`로 본인 검증되면 채택 ②실패 시 cpMeta 본인 게시물 폴백 ③둘 다 없으면 숨김. 전수감사 오매핑 0·미검증URL 3→0. 조인 로직 버그 아니라 "미검증 시트 URL 노출"이 원인.
배포 `vercel --prod`(meta-app). 미완: DK 안정 후 커버리지 재측정 · 시계열 추세는 재협업 2번째 심사부터 축적.
