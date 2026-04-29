# Memory Index

## Feedback
- [트윗·DM 글자수 한도 사전 검증](feedback_char_limit_check_first.md) — X 트윗 본문 60~80자(280 weight), 작성 후 보여주기 전 자동 카운트 검증 필수. 위반 후 재작성 절대 금지.
- [워크플로우 push 전 secret 등록 검증](feedback_verify_secrets_before_workflow.md) — 새 GH Actions 워크플로우 push 전 `gh api ... secrets`로 등록 확인. .env에 있다고 GitHub에도 있는 거 아님 + dotenv 의존성도 점검.
- [下書き·재촉 표현 임의 추가 금지](feedback_no_unsolicited_draft_request.md) — 세은 지시 없으면 下書き 요청·일정 재촉 문구 임의 삽입 X. 인플루언서 페이스 존중.
- [사용 후기에 「素敵なエピソード」 호들갑 금지](feedback_no_overreact_to_episode.md) — 아이 반응·감상에 「素敵なエピソードですね」 X. 「お子様にお合いいただけ良い影響を〜嬉しく存じます」 톤으로.
- [같은 문단 감정 표현 반복 금지](feedback_no_repeat_emotion_expression.md) — 嬉しい/ありがたい/感謝 등 감정 단어는 한 문단 1회. 반복 발견 시 한쪽을 「拝見いたしました」「ご報告ありがとうございます」 등으로 치환.
- [본명 알면 본명 호칭 (닉네임 X)](feedback_use_real_name_when_known.md) — 메모리에 본명(姓) 있으면 STEP 6 이후 무조건 「姓+様」. ちえ様/えん様 같은 닉네임 호칭 금지.
- [영상·하서 수정 요청 불릿+단정조 금지](feedback_no_bullet_command_for_revision.md) — 「・~ ・~ カット」 항목 나열 X. 한 문단 흐름 + 「いかがでしょうか」 제안형 질문 마무리.
- [영상 단계별 STEP 매핑 정확히](feedback_video_stage_correct_step.md) — 만드는 중 = STEP 11 「下書きDM共有」, 투고 후 = STEP 12 「字幕외オリジナルメール」. 「完成データ」 질문에 STEP 12 안내 X.
- [DocuSeal 계정 작성 불필요](feedback_docuseal_no_account_needed.md) — STEP 6에 「アカウント作成が必要」 문구 절대 X. 메일 링크 클릭 = 서명 끝.
- [제품·사이즈·색상 변경 추적 필수](feedback_track_product_decisions.md) — 메모리의 「관심 제품」만 보지 말고 최신 변경 이력까지 추적. 사이즈/색상이 정식 옵션 안 맞으면 무조건 정지.
- [인플루언서 진행 이력 끝까지 확인](feedback_check_full_progress_history.md) — 메모리 「다음 액션」만 보지 말 것. 인플루언서 메시지 맥락(5/11+置き配?·下書き·広告코드 등)이 진짜 STEP 시그널.
- [제작 전 「嬉しく拝見」 X / 「ご快諾」 톤](feedback_no_premature_emotion_about_creation.md) — 수락만 한 시점에 결과물 칭찬 X. 「ご快諾」 「ご協力に感謝」 「お受け入れいただき」 톤으로.
- [IG 기획안은 100% 카루셀](feedback_ig_carousel_only.md) — 인획이 주간 IG 기획안 20개 모두 카루셀로만. 릴스·단일이미지 금지.
- [리스트형 IG 카루셀은 행동 동사형](feedback_ig_list_action_verbs.md) — "○○ 5선/대책/방법"은 명사 아이템 X, "~하기/~する" 행동형 문구로.
- [JP 표현은 일상어로](feedback_jp_natural_expression_check.md) — 직역·외래어 카피 금지. 일본 일상에서 실제 쓰는 표현 (예: UVクリーム ❌ 日焼け止め ✅).
- [IG 카루셀 슬라이드 제목은 6~10자](feedback_ig_slide_title_short.md) — 동사·빈도·근거는 제목에 X. 주어+핵심 키워드만. 디테일은 설명 줄로.
- [육아 정보 카피는 사실 검증 후](feedback_verify_parenting_facts.md) — 양·빈도·시간 수치 추정 금지. "30분에 한 모금" 같은 잘못된 기준은 탈수·위해 정보.
- [자동화는 헬스체크 후 선제 보고](feedback_automation_health_check.md) — 자동화 작동 여부 묻기 전에 먼저 확인. 실패면 알림 step + 수동 재실행 즉시.
- [wl_codes_sync 수정 진행 중](project_wl_codes_sync_pending.md) — yml fix 완료, 세은 Secrets 등록 대기. 등록 후 commit/push/trigger 남음.
- [자격증명/키 요청은 값까지 가져오기](feedback_credential_fetch_actual_value.md) — "키 있어?" 질문에 위치만 X. 평문 값 추출 + 출처 경로 동봉. sed 마스킹은 본인 요청에 부적합.
- [STEP 7 주소 요청에 우편번호 포함 명시](feedback_step7_request_postal_code.md) — 「・ご住所(郵便番号も含めて)」 형식 고정. 누락 방지.
- [돈/금전 이모티콘 DM 사용 금지](feedback_no_money_emoji.md) — 💸 💰 💴 💵 🪙 X. 송금 안내는 텍스트 + 정중 이모티콘만.
- [답신 인용 시 감정 지어내기 금지](feedback_no_emotion_fabrication.md) — 원문에 없는 "좋아한다/즐긴다/마음에 들어함" 투영 금지. 원문 사실/표현 그대로만 인용.
- [24개월 초과는 전 제품 대상 외](feedback_age_limit_24months.md) — 상한 24개월. 25개월+는 ワンタッチ·ステンレス·PPSU 어떤 것도 추천 금지. 2세5개월=29개월 대상 외.
- [라쿠텐 발송대기 넘어온 것만 처리](feedback_rakuten_only_ship_wait.md) — RMS vs KSE 건수 차이 무시. 누락 경고·재실행 제안 금지. 다음 회차에 자동 흡수.
- [Playwright 실패 시 headed 먼저](feedback_try_headed_before_giving_up.md) — headless 차단·렌더 이슈를 서버 장애로 단정 금지. headed/UA/slow_mo 먼저.
- [발견한 버그는 묻지 말고 즉시 수정](feedback_fix_obvious_bugs_without_asking.md) — 버그 발견 → 수정 → dry-run → 보고. 수정 여부 질문 금지.
- [수신 확인 질문엔 다음 STEP 묶기](feedback_combine_confirm_with_next_step.md) — 직전 STEP 완성됐으면 안심 답 + 다음 STEP 한 통으로.
- [Stage 2는 12개월 이상으로 통일](feedback_stage2_12month_for_influencer.md) — 인플루언서 대응 시 「10ヶ月頃」 X. 항상 「12ヶ月以上」.
- [PII 메모리 저장 금지](feedback_no_pii_in_memory.md) — 본명·IG·이메일만 OK. 주소·전화·우편번호·수령일시 저장 X. STEP 7 정보는 즉시 사용 후 폐기.
- [STEP 12 광고코드+원본영상 항상 함께](feedback_step12_ad_code_with_original_video.md) — 二次利用 거절 무관. 광고코드만 단독 요청 금지. 한 DM에 묶음.
- [계약서 정보 수집 2개만](feedback_contract_info_fullname_email_only.md) — STEP 6에서 풀네임·이메일만. IG 핸들·송금처 물어보지 마.
- [DM 길면 분리](feedback_split_long_dm.md) — 상품 선정 + 계약서 정보 한 번에 요청 금지. 단계별로 분리.
- [상품 도착→상의 흐름 括弧 템플릿 무조건](feedback_arrival_discussion_template_always.md) — STEP 5 括弧 원문(첫 반응·연습 즉시 촬영 OK) 그대로 복사. 축약 금지.
- [공식 색상·제품명만 사용](feedback_use_official_color_names.md) — 인플루언서가 다른 이름으로 불러도 항상 라쿠텐 공식 표기로만 DM·계약서 작성.
- [미국 인플루언서 기준 문구 금지](feedback_no_us_reference_phrase.md) — "일본 시장 막 진입 + 미국 인플루언서 기준 가이드라인" 문구 DM에서 전부 제거.
- [DocuSeal 발송 전 세은 승인 필수](feedback_docuseal_approval_required.md) — DOCX 생성은 자동 OK, DocuSeal 이메일 발송·서명 필드 배치는 무조건 세은 승인 후.
- [계약서 생성 필수 필드 2개](feedback_contract_required_fields.md) — deliverables_detail + product_type 항상 지정. 누락 시 "いずれか" "例：" 문구 그대로 남음.
- [세은 템플릿 그대로 쓰기](feedback_use_template_as_is.md) — 세은이 준 DM 원문 1글자도 수정 금지. 이름·서명만 붙임.
- [본명 알면 姓様으로 불러](feedback_call_by_real_name.md) — 한자 본명 받은 시점부터 닉네임(りぃ 등) 말고 姓+様으로 호칭 변경.
- [경쟁사 제품 경험 공감 금지](feedback_no_competitor_empathy.md) — 인플루언서 다른 브랜드 스트로우마그 언급해도 공감/감사 문장 추가 X.
- [12개월 이상 PPSU 추천 금지](feedback_12m_over_no_ppsu.md) — 1세+ 아이는 ワンタッチ+ステンレス 2개만 제시. PPSU 절대 X.
- [바이오 월령은 추정형으로](feedback_bio_age_phrasing.md) — 본인이 직접 안 밝힌 월령 쓸 땐 "プロフィール 拝見하니 ~세 같으시니" 형태.
- [스테인리스 선제 추천 금지](feedback_no_stainless_first.md) — 우리가 먼저 스텐레스 제안 X. 상대가 원하면 그때 가능하다고.
- [해시태그는 "포함" 표현](feedback_hashtag_include_not_change.md) — 해시태그 요청 DM에 "변경" X, "포함해주시면 좋겠다" O.
- [일본어 시점 표현 정확히](feedback_jp_time_reference.md) — 1시간 전 → 先ほど, 며칠 전 → 先日. 당일 콘텐츠는 先ほど/本日/今朝.
- [리치아웃은 겸손한 톤](feedback_reachout_humble_tone.md) — "自信を持って" X. "お試しいただけますと嬉しく" O. 팩트만 담백하게.
- [팔로우업 DM에 시간 경과 언급 X](feedback_followup_no_time_elapsed.md) — "1ヶ月が経ちました"·"투고일 1주 남음" 압박 금지. 근황+진행 상황만 물어.
- [인플루언서 조회는 seeun RAG 필수](feedback_use_seeun_rag.md) — SE/memory 비어도 Desktop/seeun/tools/influencer_rag.py --lookup 실행.
- [세은 지시어 DM에 복붙 금지](feedback_dont_copy_instruction_into_dm.md) — "앞으로/이번부터/이런 식으로" 등 Claude 메타 지시는 DM 본문에 넣지 말 것.
- [수정 요청 전 감사/칭찬 먼저](feedback_praise_before_revision.md) — 하서/캡션 수정 요청 시 "나머지 잘 만들어 주셔서 감사" 문구 필수.
- [세은 템플릿 톤 엄수](feedback_stick_to_template_tone.md) — DM 톤은 세은 템플릿·과거 DM 기준. 캐주얼/고자세/리드 어조 금지.
- [STEP별 템플릿 섞지 말 것](feedback_dont_mix_steps.md) — 협상 DM에 제품 선정 문구 붙이기 X. 단계별 문구만.
- [호칭은 IG 표시명 그대로](feedback_ig_display_name_fallback.md) — 본명 모르면 핸들 추측 X, IG 표시명(장식 폰트 포함) 그대로 + 様.
- [STEP 5에 영상 방향 상담 안내](feedback_step5_video_direction_note.md) — 제품 선택 DM에 "영상 제작 전 방향 상담 흐름 OK?" 문구 항상 포함.
- [아이 구분 표현 금지](feedback_no_child_position_label.md) — "막내/큰아이/下のお子様" 등 위치 표현 X. 그냥 "お子様/아이".
- [Git pull 금지](feedback_no_git_pull.md) — SE 폴더 remote 없이 유지, pull/fetch 금지
- [중복 실행 금지](feedback_no_duplicate_runs.md) — 결과 있으면 재크롤링 말고 캐시로 처리
- [맥락 추측 금지](feedback_dont_assume_context.md) — 모호한 지시어는 물어보기, 메모리로 단정 X
- [사용자 행동 단정 금지](feedback_dont_blame_user.md) — 로그 기반 사실만, 세은 탓 돌리지 말 것
- [검색 규칙](feedback_search_thoroughly.md) — 인플루언서 정보는 .tmp, lightrag, Z: 메모리 전부 검색
- [DocuSeal 사용](feedback_use_docuseal_not_docusign.md) — DocuSign 아닌 DocuSeal
- [운영 피드백](feedback_operations.md) — KSE, 라쿠텐, 아마존, 주문처리
- [콘텐츠 피드백](feedback_content.md) — IG, 트위터, 스카우트, 랭킹
- [계약서 피드백](feedback_contract.md) — 계약서 생성, DocuSeal, 플레이스홀더
- [일반 피드백](feedback_general.md) — 톤, 자동위임, 에러처리, 확인규칙
- [개인정보 git 금지](feedback_no_personal_data_git.md) — 계약서/개인정보 절대 git 커밋 금지
- [자신감 있게 답변](feedback_confident_answers.md) — 질문에 주눅 들지 말고 근거 있게 설명
- [하서 3종 필수](feedback_draft_three_items.md) — 캡션+영상+썸네일 다 받아야 사내 협의
- [상품 도착 DM](feedback_product_arrival_flow.md) — 투고 포인트 바로 안 보냄. 사용 후 방향 협의
- [24개월 이상 불가](feedback_age_limit_24months.md) — 24개월↑ 아이는 제품 없음, 콜라보 불가
- [우리 측 거절 시 사과 과하게](feedback_apology_heavy.md) — 우리 사정으로 거절할 때 사과 많이
- [Affiliate 도착→가이드라인](feedback_affiliate_product_arrival.md) — affiliate는 도착 시 가이드라인 링크 발송
- [DM 바로 작성](feedback_just_draft_dm.md) — "작성할까요?" 묻지 말고 바로 초안
- [리드하는 톤 금지](feedback_no_leading_tone.md) — "제안드리겠습니다" 금지, "함께" 뉘앙스로
- [IG 캡션 짧게 요약](feedback_caption_short_summary.md) — 기획안 내용 전부 쓰지 말고 핵심 5~8줄로
- [자동화 3회 제한](feedback_max_3_retries.md) — 3번 실패하면 재시도 중단, 원인 정리 후 보고
- [되는 것부터 먼저](feedback_do_working_task_first.md) — 하나 막히면 되는 작업 먼저. 실패 집착 금지
- [영상 OK 시 썸네일·캡션 항상 확인](feedback_always_thumbnail_caption.md) — 영상 검수 DM 때 썸네일·캡션 요청 포함 여부 세은에게 먼저 묻기
- [제품 링크는 상품 페이지로](feedback_product_link_not_shop_root.md) — 샵 루트 URL 금지, 워크플로우 표준 링크 사용
- [계약 정보 수령 즉시 DOCX 생성](feedback_contract_info_auto_generate.md) — 정보 수령 → generate_influencer_contract.py 실행이 기본 액션
- [계약서 이름은 한자 원칙](feedback_contract_name_kanji.md) — カタカナ만 받으면 한자 확인 재요청
- [레퍼런스 IG는 이미지 텍스트까지 확인](feedback_reference_read_image_text.md) — picnob 캐시로 슬라이드 추측 금지. imginn alt-text로 이미지 속 문구까지 읽고 매핑
- [STEP 2 가이드라인 조정 가능 안내](feedback_guideline_adjustable_note.md) — 제품 소개 DM에 "가이드라인 협의 조정 가능 + 언제든 문의" 문구 필수
- ["기억해둬"는 3중 연결](feedback_memorize_three_way.md) — workflow + SKILL.md + memory/reference 3곳 모두 업데이트해야 재호출 가능. 파일 하나만 두면 고아됨
- [DM 작성 전 feedback 재조회](feedback_check_feedback_before_template.md) — 워크플로우 템플릿 쓰기 전 상황 관련 feedback_*.md 먼저. 충돌 시 feedback 우선.
- [파일 자동 수정 전 구조 비교](feedback_verify_file_structure.md) — 두 파일 비교·병합 시 헤더 동일 가정 금지. 실제 헤더 읽고 매핑 구성 후 수정.
- [외부 도구 한계는 공식 문서 확인](feedback_verify_tool_limits_officially.md) — ManyChat/Zapier 등 "불가능" 단정 전 공식 docs/community 검색. IG 공식 API 기준만 쓰지 말 것.
- [IG CTA 5개 톤·행동 규칙](feedback_ig_cta_focus_follow_profile.md) — 모든 게시물 CTA 후보 5개는 호기심+프로필 / 저장 / 공감 톤만, 액션은 팔로우 OR 프로필 링크로 통일. 혜택훅·DM 단독 금지.

## Influencers (influencers/ 폴더)
- 27개 파일 — 인플루언서별 메모리 + DM 로그
- 검색: `memory/influencers/influencer_{handle}.md`

## Product
- [3제품 정식 사이즈·색상 옵션](product_color_size_options.md) — PPSU·ワンタッチ·스테인리스 전체. 라쿠텐 공식 확인 2026-04-22. **DM 쓸 때 반드시 이 문서로 검증.**
- [소독 가이드](product_disinfection_guide.md)
- [크로스컷 vs 에어밸브](product_straw_crosscut_airvalve.md)
- [Stage 1·2 빨대 교체 정책](product_straw_stage_swap_policy.md) — PPSU ストローマグ는 Stage 1 기본, 교체 불가. Stage 2 원하면 ワンタッチ 대안

## Project
- [Q2 2026 OKR](project_okr_q2_2026.md)
- [일일 인플루언서 스카우트](project_daily_influencer_scout.md)
- [일일 인사이트 Teams](project_daily_insights_teams.md)
- [일일 주문 요약 Teams](project_daily_order_summary_teams.md)
- [라쿠텐 랭크 트래커](project_rakuten_rank_tracker.md)
- [하네스 시스템](project_harness_system.md)
- [W5 입구 컨텐츠](project_w5_entrance_content.md)
- [어필리에이트](project_affiliate_influencers.md)
- [영상 제작 스타일 정책](project_video_style_policy.md) — AI 음성 변조 OK, 일상 사용형 영상 환영, 레퍼런스 제공 가능.

## User
- [세은 페르소나](user_persona_name.md)
- [WJ 이름](user_wj_name.md)

## Session
- [2026-04-29 세션](session_20260429.md) — wl_codes_sync GitHub Actions 자동화 수리 + 메타 광고 화이트리스팅 가이드 + 트위터 @grosmimi_jp 분석/「韓国ママの〇〇」 시리즈 + 일주일 35개 기획안 엑셀+Teams + 슬롯 cron 알림 시스템(X:55 발동, secret 등록 + dotenv optional fix).
- [2026-04-24 세션](session_20260424.md) — 라쿠텐 1건 + DM 10건 + JP OKR Notion 정비 + IG 기획 자동화 대수술(dedup/KO 병기/하드코딩 제거).
- [2026-04-23 세션](session_20260423.md) — (오전) 마존이 주문처리 + KSE 200ml/300ml 버그 / (오후) DocuSeal Unknown Submission 추적 → 세은/ONZ 계정 공유 구조 발견, JP webhook 등록 + external_id 삽입 임시조치
- [2026-04-22 세션](session_20260422.md) — (오전) CRM Django 경로 + 파이프라인 9명 + Olive 카피 / (오후) 트위터 #今日のグロミミ 시리즈 + 해시태그 재조사(qdr:w) + Apify $800 breakdown + 라쿠텐 ALL PASS + 데이터키퍼 권한정책 + IG CTA 규칙 개편
- [2026-04-24 오답노트](mistakes_20260424.md) — 계약서 SOP 누락(saki) / 답신 감정 지어내기(児玉) / 24개월 초과 추천(のんちゃん) / 24개월 상한 명시 누락
- [2026-04-22 오답노트](mistakes_20260422.md) — 캡션 4연속 + 자동메모리 + (오후) TikTok 저작권·Apify 리셋 오단정·Vacuous PASS 재발·CTA 본문답반복·ボトル→マグ·조사 누락
- [2026-04-17 오후](session_20260417c.md) — 아마존 3+1건, 라쿠텐 ALL PASS, KSE 업로드 미해결
- [2026-04-13 세션](session_20260413.md)
- [2026-04-07 세션](session_20260407.md)

## Reference
- [Content Keeper 데이터 스펙](reference_content_keeper_spec.md) — gk_content_posts·관련 테이블·API·slim 모드 무시 컬럼. 다운스트림 데이터 소비 세션의 진입점.
- [빨대 차이 답변 템플릿](reference_straw_difference_template.md) — 10개월 이하 아이맘이 ステンレス/ワンタッチ 요청 시. Stage 1/2 + 12개월 + 호환성.

- [見送り 수락 DM 템플릿](reference_decline_acceptance_template.md) — 소프트 거절 시 워크플로우 "見送り" 섹션 템플릿. 재설득 금지.
- [가이드라인 URL 2종 (2026-04-22~)](reference_guideline_url.md) — STEP 2: natural_sp, STEP 5: categories_sp. 단계별로 다른 링크. 동시 발송 금지.
- [STEP 2 템플릿 v2 (2026-04-22)](reference_step2_template_v2.md) — PPSU 중심 + 미국 문구 제거 + 가이드라인 별도 공유 안내. 리치아웃 답장용 기본.
- [계약서 SOP (2026-04-22 확정)](reference_contract_sop.md) — 정보 수령 → DOCX 생성 → 세은 승인 → DocuSeal DOCX 업로드 → STEP 6.5. text tag 자동 필드 시스템.
- [DocuSeal 계정 공유 구조 (2026-04-23)](reference_docuseal_shared_account.md) — `docuseal.orbiters.co.kr` = 세은+ONZ 공용. OSS Community는 account 1개. user 이메일 변경=분리 아님. JP tool은 external_id="GROSMIMI_JP_*" 자동.
- [계약서 템플릿](influencer-contract-templates.md)
- [실수 기록](mistakes.md) / [로컬](mistakes_local.md)
- [오답노트 2026-04-20](mistakes_20260420.md) — SG IG "그대로 따라하기" 캡션만 보고 추측한 실수
- [Team Claude Guardrails](reference_team_claude_guardrails.md) — ORBI 공유 리포 no-touch zones, git hygiene, 원준 승인 사항
- [기존 인프라 먼저 확인](feedback_check_internal_infra_first.md) — 새 도구/비용 꺼내기 전 .env/tools/ 조사
- [ManyChat 팔로우 게이트 쿠폰 workflow](reference_manychat_follow_gate.md) — IG 댓글→팔로우 체크→라쿠텐 쿠폰 DM 자동발송 SOP. 리공이가 호출 시 자동 로드
- [CRM 건들면 무조건 적대감사](feedback_hostile_audit_crm_always.md) — 스크립트 생성/수정 후 codex 감사 필수. 소스 판별 없이 작업 금지
- [오답노트 2026-04-21](mistakes_20260421.md) — workflow exit 0 보고 성공 선언 2회, CRM 소스 판별 오판 2회
- [세션 2026-04-21](session_20260421.md) — JP CRM posted 자동전환 시스템 + 13명 sent 복구 + 대시보드 로그인 이슈
- [JP CRM 대시보드 URL](reference_jp_crm_dashboard.md) — 2026-04-22~ orbitools.orbiters.co.kr/.../pipeline-crm/jp(#/us). 주소스 n8n staticData, Django 백필.
- [트위터 고정 시리즈 #今日のグロミミ](reference_twitter_series.md) — 코디 콘텐츠 시리즈 타이틀 + 고정/보조 해시태그 풀 + 캡션 템플릿. plan_twitter_content.py와 twitter_hashtag.py에 반영됨
- [GitHub Actions cron 정각 부하 회피](reference_github_actions_cron_offset.md) — 정각(0 X * * *)은 5~15분 지연. X:55 cron + 메시지 정각 표시 패턴 + JST→UTC 슬롯 매핑.
- [데이터 키퍼 권한 정책 (2026-04-22~)](reference_datakeeper_access_policy.md) — SSH/API 키 분리, 5단계 권한, 읽기전용 키 등록. 모든 에이전트 필독, 권한 부족 시 세은에 발급 요청
- [ScheduleWakeup 자기호출 금지](feedback_no_self_schedule_wakeup.md) — 파이프라인 중간체크 예약이 세은 요청으로 오인돼 2차 실행 유발. 절대 금지.
- [PPSU 스트로머그 3대 특징](reference_ppsu_mug_3_features.md) — PPSU 소재/안 샘/핸들 회전. 얇은 빨대 표현 금지.
- [이미지 프롬프트 출력 형식 명시](feedback_image_prompt_output_spec.md) — "텍스트 답변 금지, 이미지로 출력, 사진 위에 덧그려" 3문장 필수.
- [해시태그 10개 이내 고정](feedback_hashtag_max_10.md) — IG 캡션 해시태그 항상 ≤10개. 스킬 문서의 15~25 무시. 주제 관련만.
- [IG 기획안 dedup 방식 확정](feedback_ig_plan_dedup_confirmed.md) — 하드코딩 예시 제거 + 4주+배치간 dedup. 절대 복구 금지.
- [IG 기획안 모든 필드 KO 병기](feedback_ig_plan_all_fields_ko.md) — 소제목·대제목·비주얼방향·주제·캡션 전부 KO 번역 병기. 캡션만 KO 아님.
- [이메일은 Gmail API로](feedback_email_use_gmail_api.md) — SMTP/PW 금지. tools/send_gmail.py (OAuth) 사용.
- [오답노트 2026-04-28](mistakes_20260428.md) — VSCode 첨부 즉시 file path 묻기 / "사이즈 줄여" 모호표현 먼저 확인 / WJ-Test1 룰 임의 일반화 금지.
- [세션 2026-04-28](session_20260428.md) — 트위터 4건 패치 + 룰 위반 추적 + origin이 wjcho 머신에서 푸시되는 구조 발견 + 그로미미 일러스트 톤매칭 12회 실패.
