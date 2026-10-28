---
name: 기본정보 폼 원장 → WL Code & Payment 로스터 동기화 (시트 구조 + 핸들 정규화 함정)
description: 기본정보(1Gd8JrWm gid1605522311) 응답자 중 WL Code&Payment(13S1cST2 gid751080099) 미등재자 추가 방법 + 핸들 매칭 정규화/교차검증 함정.
type: reference
---

세은 지시 반복 작업: "기본정보 탭에 입력한 사람 중 WL Code 탭에 없는 사람 전부 추가, 담당자=seeun".

## 두 시트

**Source = 기본정보 (폼 응답 원장)**
- ID `1Gd8JrWm-nOzscmL2tPLTW23EoC_QGtA07C0xMY6Jr8E`, 탭 `기본정보` gid `1605522311`
- 같은 파일 다른 탭: `통합`(329331514)·`투고완료`(1196213398)·`재협업 정보`(925116435)
- 헤더 **row 1** (index 0), 데이터 **row 2+**. 컬럼: A日時 / **B お名前(フルネーム)** / **C Instagramアカウント名(@〜)** / D ご職業 / E メールアドレス / F 月齢 …

**Target = WL Code & Payment (로스터)**
- ID `13S1cST2ukuNNHNUmyXAr1HuaYPsuuK_EfUQ10IWIQsE`, 탭 `WL Code & Payment` gid `751080099` (= 세은이 "WL Code 탭"이라 부르는 것)
- 헤더 **row 3** (index 2), 데이터 **row 4+**. col_count 47.
- 컬럼: A운영기간 / B Collab Round / **C Creator name** / **D Creator ID(=IG핸들, @없음, 매칭키)** / E Platform / F Deliverable Type / G Product / **H PIC(=담당자)** …
- 원칙상 "계약서 받은 사람만" 기재였으나, 세은 지시로 기본정보 전원 추가하기도 함(DM/계약 진행중 다수 포함 정상).

## 추가 방법 (gspread + SA)
인증 `credentials/google_service_account.json` (scopes spreadsheets+drive). 매칭키 = IG 핸들.
추가 행 = `['','',이름,핸들,'','','','seeun']` 를 마지막 채워진 행(≤col H 기준) 다음부터 `A{start}:H{end}` RAW update.
채우는 칸은 **Creator name(C)·Creator ID(D)·PIC(H)=seeun** 3개만. 나머지 세은이 채움.

## ⚠️ 핸들 정규화 함정 (교차검증 필수)
기본정보 C열 핸들 형식이 제각각 → 단순 split 하면 오탐:
- `＠`(전각 U+FF20)·`@`(반각) 혼재
- `@ unichan_uniuni7` (＠ 뒤 **공백**) → naive split 시 빈 '' 됨 → **"없음" 오판**
- `shiyupi_baby\n(TikTokも…)` 개행, `TikTok（@okane_pinchi）` 괄호+전각
- `@har_ka628 TikTok@haaru0628` (IG+TikTok 둘) → 첫 @토큰만
- 핸들이 일본어 닉네임인 경우(`がくまる`)=폼 오기입 → 세은에게 실제 핸들 확인

추출 정규식: `re.search(r'[@＠]\s*([A-Za-z0-9_.]+)', raw)` (공백 허용), 없으면 개행/괄호/공백 앞까지.
정규화: `strip().replace('＠','').replace('@','').lower()`.

**단일 정규화 결과만 믿지 말고 WL col D raw 블롭에 substring 2차 교차검증.** 2026-10-01 실제로 渋谷彩七(unichan_uniuni7)이 `＠ ` 공백 때문에 "미등재" 오탐 → raw 블롭 교차검증으로 이미 존재 확인·제외. `GROSMIMI JAPAN`(핸들 "0")은 쓰레기 행. [[mistakes-20260907-partial-data-repeated-assertion]] 계열 — 빈결과=도구/정규화 실패 신호.

2026-10-01 실행: 기본정보 135 unique 중 32명 미등재 → 249~280행 추가(PIC=seeun). 清水里花子 핸들 `がくまる`→`baby.gakubiyori__2026` 세은 교정.
