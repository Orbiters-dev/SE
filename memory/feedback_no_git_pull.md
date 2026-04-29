---
name: Git pull 금지 + 파일 크기 최우선
description: SE 폴더에 git pull/fetch 금지. 파일 크기 증가 방지가 1순위. 배포는 GitHub API 직접 수정으로.
type: feedback
---

SE 폴더는 git remote 연결 없이 독립 로컬로 유지한다.

**Why:** 이전 seeun 폴더에서 Claude Code가 세션 중 자동으로 `git pull`을 실행 → 다른 사람/github-actions[bot] 자료가 쌓여서 폴더 1GB까지 커짐 → Claude Code 작동 불가. 세은이 이 문제를 1순위로 잡으라고 강조.

**How to apply:**
- git pull, git fetch 절대 실행 금지
- git remote add 후에도 push만 하고, 안 되면 GitHub API로 직접 커밋
- push 거부되면 pull 대신 GitHub API로 파일 직접 수정 → Actions 배포
- push 후 remote 제거 (`git remote remove origin`)
- 파일 크기 증가를 항상 최우선으로 경계할 것
