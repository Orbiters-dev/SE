# 인획이 핸드오프 패키지 — 빠른 시작

GROSMIMI Japan 인스타그램 주간 콘텐츠 기획(주 20개 카루셀 기획안) 업무 인수인계 패키지입니다.

## 구성

| 경로 | 내용 |
|------|------|
| `인획이_인수인계.md` | **핵심 문서.** PART 1을 본인 Claude에 그대로 붙여넣으면 에이전트 지침으로 동작 |
| `tools/plan_weekly_content.py` | 주간 기획안 20개 생성기 (Firecrawl 트렌드 + Claude → 엑셀) |
| `tools/weekly_ig_competitor_analysis.py` | 경쟁사 IG 주간 분석 (선택) |
| `tools/scrape_ig_competitor.py` | 경쟁사 IG 스크래퍼 보조 도구 (선택) |
| `sample/7월_W4_기획안.xlsx` | 직전 주 기획안 — 첫 실행 시 `--avoid-xlsx` 로 지정 (주제 중복 방지) + 산출물 형식 참고용 |
| `.env.example` | API 키 템플릿 → `.env` 로 복사 후 키 입력 |
| `requirements.txt` | 파이썬 패키지 목록 |

## 5분 세팅

```bash
# 1. Python 3.10+ 에서 패키지 설치
pip install -r requirements.txt

# 2. .env.example 을 .env 로 복사하고 키 2개 입력
#    FIRECRAWL_API_KEY / ANTHROPIC_API_KEY

# 3. 첫 실행 (Windows 는 앞에 PYTHONIOENCODING=utf-8 붙이기)
python tools/plan_weekly_content.py --distribution "tips:8,brand:6,k_babyfood:3,knowledge:3" --avoid-xlsx "sample/7월_W4_기획안.xlsx"

# 4. 출력: .tmp/weekly_content_plan_YYYYMMDD.xlsx
#    → 생성 후 검증(인수인계.md PART 1 - 11번)을 거쳐 본인 보관 폴더에 {월}_W{N}_기획안.xlsx 로 저장
```

다음 주부터는 `--avoid-xlsx` 에 직전 주에 만든 본인 파일을 지정하면 됩니다.

## 도구 없이 Claude만으로 운영하는 경우

`인획이_인수인계.md` PART 1 지침 + 직전 주 엑셀의 주제 목록(C열)을 Claude 대화에 붙여넣고 20개 기획안을 직접 작성시키면 됩니다. 트렌드 자동 반영은 안 되지만 룰·형식·검증은 동일하게 적용하세요.

상세 규칙·사고 이력·검증 절차는 전부 `인획이_인수인계.md` 참조.
