---
name: reference-tiktok-marketing-api-rejection-domain-security
description: TikTok Marketing API(광고 Reporting) 앱 "Grosmimi JP Ads" 심사 반려 정본 — 어느 API·어느 포털·거절사유(도메인 보안)·올바른 티켓 창구·rep 막힘. "그 틱톡 API 뭐였지" 재삽질 방지.
metadata:
  type: reference
---

# TikTok Marketing API 앱 반려 정본 (2026-10-01 틱톡이 규명)

## 우리가 신청한 API = TikTok **Marketing API** (광고 Reporting)
- **목적**: 자사 TikTok 광고 실적(지출·유료뷰·전환) 수집해서 **ads 분석**. (세은이 "ads 분석하려면 API 필요하다"던 그거)
- **앱명**: `Grosmimi JP Ads` · Account type = Direct Advertiser · scope = Ad Account Management + Reporting
- **소속 포털**: **`business-api.tiktok.com/portal`** (= "TikTok API **for Business**"). ⚠️ `developers.tiktok.com`(Content Posting·Research·Commercial Content 등 다른 API 묶음)과 **별개 포털**. developers.tiktok.com Support 의 Topic 목록엔 Marketing API 가 아예 없음(Account Issues/Commercial Content/Content Posting/Data Portability/Research/TikTok API 뿐).
- **도구**: `tools/tiktok_ads_jp.py` (BASE=`business-api.tiktok.com/open_api/v1.3`, Reporting v1.3) + `tools/tiktok_oauth.py`. 근거 [[session-20260921]].

## 반려 상태 (business-api 포털 My Apps 화면 실측)
- Verification Status = **Rejected**. App ID/Secret 미발급.
- **거절 사유 원문**: "unfortunately we are unable to onboard you to the TikTok for Business Developers platform **due to the security of the domain you have provided**. For further verification, please **contact your TikTok representative if you have one**. If you do not have a TikTok representative, please **open a developer ticket** for further checks."
- Rejected fields = Account type + Additional Info 전 필드 하이라이트됐으나 **명시 사유는 "도메인 보안" 하나뿐**. (전 필드 하이라이트를 개별 문제로 과잉해석 금지 — 9/28 교훈)
- 도메인 `grosmimijapan.com` 객관 상태(10/1 실측) = **정상**: HTTP→HTTPS 301, HTTPS 200, Let's Encrypt 유효(SAN 커버), WordPress(Nexcess nxcli.io 관리형). 보안헤더(HSTS/CSP) 無. → **TLS 깨짐 같은 self-fix 거리 없음.** "도메인 보안" 이 뭘 가리키는지는 TikTok 비공개 = 확인 못 함(추측 금지).

## 해결 = 사람 수동검증. 설정 재제출로 안 뚫림.
거절문이 "Update Application 재제출"이 아니라 **rep or ticket = 사람 수동 재심사**를 지정 → 블라인드로 도메인 "고쳐서" 재제출하면 같은 플래그 재발 가능성.

**루트 우선순위**:
1. **rep (광고/Business 쪽)** = 제일 빠름. 단 ⚠️ **틱톡샵 담당자 ≠ 광고팀** (TikTok 내 다른 조직). 우리는 광고 전용 rep 없음 + 샵 담당자도 무응답(10/1) → rep 루트 사실상 막힘.
2. **business-api.tiktok.com/portal 자체 "developer ticket" 플랫폼** (Need help? → Log in → submit ticket → technical product specialist) = **rep 없을 때 최선의 정식·타겟 루트.** 거절 난 포털 소속 팀한테 직접 감. ← **현 메인 수단.**
3. developers.tiktok.com Support(Topic=TikTok API) = 세은이 먼저 낸 곳. 일반 dev 창구라 덜 타겟. 3일째 무응답(공식 심사 며칠~2주라 아직 범위 내). 폐기 말고 보너스로 유지.

## ⚠️ 광고 **계정은 정상 운영 중** — API 거절 ≠ 광고 중단 (2026-10-02 세은 교정 「아니 그건 있어 그냥 api를 안 주는 걸걸?」)
- 거절된 건 **Marketing API(자동 수집용)**뿐. **TikTok Ads 계정 자체는 살아서 광고가 돌고 있다.**
- 계정: `littlefingerusa_adv` · **aadvid `7685564258871934997`** · Ads Manager 로그인 = 구글 OAuth(hello@grosmimijapan.com 추정).
- **API 없이 성과 수집법 = 브라우저(Playwright) 수동 스크랩.** 지속 프로필 `.tmp/tiktok_probe/userdata`(headed·channel=chrome·`--disable-blink-features=AutomationControlled`) → 세은이 1회 로그인하면 세션 저장돼 재실행 시 로그인 불필요. 드라이버 `.tmp/tiktok_probe/{login_and_scrape,scrape_sept}.py`.
- **성과 URL**: `ads.tiktok.com/i18n/manage/overview?aadvid=<id>&st=YYYY-MM-DD&et=YYYY-MM-DD` (기간 = st/et GET 파라미터). 기본 = 최근 7일. DOM(role=row/th) 추출은 TikTok 커스텀 컴포넌트라 실패 → **body innerText 파싱 + full_page 스크린샷 육안 교차**가 안정적. "Got It" 공지 팝업 먼저 닫기.
- **9월 실측 스냅샷**(참고): 트래픽 목적 캠페인 1개 `260918_traffic_IHV_PPSU&Stainless`(Active) — 지출 ¥64,126·노출 304,279·클릭 49,649·CTR 16.32%·CPC ¥1·전환(목적지) 40,082·CVR 13.17%. ⚠️트래픽 목적이라 "전환"=목적지 도달(랜딩/프로필) 액션, **구매 아님**.

## 10/12 업데이트 — 포털 "앱 없음" 화면 오독 금지 + 플랜B 실행
- **`/portal/apps` "You currently don't have any apps" + "Become a Developer" 버튼 = 프로필 미온보딩 상태의 정상 표시.** 반려 신청이 소멸된 게 아님 — 반려된 프로필 신청은 그대로 존재하고 「Update Application」으로 접근·수정 가능 (10/12 세은 스크린샷 2장 실측: 앱없음 화면 + Rejected 프로필 화면 공존 = 한 상태).
- `.tmp/tiktok_probe/userdata` 저장 세션은 **ads.tiktok.com 전용 — business-api 포털은 로그아웃 상태** (10/12 실측: /portal/apps 접근 시 로그인 화면). 포털 상태 확인은 세은 스크린샷 또는 세은 로그인 1회 필요.
- **플랜B 실행 지시 전달 (10/12, 반려 2주 경과)**: Update Application → Company Website `grosmimijapan.com` → **`orbiters.co.kr`** 교체(HTTPS 200 확인) + Description 끝에 재제출 소명 문단(영문, 세은에게 복붙 제공) 추가 → 제출. 대체 도메인 실측: zezebaebae.com 200 / onzenna.com 200 / orbiters.co.kr 200 / grosmimi.co.kr 000(죽음). **재제출 결과 대기.**
- Gmail MCP 토큰만료 지속(9/30~) → 틱톡 회신 메일 교차확인 못 함.

## 10/13 업데이트 — "도메인 보안"의 측정 가능한 실체 발견: Bytespider 차단
- **실측**: `grosmimijapan.com`·`orbiters.co.kr` 둘 다 UA에 "Bytespider"(ByteDance 공식 크롤러) 포함 시 **HTTP 400** 반환. Googlebot/bingbot/AhrefsBot/빈UA/일반UA = 전부 200. robots.txt는 깨끗 → 서버(호스팅) 레벨 UA 차단. 두 도메인 같은 호스팅 대역(173.249.147.x = Nexcess) → Nexcess 봇 차단 룰 공통 적용 추정(차단 주체 레이어는 미확정).
- **onzenna.com은 Bytespider 200** (Cloudflare지만 challenge 없음) = 즉시 쓸 수 있는 대체 도메인.
- Google Safe Browsing = 두 도메인 다 "No unsafe content found" (10/13 실측).
- **TikTok 공식 서포트 메일 원문 확보** (Reddit r/buildinpublic 1ul9o9i, 다른 포털이지만 같은 메커니즘): "our review team's system may automatically flag certain signals on a website, and when that happens the site can appear inaccessible from our end... double-check security, firewall, bot protection, hosting, regional access configurations." → 봇 차단 = 공식 인정 반려 트리거.
- 승인 전환 사례 공통 조치(같은 스레드): ①봇/방화벽 차단 해제 ②Cloudflare 프록시 제거/DNS 변경 ③신형 TLD→.com ④**반려 이력 피해 새 앱 신청서 생성 후 동일 내용 제출**(4연속 반려자가 이걸로 승인).
- 같은 포털·같은 거절문 사례(r/CompSocial 1t66lyb): 2년 된 정상 도메인도 6연속 반려·해결자 없음 → **아무것도 안 바꾼 재제출 = 확정 실패**.
- ⚠️ TikTok 심사 시스템이 Bytespider UA를 쓰는지는 비공개 = 확인 못 함. 단 측정된 유일한 보안 이상이고 공식 설명(봇 차단→접근불가 플래그)과 정합.
- **액션**: ①Nexcess/WP에서 Bytespider 400 차단 해제(해제 후 내가 curl 재검증) → grosmimijapan.com으로 재제출(1순위) ②해제 불가 시 onzenna.com으로 교체 제출 ③orbiters.co.kr은 같은 400이라 플랜B 도메인으로 **부적합 판명**(10/12 지시 철회).

## 10/20 업데이트 — Update Application 재제출 완료 (심사 대기)
- 세은 승인 하에 **Update Application 재제출** (신규 앱 아닌 프로필 재제출 — 포털 구조상 반려가 프로필 단위라 이게 유일한 재제출 입구).
- 내용: 전 필드 기존값 유지 + Description 끝에 "site administrator has since reviewed and resolved the domain's security configuration. Please re-verify grosmimijapan.com" 1문장 추가.
- **제출 검증**: 포털 상태 "rejected" → **"Your profile is currently under review"** 전환 실측. 캡처 .tmp/tiktok_probe/submit_before.png·submit_after.png.
- 경위: 세은이 "관리자가 (도메인 보안 건) 해결했다"는 답을 받음 → 그 말 기준으로 재제출. ⚠️단 Bytespider UA는 제출 시각에도 400 유지 실측(UA 6종 매트릭스 — Bytespider 3변형 400·TikTokSpider/Googlebot/일반 200). 차단≠반려원인 검증된 적 없음 → 또 반려 시 "측정 이상 제거 후에도 반려" 아님에 유의, developer ticket + 틱톡샵 담당자 루트.
- 기법: 포털 세션 = .tmp/tiktok_probe/userdata에 저장됨(10/20 로그인 상태 확인 — 10/12 "로그아웃" 기록은 구식). 제출 자동화 .tmp/tiktok_probe/portal_submit2.py (적응형: textarea 유무로 단계 판단·Submit 후 Confirm 모달 처리).

## 재삽질 방지 포인트
- "틱톡 API 거절" 다시 나오면 = **이 건(Marketing API / business-api 포털 / 도메인보안)**. developers.tiktok.com 아님. **단, 광고 계정은 별개로 운영 중 → 성과는 브라우저로 수집(위).**
- 상태 확인처 = business-api.tiktok.com/portal My Apps(Rejected) + 거절 코멘트. developers.tiktok.com/apps 는 빈 화면(단방향 폼, 상태추적 X).
- 9/28 오답(거절사유 창작) 재발 금지: 사유는 "도메인 보안" 한 줄, 그 이상은 확인 못 함. [[mistakes-20260928-fabricated-requirement-and-speculation]]
