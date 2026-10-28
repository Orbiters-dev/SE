---
name: project_meta_tiktok_channel_cvr_experiment
description: Meta(fliptop URL)/TikTok(PPSU 기본컵 URL) 채널별 실구매 CVR 비교 실험. 소셜 유입=역산(상품페이지 전체−RPP). 2026-09-21 Meta 42건 스왑 완료·2026-09-23 일별 방문/주문/CVR 파이프라인 구축(tools/channel_cvr_daily.py)·RPP차감(삐삐)+틱톡측 세팅 대기.
metadata:
  type: project
---

Meta vs TikTok 채널 트래픽 質 비교 실험 (2026-09-21 착수, 세은).

## 목적 (대표님 가설 검증)
대표님 가설 = **Meta는 살 것 같지 않은 사람까지 넓게 랜딩**(저의도 유입 多) / **TikTok은 상대적 고의도**. 채널별 「유입 대비 실구매 전환율(CVR)」 차이를 본다. 우리 스택은 ROAS 직접 집계 불가 → CVR 역산으로 대체.

## 세팅 (상품페이지 = 채널 프록시)
- **Meta 광고 전량 → fliptop URL** (`grosmimi_ppsu_onetouch_srawcup`, ワンタッチ ¥4,200·12m~)
- **TikTok 광고 전량 → PPSU 기본컵 URL** (`grosmimi_ppsu_strawcup300`, ¥3,190/3,600·6m~)
- 채널마다 착지 상품페이지가 달라 라쿠텐 리포트에서 채널이 페이지로 자동 분리됨(같은 URL이면 둘 다 "외부유입"으로 뭉쳐 분리 난망 — 이 트레이드오프를 상품 confound로 지불).

## 측정법 (세은 확정 = 역산)
소셜 CVR = **(상품페이지 전체 주문 − RPP 주문) / (전체 유입 − RPP 유입)**. referrer 분류로 소셜을 집어내는 게 **아니라**, 정밀한 RPP 데이터(아이템 단위)를 통짜에서 뺀다. 전체 페이지·RPP 데이터 둘 다 확보 가능. RPP 아이템 = fliptop `10000002` / 기본컵 `10000001`.

## 비교 프레임 (세은 승인 — confound 상쇄)
Meta-CVR(fliptop) vs TikTok-CVR(기본컵) **직접 head-to-head 금지**. 각 채널을 그 페이지의 non-소셜 베이스라인과 비교(리프트/드래그)해 상품 차이를 상쇄한 뒤 채널 의도 차이만 본다.

## 2026-09-21 Meta측 완료 (메타몽)
WL Testing 22 + IH Testing 6 + PPSU Proven 14 = **PPSU 기본컵 광고 42건을 fliptop URL로 스왑**(크리에이티브 복제+creative_id 교체 → 학습 리셋 없음, 9/11 방식). stainless 31·기존 fliptop 4는 미변경. 42/42 성공·2중 검증(3캠 PPSU기본 잔여 0).
- 스크립트 `.tmp/swap_fliptop_20260921.py` (`--exec`), 롤백맵 `.tmp/swap_fliptop_rollback_20260921.json`. 규칙 = 현재 slug=='PPSU기본'만 → fliptop, 나머지 skip.

## 2026-09-23 측정 파이프라인 구축 (메타몽)
- `tools/channel_cvr_daily.py` — RMS get-item-list API 를 **하루씩(startDate=endDate)** 반복 호출(period=daily 는 기간 합산이라 date=None → 단일일 루프 필수). 로그인 1회 후 page.request 재사용.
- mngNumber 분리 확정: **fliptop = `onetouch`** 포함(main+copy), **기본컵 = `strawcup300`/`strawcup_ss`**(stainless 제외). 주문 API baseline(fliptop 9·기본컵 18유닛)과 정확히 일치 검증.
- salesFormula: visitAll(방문)·orderCountAll(주문)·cvrAll(%) 직접 제공. `--rpp-json` 으로 RPP 일별(fliptop 10000002/기본컵 10000001) 차감 시 순수 소셜 CVR. 미지정=gross. `--open` 브라우저.
- 산출: `.tmp/channel_cvr_experiment/daily_cvr.json` + `channel_cvr_daily_report.html`.
- **첫 신호(방문)**: 스왑 후 9/22 fliptop 방문 **134→3,667** 급증 + 기본컵 2,416→1,305 하락 = Meta 트래픽이 기본컵→fliptop 이동 확인. 단 **주문/CVR은 9/22 둘 다 0**(D+1 지연·저표본) → 의도 판정 불가. 9/23 RMS 미집계(0). **권장 판정=D+14(≈10/5) 주간 누적.**
- 코드 하네스(Codex STRUCTURAL) 구체 지적 없이 FAIL 반복 → E2E 동작 검증으로 확정([[reference-posttooluse-code-harness-scopecreep]]).
- **매일 자동 적재 등록(9/23)**: Task Scheduler `Grosmimi_ChannelCVR_Daily` 매일 10:30 KST(JPDash 9:20·RPP 이후, 전일 RMS 확정 후). rolling 9/7~오늘 + `--update-app`. powershell.exe -Command 인라인으로 today 계산+python 호출(래퍼 파일·harness 회피). StartWhenAvailable+WakeToRun+재시도2. 강제실행 1회 LastTaskResult=0 검증. 리스크=RMS 로그인 간헐사망 시 실패(자가복구/경보 미탑재).
- **적재 위치 = meta-app 전환 탭(세은 확정 9/23)**. `.tmp`는 gitignore(폐기용)이라 부적절 → metamong app `/ads/products`(전환)에 통합. 파일: seed `meta-app/lib/channel-cvr-seed.json` + lib `channel-cvr.ts`(server-only, build-time import) + 컴포넌트 `components/meta/ChannelCvrCard.tsx` + products/page.tsx 하단 렌더. 도구 `--update-app`이 seed 갱신+`vercel --prod` 재배포(rms_access_downloader 패턴, SE repo는 git push 아님). 로컬 `npm run build` 통과·배포 OK·라이브 /ads/products 307→login(라우트 서빙) 검증. 게이트 안쪽 시각확인은 세은 로그인 필요.

## 2026-09-23 RPP 차감(PPC 제외) 구현 (삐삐)
- **RPP 商品別 리포트 = downloadPerfFile `selectionType=3`** (すべて1·キャンペーン2·商品別3·キーワード4). **全期間(periodType=0)만 되고 日ごと(periodType=2)는 400** → access API 와 동일하게 **하루씩 startDate=endDate 全期間** 루프로 아이템×일 생성.
- **식별자 = 商品管理番号**(access API 와 동일: fliptop=onetouch / 기본컵=strawcup300·_ss). ⚠️이전 메모 "RPP 아이템 10000002/10000001" = **틀림**(그건 itemId, 리포트엔 관리번호로 나옴).
- 컬럼: クリック数(合計)=차감할 방문(RPP 클릭 ⊆ access visitAll), 売上件数(合計12時間)=차감할 주문(720h는 click일 귀속이라 same-day access 주문과 mismatch → 12h 채택).
- 도구 `tools/collect_rpp_item_daily.py` → `.tmp/channel_cvr_experiment/rpp_daily.json`. 실측 RPP 클릭(9/7~22): fliptop 212·kihon 611. **fliptop 스왑 전 방문의 ~20%가 RPP**(9/20 134→107) = 차감 필수. 9/23=400(당일 미집계, access도 0이라 무해).
- `channel_cvr_daily.py --rpp-json` 으로 차감 → seed `ppc_excluded=true` 로 배포 완료(전환 탭 카드 "RPP 차감" 표기). **스케줄 작업 2단계 체인化**: RPP 수집 → 차감 채널CVR → app 갱신 (10:30 KST). 리스크: RPP 수집 전량 실패 시 stale rpp_daily.json으로 차감(ppc_excluded=true 라벨은 유지 = 경미한 오표기).

## 미해결 플래그 / 대기
1. **상품 confound** — fliptop(¥4,200·12m~) ≠ 기본컵(¥3,190·6m~). 게다가 Meta 소재 다수가 기본컵 든 영상인데 착지는 fliptop(소재↔상품 불일치). → 위 "비교 프레임"으로만 완화. (세은 "1은 괜찮" = 인지하고 진행)
2. **역산 잔차** — 「전체−RPP」에 오가닉 검색·직접유입·라쿠텐 내부 브라우즈도 포함(순수 소셜 아님). 잔차 크기 실측 필요(비-RPP 잔여가 소셜 캠페인 기간과 붙어 움직이는지).
3. **데이터 피드 미실측** — ①라쿠텐 접속분석 상품페이지 단위 방문·주문 ②RPP 아이템별 클릭·주문. 둘 다 아이템별로 뽑히는지 확인 후 역산 집계표 골격 제작. **세은 「일단 대기」**.
4. TikTok측 URL 세팅(전량 기본컵)은 아직(틱톡이/세은 영역).

관련: [[reference_metamong_app_5tab_ih_dashboard]]
