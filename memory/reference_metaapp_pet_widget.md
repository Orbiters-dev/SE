---
name: metaapp-pet-widget
description: 메타몽 앱 펫 "꼬질몽" — 확정 디자인·감정 9종·판정 신호·트리거 확장법·배포 주의
metadata:
  type: reference
---

# 메타몽 앱 펫 위젯 「꼬질몽」 (2026-08-28 배포)

**확정 디자인**: 납작 찐빵(가로로 퍼진 몸) · 베이지(흰색 no — 세은) · 양끝으로 벌어진 짝눈(r5/4.5, 좌우 높이 어긋남) · 꼬질 얼룩+솔기 스티치 · 외가닥 안테나 머리. 컨셉 = "귀엽게 못생김"(바부) — 그냥 못생김과 다름, 못난이 개그 요소(코풍선·앞니·침)로 표현.

**정본 SVG = `meta-app/components/meta/Pet.tsx`** (감정 9종 전부 내장). .tmp 프리뷰 HTML은 폐기 가능 사본.

## 구조
- `lib/pet-status.ts` — 판정: ①delivery(Graph `fetchAdStatuses` 게이트 — [[reference-meta-wl-branded-ad-api-creation]]과 별개로 절대 룰 준수) ②오늘 Proven 졸업 ③KPI 페이스(KPI 탭과 동일 함수) ④신선도 D-3
- `app/api/pet-status/route.ts` — force-dynamic (무거운 라우트 빌드 프리렌더 금지)
- 우선순위 하나만: 몸살 > 엉엉 > 갸웃(판정불가·API실패) > 댄스 > 쿨쿨
- 걷는 기분: 쿨쿨(몽유병)·댄스·냠냠·돈눈 / 정지+호소: 엉엉(팻말)·몸살·갸웃·깜짝·선생님
- 미리보기: URL `?pet=<mood>` (dance/cry/sleep/confused/sick/surprised/rich/teacher/munch)

## 트리거 확장법 (세은 예고: 추후 추가)
얼굴은 이미 전부 있음 — `pet-status.ts`에 reason push + mood 환원 분기만 추가.
미연결 4종: 깜짝=spend/CTR 급변 · 돈눈=매출 신기록/ROAS 급등 · 선생님=주간 덱 도착 · 냠냠=수집 진행 중.

## 배포 주의
- `vercel --prod --yes` 를 **meta-app 디렉터리 + 글로벌 CLI**로 (npx 새 vercel = 미인증 실패). 프로드 alias = meta-app-one.vercel.app.
- `/ads` 정적 생성 60s 타임아웃 = DK 순단 신호 → DK 회복 후 재시도.
- 로컬 `.env.local` Graph 토큰 2026-07-31 만료 상태 (프로드 env 별도·정상).
