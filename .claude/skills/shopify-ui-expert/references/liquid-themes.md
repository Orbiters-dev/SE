# Liquid Theme Pages Reference

Python 스크립트로 Liquid 섹션과 JSON 템플릿을 Shopify Theme Asset API에 업로드하여 커스텀 페이지를 생성한다.

## Deploy 스크립트 구조

모든 deploy 스크립트가 동일한 패턴을 따른다:

```python
"""Deploy [페이지명] to Shopify.
Usage:
    python tools/deploy_[name].py
    python tools/deploy_[name].py --dry-run
    python tools/deploy_[name].py --unpublish
    python tools/deploy_[name].py --rollback
"""

import os, sys, json, argparse, urllib.request, urllib.error
from env_loader import load_env

load_env()
SHOP = os.getenv("SHOPIFY_SHOP", "mytoddie.myshopify.com")
TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"

# 업로드할 asset 키
SECTION_KEY = "sections/page-name.liquid"
TEMPLATE_KEY = "templates/page.page-name.json"
PAGE_HANDLE = "page-name"
PAGE_TITLE = "Page Title"
```

## Shopify API 헬퍼 함수

모든 deploy 스크립트에서 공유하는 4개 핵심 함수:

```python
def shopify_request(method, path, data=None):
    """Shopify Admin REST API 호출"""
    url = f"https://{SHOP}/admin/api/{API_VERSION}{path}"
    # urllib.request 기반, X-Shopify-Access-Token 헤더

def get_active_theme_id():
    """GET /themes.json → role == 'main' 인 테마 ID"""

def upload_theme_asset(theme_id, key, value):
    """PUT /themes/{id}/assets.json"""

def delete_theme_asset(theme_id, key):
    """DELETE /themes/{id}/assets.json?asset[key]={key}"""

def create_or_update_page(handle, title, template_suffix, published=True):
    """GET /pages.json?handle={handle} → 있으면 PUT, 없으면 POST"""
```

## Liquid 섹션 빌드 패턴

```python
def build_section_liquid(webhook_url):
    return f"""
<div class="pfx-container">
  <style>
    .pfx-container {{ max-width: 720px; margin: 0 auto; padding: 24px 16px; }}
    .pfx-field {{ margin-bottom: 16px; }}
    .pfx-field label {{ display: block; font-weight: 600; margin-bottom: 4px; }}
    .pfx-field input, .pfx-field select {{ width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 6px; }}
    @media(max-width:768px) {{ .pfx-row {{ flex-direction: column; }} }}
  </style>

  {{% if customer %}}
    <script>
      // 로그인 고객 정보로 폼 프리필
      var customerEmail = "{{{{ customer.email }}}}";
      var customerName = "{{{{ customer.first_name }}}} {{{{ customer.last_name }}}}";
    </script>
  {{% endif %}}

  <form id="pfx-form">
    <!-- 폼 필드 -->
  </form>

  <script>
    document.getElementById('pfx-form').addEventListener('submit', function(e) {{
      e.preventDefault();
      var data = {{ /* 폼 데이터 수집 */ }};
      fetch('{webhook_url}', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(data)
      }}).then(function() {{ /* 성공 처리 */ }});
    }});
  </script>
</div>
"""
```

### f-string 이스케이핑 규칙

Python f-string 안에서 Liquid/JS 중괄호를 사용할 때:
| 원하는 출력 | f-string 표기 |
|------------|--------------|
| `{{ customer.email }}` (Liquid) | `{{{{ customer.email }}}}` |
| `{% if customer %}` (Liquid) | `{{% if customer %}}` |
| `{ key: value }` (JS 객체) | `{{ key: value }}` |
| `${variable}` (JS 템플릿 리터럴) | `${{variable}}` |

이 규칙을 틀리면 Python f-string 파싱 에러 또는 Liquid 렌더링 오류가 발생한다.

## OS 2.0 JSON 템플릿

```python
def build_template_json():
    return json.dumps({
        "sections": {
            "main": {
                "type": "page-name",  # sections/ 파일명과 일치
                "settings": {}
            }
        },
        "order": ["main"]
    })
```

## CSS 스코핑 전략

각 페이지별 고유 접두사로 CSS 클래스를 명명하여 테마 스타일과 충돌을 방지:

| 페이지 | 접두사 | 예시 |
|--------|-------|------|
| Core Signup | `cs-` | `.cs-container`, `.cs-field` |
| Influencer Gifting | `igf-` | `.igf-form`, `.igf-step` |
| Creator Profile | `cp-` | `.cp-wrapper`, `.cp-input` |
| Loyalty Survey | `ls-` | `.ls-banner`, `.ls-question` |
| CHA&MOM Gifting | `cmg-` | `.cmg-product`, `.cmg-card` |

## 배포 CLI 옵션

| 옵션 | 동작 |
|------|------|
| (없음) | 전체 배포 (asset 업로드 + 페이지 생성/업데이트, published=true) |
| `--dry-run` | Liquid 코드만 출력, API 호출 안 함 |
| `--unpublish` | 배포하되 published=false (비공개 테스트) |
| `--rollback` | theme asset 삭제 + 페이지 삭제 |

## sessionStorage 핸드오프

다단계 설문에서 페이지 간 데이터 전달:

```javascript
// 페이지 A: 데이터 저장
sessionStorage.setItem('onzenna_signup_data', JSON.stringify(formData));

// 페이지 B: 데이터 로드
var prevData = JSON.parse(sessionStorage.getItem('onzenna_signup_data') || '{}');
```

## 새 Liquid 페이지 개발 체크리스트

1. 가장 유사한 기존 `deploy_*.py`를 복사
2. 상수 수정: `SECTION_KEY`, `TEMPLATE_KEY`, `PAGE_HANDLE`, `PAGE_TITLE`
3. CSS 접두사를 새 고유값으로 변경
4. `build_section_liquid()` 에서 HTML/CSS/JS 작성
5. n8n webhook URL 환경변수 추가 (.env)
6. `--dry-run`으로 Liquid 코드 확인
7. `--unpublish`로 비공개 배포 후 테스트
8. 확인 후 본배포
9. `workflows/` 에 배포 문서 추가
