# Gmail RAG Workflow

## Objective
이메일 이력을 시맨틱 검색으로 인덱싱하여, 맥락 기반 이메일 작성 및 중복 발송 방지를 지원한다.

## Accounts
| Account | Email | Token |
|---------|-------|-------|
| zezebaebae | hello@zezebaebae.com | `credentials/zezebaebae_gmail_token.json` |
| onzenna | affiliates@onzenna.com | `credentials/onzenna_gmail_token.json` |

## Prerequisites
- `VOYAGE_API_KEY` in `~/.wat_secrets`
- `ANTHROPIC_API_KEY` in `~/.wat_secrets`
- Gmail OAuth credentials in `credentials/`
- `pip install chromadb voyageai`

## Initial Setup (1회)

### 1. Voyage API Key 설정
```bash
echo "VOYAGE_API_KEY=pa-xxxxxxxxxx" >> ~/.wat_secrets
```

### 2. onzenna 계정 OAuth 인증 (최초 1회)
```bash
python tools/gmail_rag.py --backfill --account onzenna --max-results 1
# 브라우저에서 affiliates@onzenna.com 로그인
```

### 3. Full Backfill
```bash
# 전체 인덱싱 (두 계정 모두)
python tools/gmail_rag.py --backfill

# 특정 계정만
python tools/gmail_rag.py --backfill --account zezebaebae
```

## Daily Operations

### 증분 동기화
```bash
python tools/gmail_rag.py --sync
```

### 이메일 검색 (시맨틱)
```bash
python tools/gmail_rag.py --query "influencer commission rates"
python tools/gmail_rag.py --query "sample shipment delay" --account onzenna
```

### 중복 체크
```bash
python tools/gmail_rag.py --check-contact "jane@example.com"
python tools/gmail_rag.py --check-domain "example.com"
```

### 맥락 기반 이메일 작성
```bash
# 새 이메일
python tools/gmail_rag_compose.py --to "jane@example.com" --intent "Follow up on sample delivery"

# 스레드 답장
python tools/gmail_rag_compose.py --thread-id "abc123" --intent "Reply about commission"

# 한국어
python tools/gmail_rag_compose.py --to "email" --intent "..." --lang ko

# 미리보기만
python tools/gmail_rag_compose.py --to "email" --intent "..." --dry-run
```

### 작성 후 발송
```bash
python tools/send_gmail.py --to "jane@example.com" --subject "Subject" --body-file .tmp/gmail_rag/last_draft.html
```

## Data Storage
| 파일 | 위치 | 설명 |
|------|------|------|
| ChromaDB | `.tmp/gmail_rag/chroma_db/` | 벡터 인덱스 |
| Contacts DB | `.tmp/gmail_rag/contacts.db` | SQLite 연락처 |
| Index State | `.tmp/gmail_rag/index_state.json` | 동기화 상태 |
| Last Draft | `.tmp/gmail_rag/last_draft.html` | 최근 작성 초안 |

## Edge Cases
- **OAuth 만료**: 토큰 자동 갱신. 리프레시 토큰이 revoke되면 브라우저 재인증 필요
- **대용량 메일**: 본문 8000자 잘림. 첨부파일은 인덱싱하지 않음
- **Rate Limit**: Gmail API 429 → 자동 재시도 (backfill 시 배치 간 0.5초 대기)
- **다국어**: Voyage AI voyage-3-lite가 영어/한국어/일본어 모두 지원

## Tools
| Tool | Role |
|------|------|
| `tools/gmail_rag.py` | 인덱싱, 검색, 중복체크 |
| `tools/gmail_rag_compose.py` | 맥락 기반 이메일 초안 생성 |
| `tools/send_gmail.py` | 이메일 발송 (기존) |
