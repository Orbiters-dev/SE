---
name: "기억해둬" 요청은 3중 연결 필수
description: 세은이 "기억해둬"/"저장해둬" 할 때 파일 하나만 두지 말고 workflow + SKILL + memory 3중으로 불러올 수 있게 묶어야 함.
type: feedback
---

세은이 "기억해둬" / "저장해둬" / "틀만 저장해두려궁" 류로 재사용 SOP 저장 요청하면, 파일 1개만 덜렁 저장하지 말고 **아래 3개소를 모두 연결**해야 한다.

**Why:** 2026-04-20 ManyChat 팔로우 게이트 workflow 저장 시 `workflows/manychat_follow_gate_coupon.md` 파일만 두고 끝. 세은이 "이거 어떻게 불러와?" 물어봐서 그제서야 리공이 SKILL.md 참조 추가. 세은이 안 물어봤으면 workflow 고아 파일이 될 뻔. "내가 그냥 꺼버렸으면 어쩔 뻔?" 지적받음.

**How to apply:** 반복 가능한 SOP/템플릿 저장 요청 받으면 다음 3곳 모두 업데이트 필수:

1. **`workflows/{name}.md`** — 실제 SOP 본문
2. **담당 에이전트 `.claude/skills/{agent}/SKILL.md`**
   - "참고 문서" 표에 workflow 경로 추가 (⭐ 강조)
   - "호출 프로토콜" 섹션에 "이 키워드 들으면 반드시 workflow Read" 규칙 명시
   - "트리거 키워드" 섹션에 관련 키워드 추가
3. **`memory/reference_{topic}.md`** — 메모리 인덱스에서 로드되도록
   - MEMORY.md의 Reference 섹션에 링크 추가

3중 연결 확인 체크리스트:
- [ ] workflow 파일 저장
- [ ] SKILL.md 참고 문서 표 업데이트
- [ ] SKILL.md 트리거 키워드 확장
- [ ] SKILL.md 호출 프로토콜 섹션 (있으면) 갱신
- [ ] memory/reference_*.md 생성
- [ ] MEMORY.md 인덱스 추가

저장 후 세은에게 "앞으로 '{키워드}'라고 부르면 자동 로드됩니다" 라고 호출 예시 보고.
