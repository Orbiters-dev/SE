---
name: project_miro_jp_perf_route_map
description: Miro MCP 연결(2026-10-06) + GROSMIMI JP 퍼포먼스 마케팅 채널→랜딩 루트 맵 보드 제작. 세은 JP 업무만, 데이터 검증본(v3). 팀/대표 공유용 프로세스 맵.
metadata:
  type: project
---

# Miro JP 퍼포먼스 마케팅 루트 맵 (2026-10-06)

## Miro MCP
- `.mcp.json` 에 `miro` (http, https://mcp.miro.com/) 추가·OAuth 연결 완료. 세은 계정 명의로 편집.
- 그리기 규약: `canvas_get_canvas_composer_skill`(step=design→dsl) + `canvas_load_format_skill(diagramming, free_form)` 먼저 로드 필수. hand-assembled = 연결선 먼저(z-index 뒤)→노드→제목 순. `canvas_create_from_svg`로 생성, 이후 `canvas_update_from_svg`(data-miro-id 재사용·additive·삭제는 data-deleted).
- space_list=Access forbidden(개인/무료 팀)이지만 board_create·canvas 작동 OK.

## 보드
- **URL: https://miro.com/app/board/uXjVEeeyfUQ=/** ("GROSMIMI JP 퍼포먼스 마케팅 루트 맵 (세은 JP)")
- 목적: 팀/대표 공유용 **프로세스 맵** — 시작→랜딩 실제 루트, 같은 루트/갈라짐/수렴이 드러나게. (조직도 아님. PNG 시안 3장 거쳐 v3 확정 후 Miro 이관)

## 검증된 루트 (세은 JP만, US/현석님 제외)
- **인플루언서** 오가닉 → 감시견 D+3 미부착 → WL 자동생성(PAUSED) → 수동 ON → **Meta WL 합류**(별도 채널 아님)
- **Meta**(WL+IH 동일 랜딩): PPSU→원터치(fliptop 라쿠텐) / 스텐→스텐(라쿠텐). D+3 게이트 CPC≤95·CTR≥8%·CPLPV≤130→졸업/OFF
- **TikTok**: PPSU영상→기본컵(라쿠텐) / 스텐영상→스텐(라쿠텐). 틱톡샵(TTS)=추후 예정(현재 라쿠텐만)
- **라쿠텐 RPP**: 판매중 3상품×20키워드 → 라쿠텐 3페이지. ¥5,000 소진+전환0=OFF
- **Amazon JP**: SP 2캠(스텐·PPSU)=메인 + SB 인지형 2캠(라이브·전환0, 하루 합 ~¥3,000) → 아마존 JP ASIN
- **Google Ads = 안 돌림(제외)**. Shopify 자사몰 등 추가 채널 없음(이게 전부)

## 랜딩 (littlefingerusa 라쿠텐샵)
- 기본컵: grosmimi_ppsu_strawcup300 ¥3,190 / 원터치(fliptop): grosmimi_ppsu_onetouch_srawcup ¥4,200 / 스텐: stainless_steel_strawcup_300 ¥5,800
- 아마존 ASIN: PPSU300 B08TZY1TFY / 원터치 B0DJNXD66N / 스텐 B0G6CCJ24K

## 핵심 설계 포인트
PPSU는 Meta(원터치)/TikTok(기본컵) **일부러 갈라짐** · 스텐은 Meta·TikTok 둘 다 **스텐으로 수렴** · 라쿠텐 3페이지=RPP·오가닉 섞이는 **수렴점**(순수 소셜=RPP 차감)

## 교훈 (직전 세션 자기교정)
- 받은 예시(AMZ PPC 구조도)는 **현석님 US 구조** → JP에 갖다 붙인 게 오류. "예시 베끼지 말고 실제 집행중인 것만 조사" 지시 어김. US 티어트리·날조 운영루프·안 돌리는 SB 노드 전부 걷어냄.
- 빌더 PNG(폐기 가능): .tmp/miro_flow_jp.py / .tmp/miro_flow_jp.png (v3)

## 보드 구조 (2026-10-06 — 2차 재편, 랜딩 기준 수렴)
세은 1차 지시: 예시(AMZ PPC)처럼 트리. → 2차 교정: "트리 화살표가 다 겹쳐 헷갈림. 같은 랜딩 가는 건 한 곳으로 깔끔히 모이게." 트리(플랫폼→가지→랜딩)는 수렴선이 멀리서 교차=혼란 → **랜딩 기준 그룹핑(landing-centric)**으로 전환.
- 레이아웃: **왼쪽 유입(플랫폼·캠페인 박스, 랜딩별로 묶음) → 오른쪽 랜딩 1개로 직선 수렴**. 같은 랜딩 유입을 바로 옆에 스택 → 짧은 직선이 한 점 수렴, 교차 0.
- 그룹: 기본컵←(TikTok PPSU영상·RPP기본컵) / 원터치←(Meta PPSU소재·RPP원터치) / 스텐←(Meta스텐·TikTok스텐·RPP스텐 3선) / 아마존←(Amazon SP·SB) / TTS←(TikTok 틱톡샵, 점선 예정).
- 플랫폼=유입박스에 굵게 라벨(별도 열 없음). 운영방안 드릴다운=우측 보라 메뉴박스(textArea 5 anchor 링크 → 상세 프레임 moveToWidget). 프레임 id: Meta 3458764686147081828·TikTok 29·RPP 30·Amazon 31·인플 32.
- 상세 프레임 5개(y=1860~, f0f5fd): 각 플랫폼 운영방안(D+3게이트·졸업/OFF·¥5000컷·目安CPC·감시견 D+3 등).
- ⚠️ 미검증: 메뉴 textArea <a href> 링크가 실제 클릭되는지 세은 확인 필요(글자로만 보이면 raw URL로 교체).
- Miro 팁: 큰 update는 **타임아웃 빈발** → 부분적용됨(읽기로 확인 후 빠진 것만 재전송). 기존 위젯에 connector 걸려면 그 위젯 stub(id+data-miro-id) 동봉 후 line의 data-start/end가 local id 참조. 노드 reposition=full box+data-shape+data-miro-id. textArea 본문 <b>/<br/> 리터럴·data-content 속성은 &lt;b&gt; 이스케이프.

## 워크플로우 구조 정본 (2026-10-06 세은 확인 — 한 판에 담을 계층)
세은 3차 교정: 랜딩 말고 **각 플랫폼 운영 구조 전체 계층**을 한 판에 (예시 AMZ 구조도 깊이). 구체 임계숫자는 클릭-상세 OK지만 기본 구조(IH/WL·Testing/Proven 등)는 한 판에.
- **Meta**: 2축 = IH + WL(WL-G 기프팅/WL-P 유상). 집행 전=오가닉 D+3 방치→정량(D+3 좋아요)+정성(7축) 심사→충족분만 집행.
  - **WL** = 캠페인 3개: Testing(제품통합·1소재=1adset·ABO·₩8,000/day) → PPSU Proven / Stainless Proven(제품분리). Testing D+3 OFF(CPC≤150&CTR≥5% 생존/CPLPV≥190 OFF)·졸업(CPC≤95&CTR≥8%&CPLPV≤130→Proven 새 ad_id). Proven CPLPV OFF(14d&30d≥150).
  - **IH** = ✅세은확정: **Testing/Proven 없음. 한 캠페인에 전부 넣어 돌리는 단일 구조.**
  - WL 자동화: 감시견 D+3 미부착→WL 광고 PAUSED 자동생성→수동 ON.
- **RPP**: 판매중 3상품(스텐·PPSU기본컵·원터치) 각 20키워드. 키워드종류=branded/competitor/generic([[feedback_keyword_types_branded_competitor_generic]]). 설정CPC(상한)/추천CPC(目安). OFF=¥5,000+전환0.
- **Amazon JP** (✅2026-10-06 Ads API 실측): **SP**(평시=기존) = SS(스텐)/PPSU, 각 키워드 branded/competitor/generic. **SBV**(=SB아님! Sponsored Brands Video·브랜드영상·테마별 9/1생성) 3개: SBV_消毒_KT(ENABLED ¥1,000/d·14d ROAS0.34)·SBV_目盛り_KT(ENABLED ¥2,000/d·ROAS0.20)·SBV_お手入れたんたん(PAUSED). 돌아가는 2개=消毒·目盛り·효율낮음(전환0 아니라 ROAS낮음). JP profile 3736142261021843. SD 없음.
  - API 조회법: AMZ_ADS_JP_{CLIENT_ID,CLIENT_SECRET,REFRESH_TOKEN,PROFILE_ID}(=JP전용키·AMAZON_ADS_*는 US라 400) + advertising-api-fe + reporting v3 adProduct=SPONSORED_BRANDS reportTypeId=sbCampaigns. list v4 maxResults≤100. 빌더 .tmp/probe_sb_api.py.
- **TikTok** (✅세은 확정): **Spark Ads** — GMV Max·콜라보 아님. 자사(IH) 영상을 광고로 부스팅=Spark Ads(자사계정 오가닉 게시물 부스팅도 Spark). 랜딩 라쿠텐(외부)이라 샵광고(GMV Max/VSA/LSA/PSA) 전부 제외(샵 랜딩만 가능). DK에 TikTok 광고데이터 없음(API반려).
- **키워드 종류는 항상 branded/competitor/generic 3분류** (속성 등 임의분류 금지).

## 보고용 시계열 보드 (2026-10-06 — 지아님 양식 적용)
- **새 보드: https://miro.com/app/board/uXjVEditwHM=/** ("GROSMIMI JP 퍼포먼스 — 시계열 한 판 (보고용)"). 기존 루트맵 보드(uXjVEeeyfUQ)는 산만해서 보고용은 새 보드로.
- 세은 지시 변천: 구조형/시계열형 둘 다 만들어 컨펌 → 지아님 보드(실제 답) 보고 **시계열(하이브리드)**로 확정. 운영룰(E/I·숫자)은 나중 별도 페이지, 지금은 **시각화 시계열**만.
- 양식: 각 플랫폼 = 셋업→집행→(보호구간)→판정 시계열 + 판정 배지 **CUT(red)/WATCH(amber)/KEEP(blue)/SCALE(green)** + 상단 상태범례(확정/초안/미정/피드백).
- 섹션(세로 스택): ①Meta ②Amazon SP ③Amazon SBV ④RPP. **SP/SBV는 반드시 분리**(지아님처럼). **Meta 졸업(SCALE)→PPSU Proven 풀 / Stainless Proven 풀 각각 분리**→Proven 운영.
- ⚠️ Miro 프레임 이동: **data-frame(제목)+bg rect 포함한 g**라야 이동됨. 바 <g data-miro-id>만은 skip. 큰 배치 이동은 타임아웃(단일 프레임은 OK). 쓰기 타임아웃나도 대부분 반영됨(읽기로 확인).
- 진행: ①Meta(졸업→PPSU/Stainless Proven 풀 분리) ②Amazon SP(**SS/PPSU 캠페인 각각 집행 트랙 분리**) ③Amazon SBV ④RPP ⑤TikTok(Spark Ads) — 5판 전부 올림.
- ⚠️ **내일 (2026-10-07) 할 것 (세은 "내일 하자")**:
  - Amazon SP/SBV의 **보호구간·금요일 감사·ST 하베스트·T1~T3 티어·CUT/WATCH/SCALE 임계** = 전부 **지아님 US Amazon 보드에서 베낀 미검증분**. 세은 지적("어디서 보고 따라하는 거야"). → **삐삐(JP PPC)로 JP 실제 운영 확인** 후 교체 or 제거. JP엔 그 보호구간 룰 없을 수 있음.
  - 운영룰 상세(E/I·숫자·액션로그·용어집)는 별도 페이지로 추후.
  - 교훈: 참고 양식의 **US 전용 운영개념(보호구간 등)을 JP에 검증 없이 베끼지 말 것**. 양식(형태)만 차용, 수치/룰은 JP 실측.
- 참고양식 [[reference_jia_sbv_funnel_board_format]].

## 미완 / 다음
- 세은 트리모양·가지구성·클릭링크 피드백 반영(라이브 편집). 캠페인 더 세분화·상세프레임 내용 보강 가능.
- 아마존 JP SB 2캠 실제 이름은 DK 미수집→필요시 마존이 콘솔. (현재 라이브 확정·하루 합 ~¥3,000·전환0)
- 상세 프레임 안에 각 캠페인별 더 깊은 드릴다운(예시 US 티어트리처럼) 확장 가능.
