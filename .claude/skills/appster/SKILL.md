---
name: appster
description: "ONZ APP (Onzenna) 풀스택 배포 + E2E 테스트 에이전트. Next.js 16 (Vercel) + Django REST (EC2) + Supabase Auth 아키텍처를 관리한다. 헤드리스 앱 배포, EC2 Django 앱 배포, Vercel 프론트엔드 관리, API 엔드포인트 검증, E2E 유저 플로우 테스트를 담당한다. 앱스터, ONZ APP, onzenna app, 헤드리스 배포, Vercel 배포, EC2 배포, API 테스트, E2E 테스트, 앱 런칭 관련 작업에 반드시 사용할 것."
---

# 앱스터 (Appster) - ONZ APP Full-Stack Agent

ONZ APP(Onzenna)의 풀스택 배포와 E2E 테스트를 담당하는 에이전트다.
Next.js 프론트엔드(Vercel) + Django REST 백엔드(EC2) + Supabase Auth를 통합 관리한다.

## When to Use This Skill

- ONZ APP 배포 (Vercel / EC2)
- Django onzenna 앱 코드 수정/배포
- Next.js 코드 수정 (API routes, pages, middleware)
- EC2 API 엔드포인트 테스트/검증
- Vercel 환경변수 설정/빌드 확인
- E2E 유저 플로우 테스트 (회원가입 -> 온보딩 -> 설문 -> 추천)
- Supabase Auth 연동 이슈
- 데이터 마이그레이션 (Django makemigrations/migrate)
- CORS, SSL, DNS 설정
- Beta gate middleware 관리

## Architecture

```
[Frontend - Vercel]                    [Backend - EC2]

Next.js 16 (App Router)                Django REST API
  React 19 + TypeScript 5                /api/onzenna/*
  Tailwind CSS v4                        HTTP Basic Auth
  Supabase Auth (login only)             PostgreSQL (onz_* tables)
       |                                      |
       | fetch() via ec2-api.ts               |
       +--------------------------------------+

[Auth Layer]
Supabase Auth
  - OAuth (Google, Apple)
  - Magic Link
  - User ID = EC2 onz_users.id (UUID)
```

## Stack Details

### Frontend (Vercel)
- **Framework**: Next.js 16, App Router
- **Language**: TypeScript 5, React 19
- **Styling**: Tailwind CSS v4
- **Auth**: Supabase Auth (OAuth + Magic Link)
- **API Client**: `lib/ec2-api.ts` (EC2 Django REST)
- **Types**: `lib/types.ts` (shared interfaces)
- **Middleware**: `middleware.ts` (beta gate + auth)
- **Repo**: `Orbiters11-dev/onzenna-app`

### Backend (EC2)
- **Server**: orbiters_2 (i-00195d735d022f057)
- **Public IP**: 13.124.157.191
- **Private IP**: 172.31.9.105
- **Django Project**: `/home/ubuntu/export_calculator`
- **App**: `/home/ubuntu/export_calculator/onzenna/`
- **Auth**: HTTP Basic (`admin:admin`)
- **DB**: PostgreSQL `orbiters_db` / user `export_calculator`
- **Service**: gunicorn via systemd (`export_calculator`)
- **Nginx**: reverse proxy, HTTP -> HTTPS redirect
- **Domain**: `orbitools.orbiters.co.kr` (DNS 확인 필요)

### Auth (Supabase)
- Free tier, 로그인 전용
- Supabase user ID = EC2 `onz_users.id` (UUID PK)
- 데이터 저장은 전부 EC2 Django

## Django onzenna App

### Models (7개, prefix: `onz_`)

| Model | Table | PK | Description |
|-------|-------|----|-------------|
| OnzUser | onz_users | UUID (from Supabase) | 마스터 유저 |
| OnzOnboarding | onz_onboarding | UUID (auto) | 온보딩 설문 |
| OnzEngagementEvent | onz_engagement_events | UUID (auto) | 유저 행동 로그 |
| OnzRecommendationCache | onz_recommendation_cache | UUID (auto) | AI 추천 캐시 |
| OnzLoyaltySurvey | onz_loyalty_survey | UUID (auto) | 로열티 설문 |
| OnzCreatorProfile | onz_creator_profile | UUID (auto) | 크리에이터 프로필 |
| OnzGiftingApplication | onz_gifting_applications | UUID (auto) | 인플루언서 기프팅 신청 |

### API Endpoints

| Method | Path | View | Description |
|--------|------|------|-------------|
| POST | `/api/onzenna/users/` | create_user | 유저 생성/업서트 |
| GET/PUT | `/api/onzenna/users/<uuid>/` | get_or_update_user | 유저 조회/수정 |
| POST | `/api/onzenna/onboarding/` | save_onboarding | 온보딩 저장 |
| GET | `/api/onzenna/onboarding/<uuid>/` | get_onboarding | 온보딩 조회 |
| POST | `/api/onzenna/engagement/` | log_engagement | 이벤트 로깅 |
| GET | `/api/onzenna/engagement/<uuid>/` | get_engagement | 이벤트 조회 |
| GET/PUT | `/api/onzenna/recommendations/<uuid>/` | get_or_update_recommendations | 추천 조회/저장 |
| POST | `/api/onzenna/loyalty-survey/` | save_loyalty_survey | 로열티 설문 |
| POST | `/api/onzenna/creator-survey/` | save_creator_survey | 크리에이터 설문 |
| GET | `/api/onzenna/status/<uuid>/` | get_status | 완료 상태 조회 |
| POST | `/api/onzenna/gifting/save/` | save_gifting | 기프팅 신청 |
| POST | `/api/onzenna/gifting/update/` | update_gifting | 기프팅 상태 업데이트 |
| GET | `/api/onzenna/gifting/list/` | list_gifting | 기프팅 목록 |
| GET | `/api/onzenna/tables/` | list_tables | 테이블 row count (모니터링) |

## Deployment

### EC2 배포 (Django)

1. 로컬에서 코드 수정 (`onzenna/*.py`)
2. `python tools/deploy_onzenna.py` 로 heredoc 명령 생성
3. EC2 Instance Connect 접속 (AWS Console > EC2 > orbiters_2 > Connect)
4. heredoc 명령 붙여넣기
5. `python3 manage.py makemigrations onzenna --settings=export_calculator.settings.production`
6. `python3 manage.py migrate onzenna --settings=export_calculator.settings.production`
7. `sudo systemctl restart export_calculator`
8. `curl -s -u admin:admin http://localhost:8000/api/onzenna/tables/`

**주의:**
- EC2 SSH 키 없음 -- Instance Connect만 사용 가능
- AWS Console: credentials in `~/.wat_secrets` (key: `AWS_CONSOLE_USER`, `AWS_CONSOLE_PASS`)
- INSTALLED_APPS에 `'onzenna'` 있는지 확인
- urls.py에 `path('api/onzenna/', include('onzenna.urls'))` 있는지 확인

### Vercel 배포 (Next.js)

1. GitHub repo에 push (branch: `wj/beta-ec2-integration`)
2. Vercel에서 자동 빌드/배포
3. 환경변수 설정 (Vercel Dashboard > Settings > Environment Variables)

**필수 환경변수:**
| Key | Value | Description |
|-----|-------|-------------|
| NEXT_PUBLIC_SUPABASE_URL | `https://mmlmxubtsaovbznplsuj.supabase.co` | Supabase 프로젝트 URL |
| NEXT_PUBLIC_SUPABASE_ANON_KEY | `eyJ...` (Vercel에 설정됨) | Supabase anon key |
| EC2_API_URL | `https://orbitools.orbiters.co.kr` | EC2 Django API (도메인) |
| EC2_API_USER | `admin` | HTTP Basic auth user |
| EC2_API_PASS | `admin` | HTTP Basic auth password |
| BETA_SECRET | `onz-beta-2026` | Beta gate 접근 코드 |

### Beta Gate

- `middleware.ts`에서 쿠키 기반 접근 제어
- `?beta=SECRET`으로 접속하면 쿠키 세팅되어 이후 접근 가능
- Production 준비 전까지 모든 페이지에 적용

## E2E Test Flow

### Test 1: 유저 생성 + 온보딩

```bash
# 1. 유저 생성
curl -X POST -u admin:admin -H "Content-Type: application/json" \
  https://13.124.157.191/api/onzenna/users/ \
  -d '{"id":"TEST_UUID","email":"test@onzenna.com","full_name":"Test","auth_provider":"email"}'

# 2. 온보딩 저장
curl -X POST -u admin:admin -H "Content-Type: application/json" \
  https://13.124.157.191/api/onzenna/onboarding/ \
  -d '{"user_id":"TEST_UUID","journey_stage":"expecting","baby_birthday":"2026-06-01"}'

# 3. 상태 확인
curl -u admin:admin https://13.124.157.191/api/onzenna/status/TEST_UUID/
```

### Test 2: 기프팅 신청 플로우

```bash
# 1. 기프팅 저장
curl -X POST -u admin:admin -H "Content-Type: application/json" \
  https://13.124.157.191/api/onzenna/gifting/save/ \
  -d '{"email":"creator@test.com","full_name":"Creator Test","instagram":"@creator_test","selected_products":["sippy-cup","straw-cup"]}'

# 2. 상태 업데이트
curl -X POST -u admin:admin -H "Content-Type: application/json" \
  https://13.124.157.191/api/onzenna/gifting/update/ \
  -d '{"email":"creator@test.com","status":"approved"}'

# 3. 목록 확인
curl -u admin:admin https://13.124.157.191/api/onzenna/gifting/list/
```

### Test 3: Full E2E (Browser)

1. `https://onzenna-app.vercel.app/?beta=SECRET` 접속
2. Supabase OAuth 로그인
3. 온보딩 플로우 완료
4. 로열티 설문 완료
5. EC2 DB에 데이터 확인: `/api/onzenna/status/{user_id}/`

### Test 4: Error Handling (Failure Cases)

**Scenario 4A: EC2 API 500 Error**

```bash
# EC2 API 시뮬레이션: 일시적 오류 후 복구
sudo systemctl stop export_calculator
curl -u admin:admin https://13.124.157.191/api/onzenna/users/
# Expected: 500 or connection refused
# Fix: sudo systemctl start export_calculator
# Retry 후 성공 확인
```

**Scenario 4B: Supabase Auth Timeout**

Browser DevTools → Network → throttle to "Slow 3G" → Click "Sign in with Google" → 30초 이상 대기
Expected: 타임아웃 후 "Auth session expired. Please sign in again." 메시지
Recovery: Refresh → 새 로그인 시도 성공

**Scenario 4C: Network Timeout During Onboarding Submit**

Onboarding form 입력 후 Submit 직전 → DevTools → Offline mode 전환
Expected: "Network error. Your response will be saved locally." (sessionStorage fallback)
Recovery: Online 복구 후 Submit retry → 성공

## Troubleshooting

### EC2 접속 안 될 때
- AWS Console > EC2 > Instances > orbiters_2 > Connect > EC2 Instance Connect
- Security Group에서 inbound rule 확인 (port 80, 443, 22)

### gunicorn 에러
```bash
sudo systemctl status export_calculator
sudo journalctl -u export_calculator --no-pager -n 50
```

### Django 마이그레이션 충돌
```bash
cd /home/ubuntu/export_calculator
python3 manage.py showmigrations onzenna --settings=export_calculator.settings.production
# 필요 시: rm onzenna/migrations/0*.py (backup 먼저!)
# python3 manage.py makemigrations onzenna --settings=export_calculator.settings.production
```

### DNS/SSL 이슈
- `orbitools.orbiters.co.kr` DNS가 EC2 IP와 다를 수 있음
- EC2 직접 IP 사용: `https://13.124.157.191` (-k flag 필요 시)
- Vercel 환경변수에 IP 직접 입력

### Vercel 빌드 실패
- `vercel.com` > 프로젝트 > Deployments > 실패 빌드 로그 확인
- 환경변수 누락 확인
- TypeScript 타입 에러 확인

## Files Reference

### Local (WJ Test1/)
| File | Description |
|------|-------------|
| `onzenna/models.py` | 7 Django models |
| `onzenna/views.py` | REST API views |
| `onzenna/urls.py` | URL routing |
| `onzenna/admin.py` | Django Admin |
| `onzenna/apps.py` | App config |
| `tools/deploy_onzenna.py` | EC2 deployment command generator |
| `tools/shopify_tester.py` | E2E test runner |
| `workflows/shopify_tester.md` | Test workflow SOP |

### GitHub (Orbiters11-dev/onzenna-app)
| File | Description |
|------|-------------|
| `middleware.ts` | Beta gate + auth |
| `lib/types.ts` | Shared TypeScript interfaces |
| `lib/ec2-api.ts` | EC2 Django API client |
| `app/api/recommendations/route.ts` | Recommendations API route |
| `app/api/webhooks/n8n/route.ts` | n8n webhook handler |
| `app/api/join/route.ts` | Join/signup API |
| `app/account/page.tsx` | Account page |

## Current Status (2026-03-12)

- EC2 Django API: **LIVE** (7 tables, all endpoints working)
- Vercel Frontend: **Phase 5 검증 중**
- DNS: `orbitools.orbiters.co.kr` -> 잘못된 IP (수정 필요)
- Workaround: EC2 IP 직접 사용 (`https://13.124.157.191`)
- Beta gate: 설정됨
- Auth: admin:admin (프로덕션 전 변경 필요)
