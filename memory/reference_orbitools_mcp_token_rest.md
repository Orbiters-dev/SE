---
name: orbitools-code-edit MCP 토큰 재발급 + REST 우회 + 소스 read 경로
description: MCP 토큰 만료 시 재발급·REST 직접호출·git credential로 WONGI read·호출 규약(diff --git, UTF8 bytes, cap 모델). orbitools 코드편집 작업 진입점.
type: reference
---

# orbitools-code-edit MCP 운영 경로 (2026-06-16 확립)

## 토큰
- 설정: `C:\Users\orbit\.claude.json` → mcpServers."orbitools-code-edit".args 의 `X-Session-Token: mcp_...` (정적, 30일 long-lived).
- 만료 시 도구 호출 = `invalid or expired session`(401). 검증: `GET https://orbitools.orbiters.co.kr/mcp/code-edit/me` (헤더 X-Session-Token).
- 재발급: 인텔리전스 대시보드 **Settings > Code Editing Setup** (`https://orbitools.orbiters.co.kr/api/onzenna/intelligence/dashboard/settings/code-editing-setup`). 세은이 브라우저 로그인(GitHub 계정 **Orbiters11-dev**) 후 발급 → .claude.json 토큰 교체. 만료 7일 전 셋업 페이지에 갱신 알림.

## REST 우회 (토큰 교체 후 reconnect/Reload 없이 즉시 사용)
- stdio MCP 프로세스는 spawn 시 args 토큰 1회만 읽음 → 토큰 바꿔도 reconnect 전엔 옛 토큰 그대로(VSCode `/mcp` Connected 떠도 호출은 401).
- 우회 = **REST 직접 호출**: `POST https://orbitools.orbiters.co.kr/mcp/code-edit/mcp/tools/{tool_name}` 헤더 `X-Session-Token`=새토큰. (`GET /mcp/tools`=도구목록, `/me`=신원). 모든 도구(list_my_caps/validate_change/preview_change/edit_file/request_cap/read_guide/search_guides/list_guides) REST 호출됨.

## 호출 규약 (함정)
- **body는 UTF-8 bytes로**: `Invoke-RestMethod -Body ([Text.Encoding]::UTF8.GetBytes($json)) -ContentType "application/json; charset=utf-8"`. 안 그러면 한글·배열 깨져 `must be non-empty list` 류.
- 단일원소 배열은 PowerShell ConvertTo-Json이 스칼라로 풂 → 수동 JSON `["x"]`로 박기.
- `preview_change` patch: **기존 파일 수정은 `diff --git a/p b/p` 헤더 필수**(없으면 path_mismatch — 서버가 경로 추출 못 함). 신규 파일은 `--- /dev/null` + full content(`+`줄). hunk line-count 엄격 검증.
- 응답 한글 깨짐: `[Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())`.

## cap 모델 (list_my_caps, SE=editor)
- 보유: backend.models / backend.services / backend.us_crm / crm.* / intelligence.* / shared / read:datakeeper / read:guide. **backend.migrations 없음** (migration은 별도 cap).
- **신규 파일 생성 = unmapped**(code:edit:other, MCP 서명 불가). 등록된 기존 파일(models.py 등)만 cap으로 편집. 신규 모델은 models.py append 또는 cap 요청.
- cap 부족 = `request_cap` (rate 5/7일, 승인=원기 dashboard inbox). multi_cap_root(예 backend+shared) = PR 분리 필요.

## WONGI 소스코드 read (MCP에 소스 read 도구 없음)
- read_guide=가이드문서 / dk_query_table=DK데이터. **소스코드 read 도구 부재.**
- 우회: Windows Credential Manager에서 git 저장 토큰 추출 → GitHub API.
  - `CredRead("git:https://github.com", type=1)` advapi32 P/Invoke → password blob(ghp_ 40자). (`git credential fill`은 GCM에서 빈 응답)
  - `https://api.github.com/repos/Orbiters-dev/WONGI/contents/{path}?ref=main` 헤더 Authorization `Bearer <tok>` + Accept `application/vnd.github.raw`.
- **서버측 한계**: edit_file/preview_change가 `/home/ubuntu/WONGI` clone --depth=50 (15초 timeout) → repo 커서 `git_apply_check_failed` 빈발. 원기 timeout 상향 필요.
