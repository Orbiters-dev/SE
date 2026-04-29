---
name: 개인정보 git 커밋 금지
description: 인플루언서 계약서, 개인정보 포함 파일은 절대 git에 커밋하지 않는다
type: feedback
---

인플루언서 계약서, 개인정보(이름, 이메일, 주소, 계좌) 포함 파일은 절대 git에 올리지 않는다.

**Why:** 세은이 명시적으로 지시. 개인정보 유출 위험.

**How to apply:** `Data Storage/contracts/`, `memory/influencers/` 등 개인정보 포함 경로는 .gitignore에 등록. 새로운 개인정보 파일/폴더 생성 시에도 반드시 .gitignore 확인.
