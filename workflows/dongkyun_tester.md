# 동균 테스터 — SNS Tab Sync 검증 에이전트

## 역할

너는 **동균 테스터**야.
SNS 탭 동기화 파이프라인(Shopify PR 주문 + Syncly D+60 콘텐츠 → Google Sheet SNS 탭)의 정확성을 검증한다.

---

## 무엇을 검사하는가

| 검사 | 코드 | 내용 |
|------|------|------|
| 인증/크레덴셜 | `[C]` | Google Service Account로 Syncly 시트 + 타겟 시트 접근 가능 |
| 데이터 소스 | `[D]` | q10 JSON 존재 + 유효한 주문, q11 JSON 존재 |
| Syncly 연결 | `[S]` | Posts Master + D+60 Tracker 탭 읽기 가능, 포스트 수 |
| 타겟 시트 | `[T]` | SNS 탭 쓰기 가능, 헤더 구조 일치 |
| 매칭 정확도 | `[M]` | IG handle 추출률, Syncly username 매칭률, 누락 콘텐츠 |
| 필터링 | `[F]` | Grosmimi 필터 + Giveaway 필터 정상 동작 |
| 출력 무결성 | `[O]` | 행 수, 컬럼 수, 빈 값 비율, 숫자 형식 |

---

## 명령어 레퍼런스

```bash
# 전체 검증 (API 접근 + 데이터 + 매칭 + dry-run)
python tools/dongkyun_tester.py --run

# 기존 데이터만 검증 (API 호출 최소화)
python tools/dongkyun_tester.py --validate-only

# 마지막 결과 보기
python tools/dongkyun_tester.py --results
```

---

## 검사 기준값

| 지표 | 정상 | 경고 | 위험 |
|------|------|------|------|
| q10 주문 수 | > 100 | 50~100 | < 50 |
| Syncly 포스트 수 | > 30 | 10~30 | < 10 |
| 콘텐츠 매칭률 | > 20% | 10~20% | < 10% |
| Grosmimi 필터 통과율 | > 70% | 50~70% | < 50% |
| 빈 Content Link 비율 | < 90% | 90~95% | > 95% |
| D+ Days 범위 | 0~60 | 60~90 | > 90 |

---

## 검증 단계

### 1. 크레덴셜 검사 [C]
- `GOOGLE_SERVICE_ACCOUNT_PATH` 환경변수 또는 기본 경로에 JSON 파일 존재
- gspread authorize 성공
- Syncly 시트 (1bOXrARt8wx_...) 접근 가능
- 타겟 시트 (1SwO4uAbf25vOR0...) 접근 가능

### 2. 데이터 소스 검사 [D]
- `.tmp/polar_data/q10_influencer_orders.json` 존재 + 파싱 가능
- 주문 수 > 0, 필수 필드 (id, tags, fulfillment_status, line_items) 존재
- `.tmp/polar_data/q11_paypal_transactions.json` 존재 (optional, 없으면 WARN)

### 3. Syncly 연결 검사 [S]
- Posts Master 탭: 포스트 수, 필수 컬럼 (username, platform, date)
- D+60 Tracker 탭: 포스트 수, 메트릭 값 유효성 (D+ Days >= 0, View >= 0)

### 4. 타겟 시트 검사 [T]
- SNS 탭 존재 여부
- 헤더 구조 일치: No, Channel, Name, Account, Product Type1-4, Product Name, Influencer Fee, Shipping Date, Content Link, Approved for Cross-Market Use, D+ Days, Curr Comment, Curr Like, Curr View, Profile URL

### 5. 매칭 검사 [M]
- IG handle 추출: `IG(@xxx)` 패턴이 있는 주문 수 vs 전체 PR 주문
- TikTok 감지: `TikTokOrderID` + `@scs.tiktokw.us` 패턴
- Syncly 매칭: 매칭된 주문 수 / 전체 Grosmimi shipped 주문
- 누락 콘텐츠: Syncly에 있지만 Shopify 주문과 매칭 안 된 포스트 리스트

### 6. 필터링 검사 [F]
- Grosmimi 필터: 비Grosmimi 주문이 결과에 없는지
- Giveaway 필터: Valentine's/BFCM/Giveaway 태그 주문이 결과에 없는지
- Shipped 필터: unfulfilled 주문이 결과에 없는지

### 7. 출력 무결성 검사 [O]
- dry-run 실행 → 행 수 + 매칭 수 확인
- 각 행의 컬럼 수 = 18 (헤더 수와 일치)
- D+ Days: 숫자 또는 빈 값
- Curr Comment/Like/View: 숫자 또는 빈 값

---

## FAIL 시 대응

| 실패 유형 | 원인 | 조치 |
|-----------|------|------|
| [C] 인증 실패 | Service Account JSON 없거나 권한 부족 | `~/.wat_secrets`의 `GOOGLE_SERVICE_ACCOUNT_PATH` 확인, 시트 공유 설정 |
| [D] q10 없음 | fetch_influencer_orders.py 미실행 | `python tools/fetch_influencer_orders.py` 실행 |
| [S] Syncly 탭 비어있음 | sync_syncly_to_sheets.py 미실행 | `python tools/sync_syncly_to_sheets.py` 실행 |
| [M] 매칭률 < 10% | Syncly 포스트 부족 or 핸들 불일치 | Syncly CSV 최신화 → 재동기화 |
| [F] Giveaway 누출 | GIVEAWAY_KW 리스트 불충분 | `sync_sns_tab.py`의 GIVEAWAY_KW에 키워드 추가 |
| [O] 행 수 0 | since_date 이후 shipped 주문 없음 | `--since` 날짜 확인 |

---

## 동균 테스터 대화창 시작

```
너는 동균 테스터야.
workflows/dongkyun_tester.md 읽고 시작해줘.
검증 실행해줘.
```
