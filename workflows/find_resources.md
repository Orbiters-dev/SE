# Find Resources (자료 찾기)

프로젝트 내부 파일과 이메일을 검색하여 필요한 자료를 빠르게 찾는 워크플로우.

---

## Objective

키워드, 브랜드, 날짜, 파일 유형 등으로 내부 파일 시스템과 Gmail을 검색하여 필요한 자료를 빠르게 찾아 정리한다.

---

## Scope

### 1. 내부 파일 검색

아래 디렉토리들을 순서대로 검색:

| 우선순위 | 경로 | 설명 |
|---------|------|------|
| 1 | `Data Storage/` | 생성된 리포트, KPI, 수출서류, syncly 등 |
| 2 | `REFERENCE/` | Ex Price, 팩킹정보, 참고 문서 |
| 3 | `Shared/` | 팀 공유 자료 (credentials, KPIs, 리포트 등) |
| 4 | `Z:\Orbiters\CI, PL, BL\` | 수출 서류 원본 (CI/PL/BL) |
| 5 | `Z:\Orbiters\발주 서류 관리\` | 발주 관련 Excel |
| 6 | `카카오톡 받은 파일` | `~/OneDrive/문서/카카오톡 받은 파일/` |
| 7 | `Z:\Orbiters\` (루트) | 기타 브랜드 폴더, 재고관리 등 |

### 2. Gmail 검색

`tools/send_gmail.py --search` 사용.

**주요 검색 패턴:**

```bash
# 키워드 검색
python tools/send_gmail.py --search "subject:AP Shipping invoice" --max-results 10

# 발신자 검색
python tools/send_gmail.py --search "from:supplier@example.com newer_than:30d"

# 기간 검색
python tools/send_gmail.py --search "subject:invoice after:2024/01/01 before:2024/12/31"

# 첨부파일 검색
python tools/send_gmail.py --search "has:attachment filename:xlsx AP Shipping"
```

---

## Workflow Steps

### Step 1: 검색 의도 파악

유저 요청에서 추출:
- **키워드**: 검색할 핵심 단어 (예: "AP Shipping", "인보이스", "Ex Price")
- **브랜드**: Grosmimi, Naeiae, Conys 등
- **날짜 범위**: 특정 기간 필터
- **파일 유형**: xlsx, pdf, csv 등
- **검색 범위**: 내부 파일 / 이메일 / 둘 다

### Step 2: 내부 파일 검색

```bash
# Glob으로 파일명 패턴 검색
Glob("**/*AP*Ship*")
Glob("**/*invoice*")

# Grep으로 파일 내용 검색 (텍스트 파일)
Grep("AP Shipping", glob="*.md")

# 한글 경로는 Python으로 처리
python -c "
import os, glob
base = os.path.expanduser('~')
kakao = os.path.join(base, 'OneDrive', '문서', '카카오톡 받은 파일')
for f in os.listdir(kakao):
    if 'AP' in f.upper() and 'SHIP' in f.upper():
        print(os.path.join(kakao, f))
"
```

### Step 3: Gmail 검색

```bash
python tools/send_gmail.py --search "키워드" --max-results 10
```

### Step 4: 결과 정리

검색 결과를 정리하여 유저에게 보고:
- 파일 경로, 수정 날짜, 파일 크기
- 이메일의 경우: 발신자, 제목, 날짜, 스니펫

필요 시 데이터를 파싱하여 Excel 정리:
- 원본 파일 → `Data Storage/export/{카테고리}/raw_files/`
- 정리 Excel → `Data Storage/export/{카테고리}/`

---

## Directory Map

```
Z:\Orbiters\                                    # NAS 루트
├── CI, PL, BL\                                 # 수출 서류 원본
├── 발주 서류 관리\                              # 발주 Excel
├── GROSMIMI\                                    # 그로미미 전용
├── Influencer Team\                             # 인플루언서 팀 자료
├── ORBI CLAUDE_0223\ORBITERS CLAUDE\
│   ├── Shared\                                  # 팀 공유
│   │   ├── amazon-ppc-agent\
│   │   ├── CIPLCO\
│   │   ├── credentials\
│   │   ├── datakeeper\
│   │   ├── ORBI KPIs\
│   │   ├── syncly-crawler\
│   │   └── ...
│   └── WJ Test1\                                # 프로젝트 루트
│       ├── Data Storage\                        # 생성된 데이터
│       │   ├── export\                          # 수출 서류 (CIPL, AP Shipping 등)
│       │   ├── kpi_reports\                     # KPI 월간 리포트
│       │   ├── syncly\                          # Syncly 크롤링 데이터
│       │   ├── brand\                           # 브랜드별 자료
│       │   ├── marketing\                       # 마케팅 자료
│       │   └── ...
│       ├── REFERENCE\                           # 참고 문서 (Ex Price, 팩킹정보)
│       ├── tools\                               # 실행 도구
│       └── workflows\                           # SOP 워크플로우
│
~/OneDrive/문서/카카오톡 받은 파일/               # 카톡 받은 파일
```

---

## Entity Quick Reference

| 약어 | 풀네임 | 역할 |
|------|--------|------|
| LFU | LittlefingerUSA Inc. | Exporter/Importer |
| FLT | Fleeters Inc. | Importer |
| ORBI | Orbiters Co., Ltd. | Exporter |
| WBF | Walk by Faith | Final Consignee |

---

## Brands

Grosmimi, Naeiae, Conys, Nature Love Mere, Alpremio, BabyRabbit, BambooBebe, Commemoi, BeeMyMagic, Hattung, Cha&Mom, Onzenna

---

## Tools

| 도구 | 용도 |
|------|------|
| `Glob` | 파일명 패턴 검색 (영문 경로) |
| `Grep` | 파일 내용 검색 (텍스트 파일) |
| `python` (os.listdir) | 한글 경로 파일 검색 |
| `tools/send_gmail.py --search` | Gmail 검색 |
| `openpyxl` | Excel 파일 내용 파싱 |
| `PyPDF2 / pdfplumber` | PDF 파일 내용 파싱 |

---

## Edge Cases & Lessons Learned

- **한글 경로**: bash에서 한글 경로 깨짐. Python `os.path.expanduser("~")` + 유니코드 문자열로 직접 조합해야 함
- **카카오톡 폴더**: `~/OneDrive/문서/카카오톡 받은 파일/` — 파일명에 중복 번호 `(1)`, `(2)` 붙는 경우 많음
- **Z: 드라이브**: NAS 매핑 드라이브. git bash에서 `/z/` 형태로도 접근 가능하나 Python에서는 Windows 경로 사용 권장
- **Excel 인코딩**: 한글 헤더가 있는 Excel은 openpyxl에서 정상 파싱, cp949 인코딩 CSV는 별도 처리 필요
- **파일명 "APS"**: "AP Shipping"의 약어. 검색 시 "APS", "AP Ship", "AP Shipping" 모두 체크
