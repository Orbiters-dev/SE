# Workflow: ManyChat IG 댓글 → 팔로우 게이트 → 쿠폰 DM

**목적:** Instagram 피드 포스트 댓글에 특정 키워드를 단 유저에게, 팔로우 상태를 확인하고 라쿠텐 쿠폰+링크를 DM으로 자동 발송한다.

**담당:** 리공이 (n8n + API) + 세은 (ManyChat Dashboard 실제 세팅 / 쿠폰·URL 주입)

**관련 스킬:** `리공이` (n8n, DocuSeal), `인획이` (IG 기획)

---

## 1. 플로우 개요

```
[IG 피드 포스트 코멘트에 「{키워드}」 작성]
                ↓
      ManyChat Comment Keyword Trigger
                ↓
        "Follows your Account?" 조건 분기
        ┌───────┴───────┐
      팔로워            비팔로워
        ↓                 ↓
   쿠폰+라쿠텐       팔로우 유도 DM
   DM 즉시 발송      (팔로우 감지되면 자동 발송)
```

---

## 2. 전제 조건 (시작 전 체크리스트)

| # | 항목 | 확인 방법 | 상태 |
|---|------|----------|------|
| 1 | ManyChat Pro 플랜 | `curl /fb/page/getInfo` → `is_pro: true` | ✅ 확인 |
| 2 | 타깃 IG 계정 Professional/Creator 계정 | ManyChat 워크스페이스 연결 여부 = Pro 계정 확정 | ✅ 확인 |
| 3 | IG 계정 ManyChat 워크스페이스 연결 | ManyChat Dashboard → Settings → Channels | ✅ 확인 |
| 4 | 라쿠텐 쿠폰 코드 | 세은이 발급 (할인율/유효기간 지정) | ⚪ 매번 확인 |
| 5 | 라쿠텐 랜딩 URL | 상품 페이지 / 브랜드 스토어 / 이벤트 중 선택 | ⚪ 매번 확인 |

---

## 3. ManyChat Dashboard 세팅 (Flow Builder)

### 3-1. Custom Fields 생성
- `coupon_sent` (Boolean) — 재발송 방지
- `last_coupon_code` (Text) — 발급 코드 저장
- `last_coupon_campaign` (Text) — 어느 포스트/캠페인에서 받았는지

### 3-2. Automation > Instagram Comments > New Trigger
- **Trigger**: Specific Post Comment (또는 전체)
- **Keyword 매칭**: `{키워드}` (예: `マグ`, `クーポン`, 제품명 등)
- **매칭 방식**: Contains (변형 허용)

### 3-3. Flow 분기 설계

```
[Keyword 감지]
  ↓
Condition: coupon_sent == true?
  ├ YES → DM "既にクーポン送信済みです🤍" → End
  └ NO ↓
Condition: Follows your Account?
  ├ YES → Go to "Send Coupon DM"
  └ NO  → Go to "Follow Request DM" → (wait for follow detection) → Go to "Send Coupon DM"
```

### 3-4. Send Coupon DM 템플릿

```
コメントありがとうございます🤍
楽天の限定クーポン、お届けします🎁

▼ クーポンコード
{{last_coupon_code}}

▼ 商品ページ
{{RAKUTEN_URL}}

＊クーポンは{{VALID_UNTIL}}まで有効です
```

**Action 순서:**
1. External Request → n8n `/ig-coupon-dispatch` (쿠폰 코드 + 라쿠텐 URL 수신)
2. Set `last_coupon_code = response.coupon_code`
3. Send DM (위 템플릿, 변수 치환)
4. Set `coupon_sent = true`
5. Add Tag: `coupon_{{campaign_id}}`

### 3-5. Follow Request DM 템플릿

```
はじめまして🤍

グロミミの限定クーポンは
フォロワー様限定でお届けしています✨

@{{IG_HANDLE}} をフォローいただけると、
自動でクーポンお届けします🎁

＊フォロー後、数秒〜数十秒で届きます
```

**Action:** 그 다음 Smart Delay (5~10 sec) → Re-check "Follows your Account?" → YES면 쿠폰 DM, NO면 대기 continue.

---

## 4. n8n 서브 워크플로우 (리공이 담당)

### 4-1. `IG Coupon Dispatcher` (신규 생성 예정)
- **Webhook:** `POST /ig-coupon-dispatch`
- **입력:** `{subscriber_id, ig_handle, campaign_id}`
- **처리:**
  1. 쿠폰 풀에서 1개 pick (또는 고정 코드)
  2. 라쿠텐 URL (affiliate 트래킹 옵션)
  3. 발급 이력 저장 (staticData)
- **출력:** `{coupon_code, rakuten_url, valid_until}`
- **초기 상태:** `active=false` (세은 값 주입 후 활성화)

### 4-2. `IG Coupon Audit` (선택)
- **스케줄:** 매 1시간
- **처리:** 24h 초과 pending 유저 태그 해제, 쿠폰 사용률 로깅

---

## 5. 테스트 절차 (세은)

1. ManyChat Flow를 **비활성화(unpublished) 상태로 저장**
2. 세은 **서브 IG 계정**으로 해당 포스트에 `{키워드}` 댓글
3. DM 수신 확인:
   - 팔로워 서브 → 즉시 쿠폰 DM
   - 비팔로워 서브 → 팔로우 안내 DM → 팔로우 후 수 초 내 쿠폰 자동 발송
4. 동일 계정 재시도 → `既に送信済み` 응답 확인
5. 문제 없으면 **Publish** → 메인 포스트에 적용

---

## 6. 매 캠페인 운영 시 체크리스트 (반복 사용)

| # | 단계 | 담당 |
|---|------|------|
| 1 | 라쿠텐 쿠폰 코드 발급 | 세은 |
| 2 | 라쿠텐 랜딩 URL 결정 | 세은 |
| 3 | ManyChat External Request JSON 업데이트 (코드+URL) | 리공이 |
| 4 | 해당 포스트 Trigger 등록 (Specific Post) | 리공이 or 세은 (ManyChat UI) |
| 5 | 서브 계정 테스트 | 세은 |
| 6 | Publish | 세은 |
| 7 | 24~48h 후 사용률 확인 | 리공이 |

---

## 7. 한계 & 리스크

| 항목 | 설명 | 완화책 |
|------|------|--------|
| 스크래핑 기반 | ManyChat의 "Follows your Account"는 IG 공식 API 아닌 자체 스크래핑 | 다수 계정이 오래 쓰고 있어 안정적. Meta 정책 변동 주시 |
| Meta 메시징 정책 | "팔로우 강제" 표현 금지 | 톤 완곡: "フォローいただけると" |
| 쿠폰 중복 발급 | 동일 유저 여러 포스트에서 받을 수 있음 | `coupon_sent` Boolean + 캠페인별 태그로 제어 |

---

## 8. 참고 자료

- 설계서 원본: `docs/manychat_follow_gate_spec.md` (이 workflow로 병합됨)
- ManyChat Community: "Follows your Account" 조건 공식 사용 사례
- 리공이 스킬: `.claude/skills/리공이/SKILL.md`
