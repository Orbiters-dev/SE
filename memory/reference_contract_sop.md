---
name: 계약서 생성·DocuSeal 발송 SOP (2026-04-22 확정)
description: GROSMIMI 인플루언서 계약서 end-to-end 프로세스. 템플릿·스크립트·승인 단계 전부 포함
type: reference
---

## 전체 플로우

```
정보 수령 (풀네임 + 이메일)
  ↓
[1] DOCX 생성 (자동, 파일 생성만)
  ↓
[2] 세은 검토 + 승인
  ↓
[3] DocuSeal 발송 (DOCX 업로드)
  ↓
[4] STEP 6.5 DM 발송
  ↓
서명 대기 → 완료 → STEP 7 (배송지)
```

## [1] DOCX 생성

**스크립트:** `tools/generate_influencer_contract.py --manual '{JSON}'`

**필수 필드 (7개):**
| 필드 | 설명 | 예시 |
|------|------|------|
| `collab_type` | `paid` / `gifting` | `"paid"` |
| `influencer_name` | 한자 풀네임 | `"村井優里"` |
| `influencer_handle` | IG 핸들 (@제외) | `"bebi_mon_ikuji"` |
| `influencer_email` | 이메일 | `"x@y.com"` |
| `products_description` | 참조용 제품 설명 | `"ステンレスストローマグ 200ml (ベアバター)"` |
| `deliverables_detail` | 투고 플랫폼 | `"Instagram Reels 1本"` |
| `product_type` | `ppsu_straw` / `ppsu_onetouch` / `stainless` | `"stainless"` |
| `compensation_amount` (paid만) | 숫자 | `24200` |

**템플릿 경로 (세은 원본, 숫자 없는 버전):**
- 유상: `C:\Users\orbit\Desktop\s\참고자료\인플루언서 컨택\형식\インフルエンサーコンテンツ契約書（有償）.docx`
- 무상: `C:\Users\orbit\Desktop\s\참고자료\인플루언서 컨택\형식\インフルエンサーコンテンツ契約書（無償）.docx`

**치환되는 플레이스홀더:**
- `{{AGREEMENT_DATE}}` — 계약일 (자동 오늘)
- `{{ACCOUNT_HANDLE}}` — 핸들
- `{{INFLUENCER_NAME}}` — 풀네임
- `{{PLATFORMS}}` — `（Instagram Reels 1本）` 등
- `{{PAYMENT_AMOUNT}}` — 금액 (유상만)
- `{{COMPANY_NAME}}` — `許世恩` (고정)
- `{{HASHTAGS}}` — 제품 타입 기반 해시태그 (자동 선택)

**제품별 해시태그 매핑 (공식 통일 룰):**
| product_type | 해시태그 |
|--------------|---------|
| ppsu_straw | `#グロミミ #grosmimi #ストローマグ #スマートマグ #PPSU` |
| ppsu_onetouch | `#グロミミ #grosmimi #ストローマグ #スマートマグ #PPSU` |
| stainless | `#グロミミ #grosmimi #ストローマグ #スマートマグ` |

**서명 필드 (text tag, 자동):**
원본 template에 `{{氏名;role=First Party;type=text}}` / `{{署名;type=signature}}` / `{{日付;type=date}}` 등 이미 삽입 완료. DocuSeal이 DOCX→PDF 변환 시 자동 제거 + 서명 필드로 변환.

**출력 파일:**
- `C:\Users\orbit\Desktop\s\인플루언서 계약서(서명 없는 ver)\{name}_{date}.docx`
- `.pdf` (참고용 프리뷰)

## [2] 세은 검토

DOCX/PDF 생성만 끝난 상태. **절대 자동 발송 금지.**

세은이 파일 내용 확인 후 "발송해" 승인.

거부 시: 파일 덮어쓰기 재생성 or 수정.

## [3] DocuSeal 발송

**스크립트:** `tools/send_docuseal_contract.py`

**표준 발송 명령어 (DOCX 업로드):**
```bash
python tools/send_docuseal_contract.py \
  --name "村井優里" \
  --email "yuurikuruma629@gmail.com" \
  --pdf "C:\Users\orbit\Desktop\s\인플루언서 계약서(서명 없는 ver)\村井優里_20260422.docx" \
  --type paid
```

**반드시 DOCX 경로 전달** (`.docx` 확장자). PDF 경로 주면 레거시 모드로 text tag 글자가 남는다.

**플래그:**
| 플래그 | 용도 |
|--------|------|
| `--dry-run` | API 호출 없이 파라미터 확인만 |
| `--no-send` | submission 생성하되 이메일 발송 X (서명 URL만 반환, 세은 미리보기용) |
| `--resend SUBMITTER_ID` | 기존 submitter에 이메일 재발송 |
| `--status` | 최근 submissions 목록 |
| `--check SUBMISSION_ID` | 특정 submission 상태 조회 |

**권장 승인 서브플로우:**
1. `--no-send` 로 먼저 생성 → 서명 URL을 세은에게 공유
2. 세은이 URL 접속해 필드 배치·내용 검증
3. OK: `--resend SUBMITTER_ID` 로 이메일 발송
4. NG: DELETE submission 후 재생성

**Submission 삭제 (문제 시):**
```python
import requests, os
from dotenv import load_dotenv
load_dotenv()
base = os.getenv('DOCUSEAL_BASE_URL')
headers = {'X-Auth-Token': os.getenv('DOCUSEAL_API_TOKEN') or os.getenv('DOCUSEAL_API_KEY')}
requests.delete(f'{base}/api/submissions/{submission_id}', headers=headers)
```

## [4] STEP 6.5 DM

발송 성공 후 인플루언서에게:

```
○○様

お世話になっております。

契約書を作成のうえ、メールにてお送りいたしました。
お手数をおかけいたしますが、内容をご確認いただき、
問題ございませんでしたらご署名のうえ、ご返送いただけますと幸いです🙇‍♀️

ご不明点や修正のご希望等がございましたら、
お気軽にお知らせください😊

何卒よろしくお願い申し上げます。

GROSMIMI JAPAN
```

## 주의사항 (반드시 지킬 것)

1. **DocuSeal 발송 = 세은 승인 필수.** 자동 발송 금지 (feedback_docuseal_approval_required.md)
2. **파일 확장자 = .docx 사용.** PDF 업로드 시 text tag 글자 남음 (이번 실수)
3. **인플루언서에게 요청하는 정보 = 풀네임 + 이메일 2개만.** IG 핸들·송금처 물어보지 말 것 (feedback_contract_info_fullname_email_only.md)
4. **인플루언서가 요청한 색상/제품명은 공식 표기로 변환.** 예: `ベアバター` = ステンレス (PPSU 아님) (feedback_use_official_color_names.md)
5. **계약서 생성 전 deliverables_detail + product_type 필수.** 누락 시 `いずれか` / `例：` 문구 그대로 (feedback_contract_required_fields.md)

## 현재 시스템 상태 (2026-04-22)

- 원본 템플릿 양쪽 (有償/無償): 8-9조 빈줄 삭제 완료 / {{HASHTAGS}} 플레이스홀더 삽입 / 서명 text tag 삽입
- `generate_influencer_contract.py`: {{VAR}} 기반 치환, 필수 필드 검증 (deliverables_detail + product_type)
- `send_docuseal_contract.py`: DOCX 업로드 우선, `--no-send` / `--resend` / `--dry-run` 플래그

## 작동 확인 ID

- Submission 37 (PDF 업로드): heo seeun 테스트 → 서명까지 완료했으나 tag 글자 남음 (레거시)
- Submission 39 (DOCX 업로드): heo seeun 테스트 → 세은 "오오 좋다" 확인. 이게 표준
