# Hydrogen/Remix Storefront Reference

Shopify Hydrogen은 Remix 기반 헤드리스 커머스 프레임워크다. 현재 프로젝트에서는 계획 단계이며 기존 구현은 없다.

## 기술 스택

| 패키지 | 용도 |
|--------|------|
| `@shopify/hydrogen` | 커머스 유틸리티, Cart API, Analytics |
| `@shopify/remix-oxygen` | Oxygen 배포 어댑터 |
| `@remix-run/react` | Remix 프레임워크 코어 |

## 핵심 개념

### Storefront API
고객 대면 데이터 접근용 GraphQL API. Admin API와 별도.

```graphql
query ProductQuery($handle: String!) {
  product(handle: $handle) {
    title
    description
    variants(first: 10) {
      nodes {
        id
        title
        price { amount currencyCode }
        availableForSale
      }
    }
    metafield(namespace: "onzenna_survey", key: "product_category") {
      value
    }
  }
}
```

### Loader/Action 패턴

```jsx
// app/routes/products.$handle.jsx

export async function loader({ params, context }) {
  const { product } = await context.storefront.query(PRODUCT_QUERY, {
    variables: { handle: params.handle },
  });
  if (!product) throw new Response("Not Found", { status: 404 });
  return json({ product });
}

export async function action({ request, context }) {
  const formData = await request.formData();
  // Cart 추가, 폼 제출 등
  const cart = context.cart;
  await cart.addLines([{ merchandiseId: formData.get("variantId"), quantity: 1 }]);
  return redirect("/cart");
}

export default function ProductPage() {
  const { product } = useLoaderData();
  return (
    <div>
      <h1>{product.title}</h1>
      {/* ... */}
    </div>
  );
}
```

### Cart API

```jsx
// context.cart 을 통한 장바구니 관리
const cart = context.cart;

// 추가
await cart.addLines([{ merchandiseId, quantity }]);

// 업데이트
await cart.updateLines([{ id: lineId, quantity: newQty }]);

// 삭제
await cart.removeLines([lineId]);
```

### Customer Account API

```jsx
// 고객 로그인/계정 관리
export async function loader({ context }) {
  const customer = await context.customerAccount.query(CUSTOMER_QUERY);
  return json({ customer });
}
```

## 메타필드 접근

Storefront API에서 메타필드 읽기:

```graphql
query CustomerMetafields {
  customer {
    metafield(namespace: "onzenna_survey", key: "journey_stage") {
      value
      type
    }
    metafields(identifiers: [
      { namespace: "onzenna_survey", key: "baby_birth_month" },
      { namespace: "onzenna_survey", key: "is_creator" }
    ]) {
      key
      value
    }
  }
}
```

메타필드 **쓰기**는 Storefront API에서 불가 — Admin API 또는 n8n webhook을 통해 처리.

## 라우팅 구조

```
app/
├── root.jsx                    # 최상위 레이아웃
├── entry.server.jsx            # 서버 엔트리
└── routes/
    ├── _index.jsx              # 홈페이지
    ├── products._index.jsx     # 상품 목록
    ├── products.$handle.jsx    # 상품 상세
    ├── collections.$handle.jsx # 컬렉션
    ├── cart.jsx                # 장바구니
    ├── account.jsx             # 고객 계정
    └── pages.$handle.jsx       # 커스텀 페이지
```

## 배포 옵션

| 플랫폼 | 특징 |
|--------|------|
| Oxygen (Shopify) | 네이티브 호스팅, 자동 CDN, 무료 |
| Vercel | Edge Functions, 빠른 배포 |
| Fly.io | Docker 기반, 글로벌 엣지 |

## Liquid vs Hydrogen 선택 기준

| 기준 | Liquid 테마 | Hydrogen |
|------|------------|----------|
| 커스터마이징 | 테마 제약 내 | 완전 자유 |
| 성능 | 서버 렌더링 (Shopify CDN) | SSR + Edge (최적화 가능) |
| 개발 복잡도 | 낮음 (HTML/CSS/JS) | 높음 (React/Remix) |
| SEO | 기본 지원 | 직접 구현 |
| 유지보수 | 테마 업데이트 자동 | 직접 관리 |
| 적합한 경우 | 표준 스토어 | 고도로 커스텀된 경험 |

이 프로젝트에서는 대부분의 페이지가 Liquid 테마로 충분하다. Hydrogen은 고도로 인터랙티브한 경험(개인화된 제품 추천, 실시간 데이터 대시보드 등)이 필요할 때 도입을 검토한다.
