# Polaris Admin App Reference

Shopify Admin에 임베딩되는 React 앱을 위한 개발 가이드. 현재 프로젝트에서는 설계 단계이며 기존 구현은 없다.

## 기술 스택

| 패키지 | 용도 |
|--------|------|
| `@shopify/polaris` | UI 컴포넌트 라이브러리 |
| `@shopify/app-bridge-react` | Admin 임베딩 |
| `@shopify/shopify-app-remix` | Remix 기반 앱 프레임워크 |

## 핵심 컴포넌트

### Layout
- `Page` — 최상위 페이지 레이아웃 (title, primaryAction, secondaryActions)
- `Layout` — 2/3 + 1/3 또는 50/50 등 컬럼 레이아웃
- `Card` — 콘텐츠 그룹 (sectioned)
- `Frame` — 앱 전체 프레임 (navigation, topBar)

### Data Display
- `DataTable` — 테이블 (columnContentTypes, rows, sortable)
- `ResourceList` — 리소스 목록 (items, renderItem)
- `IndexTable` — 대량 데이터 테이블 (bulk actions 지원)
- `Badge` — 상태 뱃지 (status: "success", "warning", "critical", "attention")

### Forms
- `FormLayout` — 폼 레이아웃
- `TextField` — 텍스트 입력
- `Select` — 드롭다운
- `Checkbox` — 체크박스
- `DatePicker` — 날짜 선택
- `DropZone` — 파일 업로드

### Feedback
- `Banner` — 알림 배너
- `Toast` — 일시적 알림
- `Modal` — 모달 다이얼로그
- `SkeletonPage` / `SkeletonBodyText` — 로딩 스켈레톤

### Navigation
- `NavigationMenu` (App Bridge) — 좌측 네비게이션
- `Tabs` — 탭 네비게이션
- `Pagination` — 페이지네이션

## App Bridge 통합

```jsx
import { AppProvider } from "@shopify/shopify-app-remix/react";

function App() {
  return (
    <AppProvider isEmbeddedApp apiKey={API_KEY}>
      <Page title="Dashboard">
        <Layout>
          <Layout.Section>
            <Card>
              {/* 메인 콘텐츠 */}
            </Card>
          </Layout.Section>
          <Layout.Section variant="oneThird">
            <Card>
              {/* 사이드바 */}
            </Card>
          </Layout.Section>
        </Layout>
      </Page>
    </AppProvider>
  );
}
```

## 인증 패턴

기존 `tools/shopify_oauth.py` 패턴을 재사용:

```python
# OAuth 토큰 관리
SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
```

Admin 앱에서는 Shopify App 인증 흐름(OAuth 2.0)을 통해 세션 기반 인증을 사용한다.

## Admin API 호출

```jsx
// GraphQL (권장)
const response = await admin.graphql(`
  query {
    customers(first: 10) {
      edges {
        node {
          id
          displayName
          email
          metafield(namespace: "onzenna_survey", key: "journey_stage") {
            value
          }
        }
      }
    }
  }
`);

// REST (기존 도구 호환)
const response = await fetch(`/admin/api/2024-01/customers.json`, {
  headers: { "X-Shopify-Access-Token": TOKEN }
});
```

## 사용 시나리오

이 프로젝트에서 Polaris Admin 앱이 유용한 경우:
- 인플루언서 기프팅 신청 관리 대시보드
- 크리에이터 프로필 검토/승인 UI
- 설문 응답 통계 대시보드
- 메타필드 일괄 편집 도구
- 고객 RFM 세그먼트 시각화

## 개발 환경 셋업

```bash
# Shopify CLI로 앱 생성
shopify app init --template remix
cd my-admin-app

# 개발 서버
shopify app dev

# 배포
shopify app deploy
```

## UI Extension vs Admin App 선택 기준

| 기준 | UI Extension | Admin App |
|------|-------------|-----------|
| 위치 | 체크아웃/감사/계정 페이지 | Admin 내부 |
| 사용자 | 고객 (buyer) | 운영팀 (staff) |
| 데이터 | 고객 입력 수집 | 내부 데이터 조회/관리 |
| 복잡도 | 단순 폼/설문 | 대시보드/CRUD |
| API | 제한적 (확장 API만) | 전체 Admin API |
