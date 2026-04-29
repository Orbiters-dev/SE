# Rakuten 주문처리 통합 워크플로우

## 목적

Rakuten 신규 주문이 들어오면 **RMS 주문확인 → 발송메일 → KSE 주문수집 + 옵션코드 → 배송접수 → 송장번호 Rakuten 기입**까지 한 번에 처리한다.

---

## 트리거

세은이 다음과 같이 말하면 즉시 실행:
- "쿠텐아 주문 들어왔다"
- "라쿠텐 주문 처리해"

**응답:** "네 주인님! 할 일을 하겠습니다" → 즉시 실행

---

## 전체 파이프라인

```
[Rakuten RMS]                          [KSE OMS]
注文確認待ち (100)
    ↓  Step 1: rakuten_order_confirm.py
発送待ち (300)
    ↓  Step 2: rakuten_ship_mail.py
発送済み (500)
                                        ↓  Step 3: KSE 주문수집(API) → rakuten_jp
                                        ↓  Step 4: 옵션코드 입력
                                        ↓  Step 5: 배송접수(국제)
                                        ↓  Step 6: 송장번호 확인
[Rakuten RMS]
    ↓  Step 7: 송장번호 기입 (주문 상세 페이지)
```

---

## 실행 순서

### Step 1: RMS 주문확인 (100 → 300)

```bash
python tools/rakuten_order_confirm.py --headed
```

- 注文確認待ち 주문 조회 → 주문확인 버튼 + サンクスメール 발송

### Step 2: RMS 발송메일 (300 → 500)

```bash
python tools/rakuten_ship_mail.py --headed
```

- 発送待ち 주문 조회 → メール送信 → 次へ → 本送信

### Step 3~5: KSE 주문수집 + 옵션코드 + 배송접수

```bash
python tools/kse_rakuten_order.py --headed
```

자동 처리:
1. KSE OMS 로그인
2. 주문수집(API) 페이지 직접 이동
3. 마켓: `rakuten_jp`, 계정: `라쿠텐JP` 선택
4. 날짜 설정 (화~금: 어제~오늘, 월: 금~오늘)
5. "주문서 가져오기" 클릭
6. **옵션코드 자동 입력** (상품명 → GROSMIMI 바코드 매핑)
7. 전체 선택 → **배송접수(국제)** 클릭

> **중요:** 옵션코드는 **배송접수 전에** 입력해야 함 (팩킹리스트 아님!)

### Step 6: 팩킹리스트 잔여 옵션코드 보정 (필요 시)

```bash
python tools/fill_kseoms_option_code.py --headed
```

- 배송접수 후 팩킹리스트에 옵션코드 빈 칸이 있으면 보정
- `gridCellUpdater` 호출로 AJAX 저장까지 자동 처리

### Step 2.5: 10분 대기

RMS 메일발송 완료 후 **10분 대기**. KSE에 주문이 반영되는 시간이 필요함.
세은 재트리거 없이 자동 진행.

### Step 7: 송장번호 → Rakuten RMS 입력

```bash
python tools/rakuten_tracking_input.py --headed
```

자동 처리:
1. KSE 팩킹리스트 → `LocalTrackingNo` (143516... JP Post 번호) 읽기
2. `packNo` 기준으로 RMS 주문번호와 매칭 (1주문 여러 아이템 → 1건 통합)
3. RMS 発送待ち → 각 주문 상세 진입
4. **配送会社: 日本郵便** 드롭다운 선택
5. **発送日: 今日** 클릭
6. **お荷物伝票番号: 송장번호** 입력 (input[name='parcelNumber'])
7. **「✔入力内容を反映」** 빨간 버튼 클릭

---

## 필요 환경변수

```
# Rakuten RMS
RAKUTEN_RMS_LOGIN_ID
RAKUTEN_RMS_LOGIN_PASSWORD
RAKUTEN_SSO_ID
RAKUTEN_SSO_PASSWORD

# KSE OMS
KSEOMS_LOGIN_ID
KSEOMS_LOGIN_PASSWORD
```

---

## 날짜 계산 로직

```python
from datetime import date, timedelta

today = date.today()
weekday = today.weekday()  # 0=월, 1=화, ..., 4=금

if weekday == 0:  # 월요일
    start_date = today - timedelta(days=3)  # 지난 금요일
else:  # 화~금
    start_date = today - timedelta(days=1)  # 어제
end_date = today
```

---

## 도구 현황

| Step | 도구 | 상태 |
|------|------|------|
| 1 | `rakuten_order_confirm.py --headed` | 완료 |
| 2 | `rakuten_ship_mail.py --headed` | 완료 |
| 3~5 | `kse_rakuten_order.py --headed` | 완료 |
| 6 | `fill_kseoms_option_code.py --headed` | 완료 (필요 시) |
| 7 | `rakuten_tracking_input.py --headed` | 완료 |

---

## 주의사항

- 모든 스크립트 `--headed`로 실행 (세은이 브라우저 확인)
- テンプレート 선택: 변경하지 않음 (기본값 유지)
- 옵션코드는 반드시 배송접수 **전에** 입력
- Amazon 주문은 마존이가 별도 처리 (주문등록 Excel 탭)
- **송장번호 입력은 배송접수 직후 바로 실행** (발송 후가 아님! 팩킹리스트 나오자마자 바로)
- **송장번호 입력(Step 7) 시 楽天処理中 상태인 주문은 skip** → 発送待ち 상태인 주문만 송장번호 입력 대상
- **dry-run → 실행을 브라우저 껐다 켜지 말 것** → 한 세션에서 확인 후 바로 실행
- **매 단계마다 세은에게 확인 묻지 말 것** → 에러 나면 알아서 고치고, 전체 완료 후 Teams로 결과 보고
- 진짜 판단 불가능한 경우에만 질문
- **RMS 메일발송 완료 후 10분 대기** → KSE에 주문 반영 시간 필요. 세은 재트리거 없이 자동 진행
- **전체 완료 후 TEAMS_WEBHOOK_URL_SEEUN으로 결과 전송** → 주문번호, 옵션코드, 송장번호 포함

---

## 주요 필드 매핑 (KSE ↔ RMS)

| KSE 필드 | 내용 | 비고 |
|----------|------|------|
| `packNo` | RMS 주문번호 (435776-XXXXXXXX-XXXXXXXXXX) | RMS 매칭 키 |
| `orderNo` | 라쿠텐 내부 주문번호 (숫자) | 참조용 |
| `LocalTrackingNo` | JP Post 송장번호 (143516...) | **RMS에 입력하는 송장** |
| `TrackingNo` | KSE 내부 트래킹 (K번호) | RMS용 아님 |
| `optionCode` | 바코드 옵션코드 | GROSMIMI 매핑 |

## RMS 송장입력 UI 요소

| 항목 | 셀렉터 |
|------|--------|
| 配送会社 | `select` → 日本郵便 옵션 |
| 発送日 | `a:has-text('今日')` or `button:has-text('今日')` |
| お荷物伝票番号 | `input[name='parcelNumber']` |
| 저장 | `button:has-text('入力内容')` (빨간 버튼) |

## Step 8b: 楽天処理中 미넘어옴 건 확인 (필수)

STEP 1에서 注文確認 + サンクスメール + 発送メール을 보낸 주문이 KSE에 안 잡혔거나 RMS 発送待ち로 안 넘어왔다면 → **반드시 楽天処理中 칸을 확인**한다.

**원인은 대부분 자동화 버그가 아니라 결제/유저 상태:**

| 注文情報 | 楽天からのお知らせ | 의미 | 우리 액션 |
|---------|-------------------|------|----------|
| 銀行振込 | (없음) | 은행입금 미입금 — 고객이 아직 입금 안 함 | **없음** (입금되면 자동 발송대기로 넘어옴) |
| コンビニ前払 | (없음) | 편의점 결제 미입금 — 최대 14일 대기 가능 | **없음** (입금 시 자동 전환) |
| クレジットカード | ユーザ対応待ち | 카드 결제 후 유저 대응 필요 (주소/인증 등) | **없음** (라쿠텐/유저가 처리) |

**확인 절차:**
1. RMS → 受注一覧 → 楽天処理中 탭으로 이동
2. STEP 1에서 처리한 주문번호 중 発送待ち로 안 넘어온 건을 찾는다
3. 注文情報 칸 + 楽天からのお知らせ 칸 확인
4. 위 표 기준으로 사유 분류

**보고 형식:**
> "OO건은 발송대기에서 확인이 안 되고 있는데, 라쿠텐 처리중 칸을 보니 [銀行振込 미입금 / ユーザ対応待ち / 등]인 것 같다."

**우리가 하지 말 것:** KSE 재실행, 옵션코드 강제 입력, RMS 송장 강제 등록 — 라쿠텐 자체가 처리 단계로 안 넘긴 거라 강제로 진행하면 데이터 깨짐.

---

## Step 9: Teams 알림 (자동)

전체 사이클 완료 후 `TEAMS_WEBHOOK_URL_SEEUN`으로 처리 결과 자동 전송.

```python
import os, json, urllib.request, ssl
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('TEAMS_WEBHOOK_URL_SEEUN')
msg = {'text': f'✅ 라쿠텐 주문 처리 완료\n\n주문번호: {주문번호}\n• 주문확인 ✓\n• メール ✓\n• KSE 옵션코드 ({코드}) ✓\n• 배송접수 ✓\n• 송장번호 ({송장}) ✓'}
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
req = urllib.request.Request(url, data=json.dumps(msg).encode(), headers={'Content-Type':'application/json'}, method='POST')
urllib.request.urlopen(req, context=ctx)
```

---

## 히스토리

- 2026-03-13: 최초 작성. RMS 주문확인 + 발송메일.
- 2026-03-13: KSE 주문수집 + 옵션코드 + 송장번호 파이프라인 추가.
- 2026-03-13: 옵션코드는 팩킹리스트가 아닌 배송접수 전 대기목록에서 입력으로 수정.
- 2026-03-16: Step 3~7 전체 자동화 완료. kse_rakuten_order.py + rakuten_tracking_input.py.
- 2026-03-16: 송장번호 = LocalTrackingNo (143516...), TrackingNo(K번호)는 KSE 내부용.
- 2026-03-16: RMS 저장 버튼 = 「✔入力内容を反映」빨간 버튼, packNo = RMS 주문번호.
- 2026-03-17: 송장번호는 배송접수 직후 바로 입력 (발송 후 아님). 楽天処理中 상태 skip 규칙 추가.
- 2026-03-17: 실행 방식 개선: dry-run/실행 분리 금지, 매 단계 확인 금지, 전체 완료 후 Teams 보고.
- 2026-03-20: RMS 메일발송 완료 후 10분 대기 → KSE 자동 진행 규칙 추가. 전체 완료 후 TEAMS_WEBHOOK_URL_SEEUN으로 결과 자동 전송.
- 2026-04-27: Step 8b 추가. 발송메일까지 보냈는데 発送待ち로 안 넘어온 건은 楽天処理中 칸 확인 필수 (대부분 銀行振込/コンビニ前払 미입금 또는 ユーザ対応待ち). 자동화 버그 아님 — 강제 진행 금지, 사유 정리 보고만.
