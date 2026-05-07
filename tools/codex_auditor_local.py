#!/usr/bin/env python3
"""
Codex Auditor — OpenAI 기반 검사인 에이전트
Builder가 만든 산출물을 독립적으로 검증하고 피드백을 반환한다.

Usage:
    from codex_auditor import CodexAuditor
    auditor = CodexAuditor()
    result = auditor.audit(task_type="dm", content=draft, context={...})
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime

# .env 로드
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from openai import OpenAI

# ── 업무별 검사 규칙 ──────────────────────────────────────────

AUDIT_RULES = {
    "dm": {
        "name": "인플루언서 DM 검사",
        "system": """당신은 일본 인플루언서 DM 품질 검사관입니다.
아래 규칙을 기준으로 DM 초안을 검사하고 위반 사항을 지적하세요.

【필수 규칙】
- 赤ちゃん 금지 → お子様 사용
- ストローカップ 금지 → ストローマグ
- GROSMIMI JAPANです 자기소개 금지
- 서명에 개인 이름(허세은 등) 금지, GROSMIMI JAPAN만
- 컬러 목록 나열 금지
- ですよ 금지 → です
- 大丈夫ですよ 금지 → 大丈夫です
- 허락하는 톤 금지 (進めていただいて大丈夫です 등)
- 항목 2개 이상이면 ①② 또는 ・로 구분
- ・항목 사이 빈 줄 1개씩
- 이름은 성(名字)만, 풀네임 금지
- 용량(200ml/300ml) 지정 금지
- ワンタッチ에 300ml 붙이지 않음
- 스테인리스 제품 제안 금지 (재고 문제)
- 24개월 이상 추천 안 함
- 링크는 https://www.rakuten.co.jp/littlefingerusa/ 고정
- 해시태그: #PR #グロミミ #grosmimi #ストローマグ
- 기프팅 안내 시 쿠션어 사용 (ギフティングです 직접적 X)
- 당연한 안내 넣지 않기
- 같은 이름 반복 최소화

【톤 규칙】
- 건조한 안내 금지, 감사+공감 충분히
- STEP 2 첫 응답은 상대 메시지 맥락에 맞춰 커스텀
- 거절 답장도 맥락 커스텀
- 부탁하는 입장으로 공손하게""",
        "check_format": """검사 결과를 아래 JSON 형식으로 반환하세요:
{
  "pass": true/false,
  "score": 0-100,
  "violations": [{"rule": "규칙명", "location": "위반 위치", "fix": "수정 제안"}],
  "tone_check": "톤 평가 한 줄",
  "improved_draft": "수정된 전체 DM (위반 있을 경우만)"
}"""
    },

    "workflow": {
        "name": "n8n 워크플로우 검사",
        "system": """당신은 n8n 워크플로우 구조 검사관입니다.
아래 규칙을 기준으로 워크플로우 JSON을 검사하세요.

【필수 규칙】
- POST 시 active 필드 포함 금지 (read-only)
- PUT 시 name 필드 필수
- 노드 간 연결(connections) 누락 체크
- 크레덴셜 참조가 유효한지 확인
- Webhook 노드의 path 중복 체크
- Error handling 노드 존재 여부
- 무한 루프 가능성 체크
- WJ TEST 환경이면 base ID가 appT2gLRR0PqMFgII인지 확인
- PROD 환경이면 base ID가 appNPVxj4gUJl9v15인지 확인""",
        "check_format": """검사 결과를 아래 JSON 형식으로 반환하세요:
{
  "pass": true/false,
  "score": 0-100,
  "violations": [{"rule": "규칙명", "node": "노드명", "fix": "수정 제안"}],
  "structure_check": "구조 평가 한 줄",
  "missing_connections": ["누락된 연결 목록"]
}"""
    },

    "code": {
        "name": "Python 코드 검사",
        "system": """당신은 Python 코드 품질 검사관입니다.
이 프로젝트의 알려진 실수 패턴을 기준으로 검사하세요.

【필수 규칙】
- cp949 인코딩 사용 금지 → utf-8
- Windows에서 curl 사용 시 -sk 필수
- subprocess에서 shell=True 사용 시 보안 체크
- .env 파일 직접 읽기 대신 dotenv 사용
- API 키 하드코딩 금지
- try/except에서 bare except 금지
- f-string 안에서 따옴표 중첩 주의
- Path 사용 시 Windows/Unix 호환성
- Google Sheets API range에 시트명 포함 여부
- requests timeout 미지정 체크
- 파일 쓰기 시 encoding='utf-8' 명시""",
        "check_format": """검사 결과를 아래 JSON 형식으로 반환하세요:
{
  "pass": true/false,
  "score": 0-100,
  "violations": [{"rule": "규칙명", "line": "라인번호/위치", "fix": "수정 제안"}],
  "security_check": "보안 평가 한 줄",
  "improved_code": "수정된 코드 (위반 있을 경우만, 해당 부분만)"
}"""
    },

    "report": {
        "name": "리포트/엑셀 검사",
        "system": """당신은 데이터 리포트 품질 검사관입니다.

【필수 규칙】
- 숫자 합산 정합성 (부분합 = 전체합)
- 날짜 범위 일관성
- 빈 셀/NaN/0 처리
- 브랜드/채널 커버리지 완전성
- 단위 통일 (엔/달러 혼재 금지)
- 전월 대비 ±50% 이상 변동 시 경고
- n.m 셀 적절성 (데이터 미수집 기간)""",
        "check_format": """검사 결과를 아래 JSON 형식으로 반환하세요:
{
  "pass": true/false,
  "score": 0-100,
  "violations": [{"rule": "규칙명", "location": "셀/탭", "fix": "수정 제안"}],
  "data_integrity": "데이터 정합성 평가 한 줄",
  "warnings": ["경고 목록"]
}"""
    },

    "ig_plan": {
        "name": "인스타그램 기획안 검사",
        "system": """당신은 인스타그램 콘텐츠 기획안 검사관입니다.

【필수 규칙】
- 3분야 각 10개씩 = 총 30개 확인 (meme:10, brand:10, mom_tip:10)
- 주제 중복 금지 (과거 기획안과 비교)
- Mom Tips: あるある공감 + チェックリスト 위주
- 캐러셀 페이지별 이미지 구상 포함 여부
- 시리즈명 ママの「それ知りたかった！」 사용
- 경쟁사 분석 데이터 반영 여부
- 시즌성/시의성 체크""",
        "check_format": """검사 결과를 아래 JSON 형식으로 반환하세요:
{
  "pass": true/false,
  "score": 0-100,
  "violations": [{"rule": "규칙명", "item": "해당 기획", "fix": "수정 제안"}],
  "category_balance": {"meme": N, "brand": N, "mom_tip": N},
  "duplicate_topics": ["중복된 주제 목록"],
  "seasonality_check": "시즌성 평가 한 줄"
}"""
    },

    "ppc": {
        "name": "Amazon PPC 실행 검사",
        "system": """당신은 Amazon PPC 광고 실행 검사관입니다.

【필수 규칙】
- 일일 예산 상한: $120 (Manual 60% / Auto 40%)
- 캠페인별 최대: $50
- 입찰 최대: $3.00
- 모든 실행은 "approved": true 필수
- Fleeters Inc (Naeiae) 전용 실행, 나머지는 분석만
- 입찰 변경폭 ±20% 이내
- 네거티브 키워드 추가 시 전환 0건 + $5+ 지출 확인""",
        "check_format": """검사 결과를 아래 JSON 형식으로 반환하세요:
{
  "pass": true/false,
  "score": 0-100,
  "violations": [{"rule": "규칙명", "campaign": "캠페인명", "fix": "수정 제안"}],
  "budget_check": {"total": N, "limit": 120, "safe": true/false},
  "bid_check": {"max_bid": N, "limit": 3.0, "safe": true/false},
  "approval_check": true/false
}"""
    },

    "general": {
        "name": "일반 산출물 검사",
        "system": """당신은 업무 산출물 품질 검사관입니다.
논리적 일관성, 완전성, 정확성을 검사하세요.""",
        "check_format": """검사 결과를 아래 JSON 형식으로 반환하세요:
{
  "pass": true/false,
  "score": 0-100,
  "violations": [{"rule": "규칙명", "location": "위치", "fix": "수정 제안"}],
  "summary": "전체 평가 한 줄"
}"""
    }
}


class CodexAuditor:
    """OpenAI Codex 기반 독립 검사 에이전트"""

    def __init__(self, model: str = "gpt-4o"):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.log_dir = Path(__file__).parent.parent / ".tmp" / "auditor_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def audit(self, task_type: str, content: str, context: dict = None,
              extra_rules: str = None) -> dict:
        """
        산출물을 검사하고 결과를 반환한다.

        Args:
            task_type: dm, workflow, code, report, ig_plan, ppc, general
            content: 검사할 산출물 텍스트
            context: 추가 맥락 (인플루언서 정보, 이전 DM 등)
            extra_rules: 추가 검사 규칙

        Returns:
            dict: 검사 결과 (pass, score, violations, ...)
        """
        rules = AUDIT_RULES.get(task_type, AUDIT_RULES["general"])

        system_prompt = rules["system"]
        if extra_rules:
            system_prompt += f"\n\n【추가 규칙】\n{extra_rules}"

        user_prompt = f"다음 산출물을 검사해주세요.\n\n"
        if context:
            user_prompt += f"【맥락】\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        user_prompt += f"【산출물】\n{content}\n\n"
        user_prompt += rules["check_format"]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content
            result = json.loads(result_text)

            # 로그 저장
            self._save_log(task_type, content, result)

            return result

        except Exception as e:
            error_result = {
                "pass": False,
                "score": 0,
                "violations": [{"rule": "SYSTEM_ERROR", "location": "auditor", "fix": str(e)}],
                "error": str(e)
            }
            self._save_log(task_type, content, error_result)
            return error_result

    def audit_loop(self, task_type: str, content: str, context: dict = None,
                   extra_rules: str = None, max_loops: int = 2,
                   builder_fix_fn=None) -> dict:
        """
        Builder ↔ Auditor 2회 루프를 실행한다.

        Args:
            task_type: 업무 유형
            content: 초안
            context: 맥락
            extra_rules: 추가 규칙
            max_loops: 최대 루프 횟수 (기본 2)
            builder_fix_fn: Builder 수정 함수 (violations → 수정된 content)
                            None이면 Auditor의 improved_draft 사용

        Returns:
            dict: {
                "final_content": 최종 산출물,
                "loops": [loop1_result, loop2_result],
                "final_pass": bool,
                "final_score": int
            }
        """
        loops = []
        current_content = content

        for i in range(max_loops):
            # Auditor 검사
            result = self.audit(task_type, current_content, context, extra_rules)
            loops.append({
                "loop": i + 1,
                "result": result,
                "content_before": current_content
            })

            # PASS면 조기 종료
            if result.get("pass", False):
                return {
                    "final_content": current_content,
                    "loops": loops,
                    "final_pass": True,
                    "final_score": result.get("score", 100)
                }

            # Builder 수정
            if builder_fix_fn and callable(builder_fix_fn):
                current_content = builder_fix_fn(
                    current_content, result.get("violations", [])
                )
            else:
                # Auditor가 제안한 수정본 사용
                improved = (result.get("improved_draft")
                           or result.get("improved_code")
                           or current_content)
                if improved and improved != current_content:
                    current_content = improved
                else:
                    # 수정본이 없으면 루프 중단
                    break

        final_result = loops[-1]["result"] if loops else {}
        return {
            "final_content": current_content,
            "loops": loops,
            "final_pass": final_result.get("pass", False),
            "final_score": final_result.get("score", 0)
        }

    def _save_log(self, task_type: str, content: str, result: dict):
        """검사 로그 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"{task_type}_{timestamp}.json"
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "task_type": task_type,
            "content_preview": content[:500],
            "result": result
        }
        log_file.write_text(
            json.dumps(log_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )


# ── CLI ──────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Codex Auditor — OpenAI 기반 검사인")
    parser.add_argument("--type", "-t", default="general",
                       choices=list(AUDIT_RULES.keys()),
                       help="검사 유형")
    parser.add_argument("--file", "-f", help="검사할 파일 경로")
    parser.add_argument("--text", help="검사할 텍스트 (직접 입력)")
    parser.add_argument("--context", "-c", help="맥락 JSON 파일")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI 모델")
    parser.add_argument("--loop", action="store_true",
                       help="Builder-Auditor 2회 루프 실행")
    parser.add_argument("--test", action="store_true",
                       help="API 연결 테스트")
    args = parser.parse_args()

    if args.test:
        print("Testing OpenAI API connection...")
        try:
            auditor = CodexAuditor(model=args.model)
            result = auditor.audit("general", "Hello, this is a test.", {})
            print(f"  OK — Score: {result.get('score', '?')}")
            print(f"  Model: {args.model}")
            print(f"  Result: {json.dumps(result, ensure_ascii=False, indent=2)}")
        except Exception as e:
            print(f"  FAIL — {e}")
        return

    # 콘텐츠 로드
    content = ""
    if args.file:
        content = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        content = args.text
    else:
        print("Error: --file 또는 --text 필요")
        sys.exit(1)

    # 맥락 로드
    context = {}
    if args.context:
        context = json.loads(Path(args.context).read_text(encoding="utf-8"))

    auditor = CodexAuditor(model=args.model)

    if args.loop:
        result = auditor.audit_loop(args.type, content, context)
        print(f"\n{'='*60}")
        print(f"HARNESS RESULT — {AUDIT_RULES.get(args.type, {}).get('name', args.type)}")
        print(f"{'='*60}")
        print(f"Loops: {len(result['loops'])}")
        print(f"Final Pass: {'PASS' if result['final_pass'] else 'FAIL'}")
        print(f"Final Score: {result['final_score']}/100")
        for loop in result["loops"]:
            r = loop["result"]
            violations = r.get("violations", [])
            print(f"\n  Loop {loop['loop']}: {'PASS' if r.get('pass') else 'FAIL'} "
                  f"(Score: {r.get('score', '?')}, Violations: {len(violations)})")
            for v in violations[:5]:
                print(f"    - [{v.get('rule', '?')}] {v.get('location', v.get('line', v.get('node', '?')))}: {v.get('fix', '')}")
        if result.get("final_content") and not result["final_pass"]:
            print(f"\n--- Improved Draft ---")
            print(result["final_content"][:1000])
    else:
        result = auditor.audit(args.type, content, context)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
