---
name: session-20261027-jangbogo
description: 세션 2026-10-27 (/장보고 10-27 (화) 32블록 append·라이브 검증 — 메타 D-1 CPLPV 74.9·주 83.8·DM 4건·JP 토큰 재발급·플레이북 개정 8건·TTS 타깃 전달. CRM PR 0건 이중 교차검증. 교정 0건)
type: project
---

# 세션 2026-10-27 — /장보고 (노션 토글 append)

## 산출

- 노션 Seeun Daily Report에 `2026-10-27 (화)` 토글 append — 32블록, toggle id `40686c6d-c046-81e0-ae33-da345dfc629e`. append 후 라이브 재덤프로 전 블록 검증.
- 구성: Headline 4항목(제목형) / CRM PR 0건 / 메타 일·주 표 + 캠페인 4 bullet + ◆ JP API 토큰 재발급 / 기타(인플루언서 소통·혜인님 인수인계·틱톡샵).

## 수집 데이터 (Meta JP)

- D-1(10-26): 지출 295,152 · CTR 12.07% · CPC 47 · CPLPV 74.9 (D-2 대비 지출 -19.8%).
- 주(10-20~26 vs 10-13~19): 지출 2,666,372(-11.8%) · CPLPV 83.8(-8.1).

## 당일 작업 수집 결과 (트랜스크립트 스캔 + 세션 메모리)

- DM 4건 (小向·田中anri·三輪·本城) — session_20261027_dm.md / _dm_b.md.
- Meta JP 토큰 재발급 세션 — 장기 교환·GHA 8개 시크릿 갱신·data access 2027-01-25 리셋·글로벌 토큰=US 전용 규명.
- 인플루언서 플레이북(노션)+핸드오버 문서 개정 룰 8건 반영 세션.
- TTS 맘풀 리포트+타깃 807명 CSV를 Desktop\s\performance marketing\Tiktok Shop 폴더로 전달.
- 제외: MCP 서버 등록(내부 환경설정)·이미지 압축 잡무(trivial — 10/26 ◆잡무 세은 삭제 관찰 반영).

## 재사용

- .tmp/daily_report_fetch_20261027.py (전일 sed 치환) · .tmp/scan_today_1027.py · .tmp/scan_detail_1027.py (특정 세션 assistant 발화 덤프) · .tmp/daily_report_notion_20261027.py.
- CRM PR 교차검증 = git log --since + orbitools list_recent_prs 이중.

## 교정 / 미완

- 교정 0건.
- 혜인님 인수인계 미팅 자체(10/26 「명일 예정」)는 트랜스크립트로 확인 불가 — 토글에는 검증된 플레이북 문서 작업만 기재. 세은이 필요 시 직접 추가.
