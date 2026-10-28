# content_intake 멀티 폼(form_slug) 확장 — 적용 요청 (se.heo, 2026-10-21)

원지님, JP 인플루언서 트래커 구글시트를 DK PG로 이관하는 작업 1단계입니다.
JP 투고완료 폼(일본어 구글폼)을 content_intake의 **둘째 config**로 수집하려는 건데,
현재 수집기가 단일 활성 config 구조(`load_active_config`)라 멀티 폼 확장이 필요합니다.

## 요청 2건

1. **캡 승인**: code-edit MCP 캡 요청 **#8** (`code:edit:datakeeper:*`, se.heo) — 승인되면 datakeeper 쪽 12파일은 제가 MCP PR로 제출합니다. (`wongi_p1_datakeeper.diff` = 그 내용 사전 리뷰용)
2. **ingestion 2파일 직접 적용**: `wongi_p1_ingestion.diff` — validate_change가 `code:edit:ingestion:*`은 MCP 자동수정 미지원(signer-shared 미커버, "admin이 git으로 직접")으로 판정해서 부탁드립니다.
   - `apps/ingestion/collectors/content_intake_sheet.py`
   - `apps/ingestion/tests/test_content_intake_sheet_collector.py`

## 적용 순서 (이 순서면 어느 시점에 멈춰도 US 파이프라인 무사)

1. **datakeeper분 먼저** (모델 AddField 3개 — 전부 blank/default "" 메타데이터 연산, 백필 불요 + services 로더 확장 + 뷰/커맨드. 수집기는 아직 구 `load_active_config`를 부르는데, 그 함수를 primary(form_slug="") 고정으로 재정의해서 **동작 불변**)
2. **ingestion분** (fetch_v2 → per-config 루프 활성화)
3. 이후 JP config POST는 저희가 진행 (form_slug=jp_posting — 등록 전 폼 헤더 실측·GkBrandTracking grosmimi/jp 확인까지 체크리스트 있음)

## US 무중단 설계 포인트 (리뷰 시 봐주실 핵심)

- `load_active_config()` = **primary(form_slug="") 고정**으로 재정의 — JP config가 더 높은 version으로 생겨도 NAS base·수동업로드·erasure·다운로드 워커 등 레거시 호출처 16곳(전수 확인)이 계속 US config를 집습니다.
- **멱등키 불변**: `form_slug`는 `_KEY_CONTENT_FIELDS`·`SHEET_ALIAS_TARGET_FIELDS` 어디에도 안 들어갑니다(row_uid와 같은 "식별자" 분류). 기존 307행 source_row_key 변동 0 — US 픽스처 키 스냅샷 테스트로 못박음.
- orphan 판정·키매핑 가드 **폼 스코프** 추가 (한 폼의 read가 다른 폼 행을 '시트에 없음' 오판하는 교차 사고 차단).
- config POST의 active 플립도 **form_slug 스코프** (US 설정 저장이 JP config를 끄는 교차 사고 차단). version은 전역 max+1 유지 (media.root_version 역조회 앵커 보존).
- 비-primary 수집 실패는 `logger.exception` + PartialFailure로 격리 (primary 실패는 기존대로 run 전체 loud-fail — base.save가 제너레이터 소진 후라 US 행 유실 방지).
- collab_type 정규화(有償→Paid/ギフティング→Gifted)는 `_row_to_submission` 안 **키 계산 뒤** (핸들 정규화와 동일 패턴 — 파서 단일 공유 유지).

## 검증 내역

- 격리 git repo에 `git apply` 실제 적용 → 수정본 트리와 바이트 동일 재현 확인
- 전 파일 `py_compile` 통과
- 기존 테스트 깨지는 지점 전수 보정 (collector 테스트의 `load_active_config` mock → `load_active_configs`, sheet_edit fixture, stamp cmd 가짜 모듈) + 신규 테스트 6종 (US 키 불변 스냅샷 / 비-primary 스탬프 / orphan 폼 스코프 / 정규화+키 불변 / 상수 일치 / POST 교차 플립 금지)
- 마이그레이션: `0461_content_intake_multi_form_2026_10_21.py`, deps `("datakeeper", "0460_collab_link_force_pass_2026_10_15")` (라이브 leaf 실측), AddField 3개뿐 — 테이블 재작성 없음, 롤백 = 컬럼 drop

## 파일

| 파일 | 용도 |
|---|---|
| `wongi_p1_ingestion.diff` | **직접 적용 요청분** (2파일, +146/−10 상당) |
| `wongi_p1_datakeeper.diff` | 캡 승인 후 제가 MCP PR 제출 — 사전 리뷰용 (12파일) |
| `wongi_p1.diff` | 전체 통합본 (참고) |

문의는 세은(se.heo)에게 주시면 됩니다. 감사합니다.
