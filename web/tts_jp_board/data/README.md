# TTS JP 크리에이터 파이프라인 — 수정 가이드 (사람 · Claude 공용)

US팀 보드(TTS 크리에이터 파이프라인, 아티팩트 Ba3VG3hRq6fSk99ZcyE4hV)의 JP 포크.
`index.html` 한 파일 + `data/` 의 날짜 버전 JSON 구조는 US와 동일. US판 수정 가이드의 탭/함수/공식 설명이 그대로 적용된다.

## US와 다른 점 (JP 플로우)

| 축 | US | JP |
|---|---|---|
| 풀 소스 | Reacher (무료) | **FastMoss API** `creator/v1/search` region=JP (`tools/fastmoss_jp.py`) |
| 영상 지표 | FastMoss API | 동일 (`video/v1/search` region=JP) |
| 아웃리치 | 이메일 대량 발송 (Reacher) | **Affiliate Center 인바이트+IM + IG DM** (기존 인플루언서 파이프라인) — 이메일 열은 JP에서 비활성 |
| 우리 영상 GMV 실측 | Reacher /videos/list | **TTS JP 셀러센터 스크랩** (샵 개통 후) |
| GMV Max 광고비 | Reacher /gmv-max | **Ads 헤디드 스크랩** (`.tmp/tiktok_probe/scrape_daily_ads.py` 패턴 재사용) |
| 협업 Fee·지급 | Reacher 리테이너·Stripe | **자체 체계** (DocuSeal 계약 · WL 탭 · 송금 기록) |
| 레벨 (lv) | Reacher L0~L7 | null — 샵 개통 후 Affiliate Center 레벨로 보강 |

## 데이터 버전

- `pool_20261030-v0.json` — 807명 시드 (2026-10-26 JP 맘풀 산정 CSV `reports/jp_tts_targets_20261026.csv`). GMV·ER 등 지표는 FastMoss API 키 수령 후 보강.
- `videos_20261030-v0.json` — 빈 v0. 키 수령 후 `tools/fastmoss_jp.py --videos --from-pool` 로 수집 (크레딧: 1명당 ~3).
- `versions.json` — US와 동일 스키마. 새 수집은 새 날짜 버전으로 추가하고 이전 버전은 지우지 않는다.

## RAW 원본

NAS `Z:\fastmoss_jp\raw_data\` (US의 `reacher_fastmoss`와 같은 share에 나란히):
- `Fastmoss\creator_search\` · `creator_videos_api\` · `live_api\` — API 응답 원문 + `_manifest.jsonl`
- `SellerCenter\` · `Ads\` — 샵 개통 후 실측 스크랩 원문
- `versions\` — 보드용 날짜 버전 사본
- `reference_us\` — US 보드 캡처본 (2026-10-30, 구조 참조용)

## 로더 차이 (v0 한정)

`loadData()`의 빈 파일 검증을 pool만 보도록 완화함 (videos 0건 허용) — US 원본은 둘 다 필수.
영상 수집이 들어오면 원복해도 된다. 그 외 로직은 US 원본 그대로.

## 갱신 절차 (키 수령 후)

1. `python tools/fastmoss_jp.py --ping` — 키·인증 헤더·BASE_URL 검증 (⚠️ BASE_URL/헤더 형식은 콘솔에서 확정 필요)
2. `--pool` — Baby&Maternity 카테고리 ID 런타임 해석 후 풀 수집 (실패 시 중단, `--all-categories`로만 우회)
3. `--videos --from-pool` — 풀 전원 영상 수집 (크레딧 소모 — 실행 전 세은 확인)
4. `versions.json`에 새 버전 수동 추가 → 보드 데이터 버전 탭에서 전환

## 고칠 때 주의 (US 규칙 준용)

- 숫자는 사실 값만. 데이터 파일을 지우거나 덮지 말 것 (버전 누적).
- 팀 입력(status) 문서는 지시 없이 바꾸지 말 것.
