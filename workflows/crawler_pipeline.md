# 크롤러 파이프라인 (Apify Content Daily Pipeline)

## 목적

인플루언서가 브랜드 계정을 태그한 IG 포스트 + TikTok 포스트를 매일 수집,
Google Sheets에 누적 저장하고 USA_LLM · SNS 탭 등 하위 시스템에 연결한다.

---

## 데이터 소스

| 소스 | 방식 | 비용 | 대상 |
|------|------|------|------|
| IG tagged posts | Instagram Graph API `/tags` | **무료** | US (onzenna.official, grosmimi_usa), JP (grosmimi_japan) |
| TikTok posts | Apify `free-tiktok-scraper` | ~$10/일 | US only (onzenna, grosmimi 검색) |
| IG 프로필 팔로워 | Apify `instagram-profile-scraper` | ~$10/일 | IG 크리에이터 전체 |
| Syncly 포스트 | `migrate_syncly_to_apify.py` | 무료 | US (D+60 Tracker 기반) |
| Shopify PR 주문 | `fetch_influencer_orders.py` | 무료 | 인플루언서 발송 현황 |

> IG tagged는 Apify에서 Graph API로 교체. 월 ~$600 절감.
> `META_GRAPH_IG_TOKEN` 없으면 Apify fallback 자동 적용.

---

## 핵심 시트

### Apify 시트 (소스 오브 트루스)
**ID**: `1mYofqMBYqIHS3XNQ29vDA__SzYBfkkGCPn3Jb8OxAkY`

| 탭 | 내용 | 업데이트 방식 |
|----|------|--------------|
| US Posts Master | 포스트별 메타데이터 (URL, 날짜, 좋아요/댓글/뷰, 팔로워) | append-only (기존 유지) |
| US D+60 Tracker | D+0~D+60 일별 메트릭 스냅샷 (192열) | 신규 append + 기존 D+N 갱신 |
| US Influencer Tracker | 크리에이터별 집계 (총 뷰/좋아요/댓글, 포스트 수) | 전체 재작성 (데이터 없으면 스킵) |
| JP Posts Master | 일본 동일 구조 | append-only |
| JP D+60 Tracker | 일본 D+N | 동일 |
| JP Influencer Tracker | 일본 크리에이터 집계 | 전체 재작성 (데이터 없으면 스킵) |

### Grosmimi SNS 시트 (하위 시스템)
**ID**: `1SwO4uAbf25vOR0UYWOUlxzy5gCbFRrNXwO2kAWydyeA`

| 탭 | 소스 | 담당 스크립트 |
|----|------|--------------|
| SNS | US Posts Master + Shopify PR 주문 매칭 | `sync_sns_tab_grosmimi.py` |
| USA_LLM | US Posts Master → 유저별 집계 | `update_usa_llm.py` |

### Syncly D+60 Tracker 시트 (외부 소스)
**ID**: `1bOXrARt8wx_YeKyXMlAS1nKzkZBypeaSilI6xDg4_Tc`

- `migrate_syncly_to_apify.py`가 Apify 시트에 없는 포스트만 추가
- Syncly 커버리지 = Apify의 거의 완전한 부분집합 (Syncly-only 1명 수준)

---

## 실행 흐름 (fetch_apify_content.py --daily)

```
1. IG 태그 수집
   ├── META_GRAPH_IG_TOKEN 있음 → Graph API /tags (무료)
   │   └── 페이지네이션, 500 에러 시 10s→20s retry
   └── 없음 → Apify instagram-scraper fallback

2. TikTok 수집 (Apify free-tiktok-scraper)
   └── 4개 쿼리: onzenna, grosmimi, grosmimi_usa, onzenna.official
       → 키워드 필터 (grosmimi, onzenna, straw cup 등)
       → 브랜드 계정 EXCLUDE

3. IG 프로필 팔로워 (Apify instagram-profile-scraper)
   └── IG+TT 크리에이터 전체 일괄 조회

4. 정규화 + 합산
   └── ig_norm + tt_norm → us_data (중복 제거, 날짜순 정렬)

5. Google Sheets 업데이트 (US)
   ├── US Posts Master (append-only)
   ├── US D+60 Tracker (D+N 갱신 + 신규 append)
   └── US Influencer Tracker (전체 재작성, 빈 데이터면 보존)

6. JP Pipeline (동일 흐름, IG Graph API or Apify)
   └── grosmimi_japan/tags → JP 3탭 업데이트
```

---

## GitHub Actions 전체 스텝 순서

```
apify_daily.yml (매일 KST 08:00 = UTC 23:00)

① fetch_apify_content.py --daily     # IG + TikTok 수집 → Apify 시트 6탭
② fetch_influencer_orders.py          # Shopify PR/샘플 주문 → .tmp/polar_data/q10_*.json
③ migrate_syncly_to_apify.py --region us  # Syncly → Apify 시트 누락분 추가
④ sync_sns_tab_grosmimi.py            # Apify US Posts Master + Shopify 주문 → SNS 탭
⑤ update_usa_llm.py                   # Apify US Posts Master → USA_LLM 탭
   └── 하이라이트 감지 (오늘 첫 감지 URL, 뷰 순)
   └── 트렌딩 감지 (전일 대비 뷰 50%+ 변화)
   └── .tmp/usa_llm_highlights.json 저장
⑥ build_apify_report.py               # HTML 일일 리포트 생성
⑦ send_gmail.py                        # wj.choi@orbiters.co.kr 발송
```

---

## 데이터 연결도

```
[IG Graph API]          [Apify TikTok]     [Syncly 시트]    [Shopify 주문]
      ↓                       ↓                  ↓                ↓
      └──────── fetch_apify_content.py ─────────┘                │
                              ↓          migrate_syncly_to_apify.py
                    [Apify 시트 - 소스 오브 트루스]                │
                    ┌─────────────────────────┐               │
                    │ US Posts Master (749행)  │←─────────────┘
                    │ US D+60 Tracker (432행)  │
                    │ US Influencer Tracker    │
                    │ JP Posts Master  (33행)  │
                    │ JP D+60 Tracker  (24행)  │
                    │ JP Influencer Tracker    │
                    └──────────┬──────────────┘
                               │
              ┌────────────────┼────────────────────┐
              ↓                ↓                    ↓
    sync_sns_tab_grosmimi  update_usa_llm    (향후 확장)
              ↓                ↓
    [Grosmimi SNS 시트]   [Grosmimi SNS 시트]
         SNS 탭               USA_LLM 탭
    (인플루언서 발송현황)   (크리에이터별 집계 +
                           하이라이트 + 트렌딩)
```

---

## USA_LLM 연결 상세

`update_usa_llm.py`가 Apify US Posts Master를 읽어 Grosmimi SNS 시트 `USA_LLM` 탭에 씀.

| 항목 | 내용 |
|------|------|
| 소스 | Apify 시트 > US Posts Master |
| 대상 | Grosmimi SNS 시트 > USA_LLM 탭 |
| 집계 | 유저별 총 뷰/좋아요/댓글, 최신 포스트, 팔로워 |
| 하이라이트 | 오늘 첫 감지 URL (detection_log 기반) |
| 트렌딩 | 전일 뷰 대비 50%+ 변화 (`usa_llm_prev.json` 비교) |
| 컨텐츠 통계 | 24h / 7d / 30d 신규 포스트 수 |
| 캐시 파일 | `.tmp/content_detection_log.json`, `.tmp/usa_llm_prev.json` (GitHub Actions cache) |

---

## 주요 설정값

| 키 | 값 | 비고 |
|----|----|------|
| `META_GRAPH_IG_TOKEN` | Ins_post_hook 앱 토큰 | ~60일마다 갱신 필요 |
| `IG_BUSINESS_USER_ID_ONZENNA` | `17841458739542512` | 고정 |
| `IG_BUSINESS_USER_ID_GROSMIMI_USA` | 미설정 | FB 계정 분리 이슈 |
| `IG_BUSINESS_USER_ID_GROSMIMI_JP` | 미설정 | 동일 |
| `APIFY_API_TOKEN` | GitHub Secret | TikTok + 팔로워 스크래핑용 |

---

## 오류 처리 원칙

| 상황 | 동작 |
|------|------|
| Apify 쿼터 초과 | `[WARN]` 출력 후 해당 소스 스킵, 나머지 계속 |
| Graph API 500 에러 | 10s → 20s retry → raise (Apify fallback 없음) |
| `us_data` 빈 경우 | `update_influencer_tracker` 스킵 (기존 데이터 보존) |
| 시트 API 쿼터 초과 | 예외 발생 → `continue-on-error: true` 스텝은 허용 |
| Syncly 마이그레이션 실패 | `continue-on-error: true` (비치명적) |

---

## 갱신 주기 및 캐시

- **GitHub Actions cache**: `tmp-state-${{ runner.os }}-` 키로 detection_log + prev_metrics 유지
- **Data Storage/apify/**: 날짜별 raw JSON 7일 artifact 보관
- **토큰 갱신**: `python tools/setup_ig_graph_token.py --token "..." --save`

---

## 한계 및 주의사항

1. **grosmimi_usa tagged**: Graph API 미수집 (FB 계정 분리). 실데이터 0.3% → 현재 무시
2. **Meta Graph Token 만료**: ~60일마다 수동 갱신 (자동화 미구현)
3. **Influencer Tracker**: 전체 재작성 방식 → 빈 데이터 가드로 보호 중
4. **JP TikTok**: 미수집 (JP 브랜드 TikTok 활동 없어 제외)
5. **Syncly vs Apify 갭**: Syncly-only 크리에이터 1명 (`@mebebun_uyentrang`) — 무시 가능 수준
