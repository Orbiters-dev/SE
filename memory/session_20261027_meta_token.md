# 세션 2026-10-27 — Meta 토큰 재발급 E2E

## 한 일
1. **진단**: META_ACCESS_TOKEN(글로벌) = code190/subcode **460** (비번 변경 세션 무효 — 459 체크포인트와 달리 재발급 필수) 이미 사망. META_JP_ACCESS_TOKEN = 유효하나 data_access 만료 11/1 (D-5).
2. **앱 구조 전수 규명**: .env FB_APP_ID/SECRET = **claude connection** 앱. 1차로 GROSMIMI_JP_API에서 뽑은 토큰은 시크릿 미보유라 장기교환 불가 + 글로벌 403 → 폐기. claude connection에서 재발급이 정답. (정본: 자동메모리 reference_meta_token_apps_structure.md)
3. **JP 완결**: 새 토큰 debug(스코프 3종 확인)→장기 교환(data_access 2027-01-25로 리셋)→JP 계정 라이브 검증→.env 교체→GHA 시크릿 갱신(gh secret set --body, 워크플로우 8개)→**meta_token_watch dry-run으로 E2E 검증 (D+89.7 여유 판정)**. 임시 토큰 파일 삭제.
4. **글로벌 규명**: 세은 FB 로그인의 접근 계정 = JP + Kazuki 개인 2개뿐 → act_6201(US) 권한 자체 없음. 용도 전수 = US 일간 리포트(10/21부터 12런 연속 실패)·DK meta_campaigns 채널(400, 런은 success로 떠서 은폐)·JP 투고 트래커(Apify 폴백으로 무피해 가동 실측). **결론: 글로벌 재발급 = US 계정 권한자 몫, 세은 할 일 없음.**

## 교정 (1건·소프트)
- 글로벌 토큰 복구를 세은의 선택지로 제시 → 세은 「내가 US Meta 만진 적 없는데 뭐하게?」가 정당한 반문. **복구 액션 배정 전에 "그 자원이 누구 업무인가" 용도 전수 실측이 먼저** — 용도를 모른 채 "복구 경로 2택"부터 내밀지 말 것.

## 재사용
- `.tmp/new_token_verify.py` — 토큰 debug→라이브→장기교환→재검증 원샷 (다음 재발급 2027-01 전 그대로 사용)
- `.tmp/token_expiry_check.py` — 양 토큰 만료·라이브 교차검증
- 토큰 발급 앱 판별 = `GET /app?fields=id,name` (debug_token 400 "did not match Viewing App" = 다른 앱 소속 신호)
- data_keeper.yml success여도 채널별 `FAILED` grep 필수 재확인

## 미완/대기
- US 리포트 중단(10/21~) 사실을 US 운영 쪽에 전달할지 = 세은 판단 대기 (세은 액션 아님).
