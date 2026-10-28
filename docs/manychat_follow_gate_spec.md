# ManyChat 팔로우 게이트 플로우 설계서

**작성일**: 2026-04-20
**담당**: 리공이 (n8n/API 파트) + 세은 (ManyChat Dashboard 세팅)
**상태**: 설계 완료, 세은 확인 필요

---

## 1. 목표 플로우

```
[IG 피드 포스트 코멘트에 「マグ」 작성]
                ↓
      ManyChat Comment Keyword Trigger
                ↓
        팔로우 상태 분기
        ┌───────┴───────┐
      팔로워            비팔로워
        ↓                 ↓
   쿠폰+라쿠텐       안내 DM + Quick Reply
   DM 즉시 발송      [👆 フォローしました]
                           ↓ 버튼 탭
                      팔로우 상태 재확인
                      ┌─────┴─────┐
                  팔로워          미확정
                      ↓               ↓
                 쿠폰 DM         재안내 루프
```

---

## 2. 기술 검증 결과 (재확인 2026-04-20)

### ✅ 확인된 인프라
| 항목 | 상태 |
|------|------|
| ManyChat API 연결 | 정상 (LITTLEFINGERUSA 楽天市場店 워크스페이스) |
| ManyChat 플랜 | **Pro** (is_pro: true) — Instagram Automation 가능 |
| Instagram Graph API | 환경변수 존재 (IG_USER_ID, IG_ACCESS_TOKEN) |
| n8n 워크플로우 | `fsrnGT7aPn5jfVQ5m7I8C` (Orbiters: ManyChat Automation) — 63 노드 |

### ✅ ManyChat "Check Follower" 기능 (재확인)
- ManyChat Community 공식 문서 확인: **"Follows your Account" 조건 / Check Follower 기능 존재**
- Comment Reply Flow에서 팔로우 여부를 실시간 분기 조건으로 사용 가능
- 구현 방식: IG 공식 API가 아니라 ManyChat 내부 스크래핑 — 공식은 아니지만 **실제 작동함**
- 많은 일본/글로벌 IG 계정이 이 방식으로 "follow-gated coupon" 운영 중

### ⚠️ 잔여 한계 (참고)
1. ManyChat 스크래핑 기반이라 Meta가 제재할 가능성 존재 (장기적 리스크)
2. 팔로우 직후 체크 타이밍에 따라 최대 수 초~수십 초 지연 가능 (실시간에 가까움, 폴링 5~10분이 아님)

### ✅ 실제로 동작 가능한 구조
- ManyChat **Comment Keyword Trigger** ✅
- ManyChat **"Follows your Account" 조건 분기** ✅
- ManyChat **Tag 기반 상태 관리** ✅
- ManyChat **Custom Field로 쿠폰 발급 로그** ✅
- n8n **External Request**로 쿠폰 코드 동적 발급 ✅

---

## 3. ManyChat Dashboard 세팅 (세은 or Playwright 대행)

### Step 1. Instagram Automation → Comments

1. 새 Automation 생성
2. Trigger: **Specific Post Comment** (처음엔 특정 포스트만, 나중에 전체 확장)
3. Keyword: `マグ` (포함 매칭)
4. First Action: **Send Message in DM**

### Step 2. DM 첫 응답 분기 ("Follows your Account" 조건 사용)

ManyChat Custom Fields:
- `coupon_sent` (Boolean) — 이미 쿠폰 받은 유저 재발송 방지
- `last_coupon_code` (Text) — 발급된 쿠폰 코드 저장

분기 조건 (ManyChat 내장 조건 사용):
```
IF coupon_sent == true
  → "既にクーポン送信済みです🤍 またのご参加お待ちしてます！"

ELSE IF [Follows your Account == YES]
  → 쿠폰 DM 발송 (Step 3으로)

ELSE (비팔로워)
  → 팔로우 유도 DM (Step 4로) + 팔로우 감지 대기
```

### Step 3. 팔로워 대상 쿠폰 DM

```
[그로스미미 JP 감사 메시지]

コメントありがとうございます🤍
楽天の限定クーポン、お届けします🎁

▼ クーポンコード
{{last_coupon_code}}  ← n8n External Request로 동적 발급

▼ 商品ページ
{{rakuten_product_url}}

*クーポンは○月○日まで有効です
```

Action: Set `coupon_sent = true`

### Step 4. 비팔로워 대상 팔로우 유도 DM

```
はじめまして🤍

グロミミの限定クーポンは
フォロワー様限定でお届けしています✨

@grosmimi_japan をフォローいただけると、
自動でクーポンお届けします🎁

＊フォロー後、数秒〜数十秒で届きます
```

버튼 없이 단순 안내 + ManyChat의 Check Follower가 유저 팔로우 상태를 감지하는 순간 자동으로 Step 3 실행.

### Step 5. 재발송 방지
- Step 3 실행 시 Set `coupon_sent = true`
- 동일 유저 재트리거 시 Step 2에서 차단

---

## 4. n8n 서브 워크플로우 (리공이 담당)

### 4-1. 새 워크플로우: `IG Coupon Dispatcher`

- **목적**: ManyChat External Request로 호출되어 쿠폰 코드 동적 발급 + 로그
- **Webhook**: `POST /ig-coupon-dispatch`
- **처리**:
  1. subscriber_id + handle 수신
  2. 현재 발급 가능한 쿠폰 풀에서 하나 pick (또는 고정 코드)
  3. 라쿠텐 상품 URL 생성 (affiliate 트래킹 포함 시)
  4. 발급 이력 저장 (staticData)
  5. 응답: `{coupon_code, rakuten_url, message}`

### 4-2. 새 워크플로우: `IG Coupon Audit`

- **목적**: 24h 후 pending 유저 정리 + 팔로우 안 한 버튼 탭 유저 감사
- **Trigger**: 스케줄 (매 1시간)
- **처리**: 24h 초과 pending → 태그 해제

### 4-3. 초기 상태
- 두 워크플로우 모두 **비활성화(active=false)** 로 저장
- 세은 확인 후 실제 쿠폰 코드/URL 넣고 publish

---

## 5. 테스트 절차 (세은용)

1. 세은 **서브 IG 계정**으로 ManyChat 연동 피드 포스트 찾기
2. 해당 포스트에 댓글 `マグ` 달기
3. DM 수신 확인:
   - 팔로워 서브 계정 → 즉시 쿠폰 DM 예상
   - 비팔로워 서브 계정 → 안내 DM + 버튼 예상
4. 비팔로워 → 서브 계정 팔로우 → `[👆 フォローしました]` 탭
5. 쿠폰 DM 재발송 확인
6. 동일 계정 재시도 → `既にクーポン送信済み` 응답 확인 (재발송 방지)
7. 문제 없으면 세은 메인 계정으로 publish

---

## 6. 세은 확인 필요 4대 항목

| # | 항목 | 현재 상태 | 세은 답변 필요 |
|---|------|----------|----------------|
| 1 | **라쿠텐 쿠폰 코드** | 미확인 | 실제 발급 가능 여부, 할인율(%), 유효기간 |
| 2 | **라쿠텐 랜딩 URL** | 미확인 | 상품 페이지 / 브랜드 스토어 / 이벤트 페이지 중 선택 |
| 3 | **ManyChat OAuth 연결** | 확인 (LITTLEFINGERUSA 워크스페이스) — @grosmimi_japan IG 별도 확인 필요 | @grosmimi_japan이 이 워크스페이스에 이미 연결되어 있는지 |
| 4 | **Instagram Professional Account** | 미확인 | @grosmimi_japan이 Professional/Creator 계정 상태인지 (ManyChat 요구사항) |

---

## 7. 리공이 작업 완료 / 세은 대기

**완료:**
- 인프라 진단
- 플로우 설계
- n8n 서브 워크플로우 계획
- 테스트 절차 문서화
- 본 설계서 작성

**대기 (세은 답변 후 착수):**
- n8n 서브 워크플로우 실제 생성 (비활성화)
- ManyChat Dashboard Flow 구성 (Playwright 대행 또는 세은 직접)
- 실제 쿠폰 코드/URL 주입
- 테스트 + publish

---

## 8. 대안 시나리오 (honor system 안 쓸 경우)

만약 세은이 "버튼 신뢰 기반"이 찝찝하다고 하면:

**Option A**: 쿠폰 사용 시점 검증
- 쿠폰 발급은 누구나 OK
- 라쿠텐 주문 시 "IG 팔로우 유저만 유효" 조건 → 라쿠텐측 검증
- 문제: 구현 복잡, 라쿠텐 기능 확인 필요

**Option B**: 재댓글 요구
- 팔로우 후 **다른 키워드**(예: `クーポン希望`)로 재댓글 요구
- UX 덜 깔끔하지만 확실한 engagement 신호

**Option C**: 수동 승인
- 비팔로워 유저 → Teams 알림 → 세은이 수동으로 팔로우 확인 후 발송
- 소량일 때만 가능
