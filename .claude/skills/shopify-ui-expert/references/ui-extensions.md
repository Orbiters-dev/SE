# Checkout UI Extensions Reference

Shopify Checkout UI Extensions는 `@shopify/ui-extensions-react/checkout` 패키지 기반 React 컴포넌트다. 체크아웃과 감사 페이지에 커스텀 UI를 삽입한다.

## 프로젝트 구조

```
onzenna-survey-app/
├── shopify.app.toml                   # 앱 설정 (OAuth scopes, webhooks)
├── package.json
└── extensions/
    ├── onzenna-checkout-survey/
    │   ├── shopify.extension.toml     # Extension 설정
    │   └── src/Checkout.jsx           # 체크아웃 설문 (Q4~Q7)
    └── onzenna-thankyou-survey/
        ├── shopify.extension.toml
        └── src/ThankYou.jsx           # 크리에이터 폼 + 로열티 CTA
```

## Extension Targets

| Target | 위치 | 현재 사용 |
|--------|------|----------|
| `purchase.checkout.contact.render-after` | 체크아웃 연락처 아래 | Checkout.jsx |
| `purchase.thank-you.block.render` | 감사 페이지 블록 | ThankYou.jsx |
| `purchase.checkout.block.render` | 체크아웃 블록 (범용) | 미사용 |
| `customer-account.order-status.block.render` | 고객 계정 주문 상태 | 미사용 |

## shopify.extension.toml 구조

```toml
api_version = "2024-10"

[[extensions]]
name = "Extension Display Name"
handle = "extension-handle"
type = "ui_extension"

[[extensions.targeting]]
module = "./src/Component.jsx"
target = "purchase.checkout.contact.render-after"

[extensions.capabilities]
api_access = true          # Shopify API 접근 허용
network_access = true      # 외부 네트워크 (webhook 등) 허용

[extensions.settings]
  [[extensions.settings.fields]]
  key = "setting_key"
  type = "single_line_text_field"
  name = "Setting Name"
  description = "설정 설명"

# 메타필드 접근 선언 (읽기/쓰기 모두 여기에 선언 필요)
[[extensions.metafields]]
namespace = "onzenna_survey"
key = "field_name"
```

새 메타필드를 추가할 때는 반드시 `shopify.extension.toml`의 `[[extensions.metafields]]`에도 선언해야 한다.

## Component API

### Layout
| 컴포넌트 | 용도 |
|---------|------|
| `BlockStack` | 수직 레이아웃 (spacing: "none", "extraTight", "tight", "base", "loose") |
| `InlineStack` | 수평 레이아웃 |
| `Divider` | 구분선 |

### Typography
| 컴포넌트 | 용도 |
|---------|------|
| `Heading` | 제목 (level: 1~3) |
| `Text` | 본문 (size: "small", "base", "large"; appearance: "subdued", "critical") |

### Form
| 컴포넌트 | 용도 |
|---------|------|
| `Select` | 드롭다운 (label, options: [{value, label}], onChange) |
| `TextField` | 텍스트 입력 (label, placeholder, onChange) |
| `Checkbox` | 체크박스 (children으로 라벨, onChange(boolean)) |
| `Button` | 버튼 (kind: "primary"/"secondary", onPress, loading, disabled) |

### Feedback
| 컴포넌트 | 용도 |
|---------|------|
| `Banner` | 알림 배너 (status: "info", "success", "warning", "critical") |
| `Link` | 링크 (to: URL) |

## Hooks

### useApplyMetafieldsChange
주문 메타필드에 데이터를 저장한다. 체크아웃 중에는 customer metafield에 직접 쓸 수 없고, order metafield에 기록된다. 이후 n8n이 customer metafield로 동기화한다.

```jsx
const applyMetafieldsChange = useApplyMetafieldsChange();

applyMetafieldsChange({
  type: "updateMetafield",
  namespace: "onzenna_survey",
  key: "journey_stage",
  valueType: "string",    // "string" | "json" | "integer"
  value: selectedValue,
});
```

### useMetafield
기존 메타필드 값을 읽는다. 반환 시 `existingMf?.value`로 접근.

```jsx
const existingSignup = useMetafield({
  namespace: "onzenna_survey",
  key: "signup_completed_at",
});
if (existingSignup?.value) { /* 이미 설문 완료 */ }
```

### useCustomer
로그인된 고객 정보. 게스트 체크아웃에서는 null.

### useOrder
감사 페이지에서 주문 정보 접근. `order.id`, `order.customer.id`, `order.metafields`.

### useSettings
`shopify.extension.toml`의 `[extensions.settings]`에서 정의한 설정값 읽기.

```jsx
const settings = useSettings();
const webhookUrl = settings?.n8n_webhook_url;
```

## 데이터 전송 패턴

### 패턴 1: 메타필드 쓰기 (체크아웃)
체크아웃 중 폼 값 → `useApplyMetafieldsChange` → Order Metafield 저장. 별도 네트워크 호출 불필요.

### 패턴 2: Webhook POST (감사 페이지)
감사 페이지에서 크리에이터 프로필 같은 복잡한 데이터를 n8n webhook으로 전송.

```jsx
const payload = {
  form_type: "onzenna_creator_survey",
  order_id: order?.id,
  customer_id: order?.customer?.id,
  submitted_at: new Date().toISOString(),
  creator_data: { /* ... */ },
};

await fetch(webhookUrl, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});
```

## 새 Extension 추가 체크리스트

1. `onzenna-survey-app/extensions/` 아래 새 디렉토리 생성
2. `shopify.extension.toml` 작성 (target, capabilities, metafields)
3. `src/Component.jsx` 작성 (필요한 컴포넌트 import)
4. 메타필드 접근이 필요하면 toml에 `[[extensions.metafields]]` 선언
5. webhook이 필요하면 `[extensions.settings]`에 URL 필드 추가, `[extensions.capabilities]`에 `network_access = true`
6. `shopify app dev` 로 로컬 프리뷰
7. Bogus Gateway로 테스트 주문 생성
8. `shopify app deploy` 로 프로덕션 배포

## 조건부 렌더링 패턴

기존 메타필드 값에 따라 다른 UI를 보여주는 패턴:

```jsx
// 반환 고객이면 설문 숨기기
if (existingSignup?.value) {
  return <Text>Welcome back!</Text>;
}

// 크리에이터 여부에 따라 분기
{isCreator ? <CreatorForm /> : <LoyaltyCTA />}
```

## 상태 관리

- 간단한 폼: 클로저 변수 (`let selectedMonth = ""`)
- 제출 상태 추적: `useState` (`submitted`, `submitting`)
- 복합 상태: `useState` 객체 (`contentTypes: { reviews: false, ... }`)

Checkout Extension 환경에서는 외부 상태 관리 라이브러리(Redux, Zustand 등) 사용이 제한된다. React의 기본 `useState`로 충분하다.
