# Gmail RAG (이메일 지니)

Gmail 이메일 이력을 벡터 인덱싱하여 시맨틱 검색, 맥락 기반 이메일 작성, 중복 발송 방지를 지원하는 에이전트.

## Accounts
- `hello@zezebaebae.com` (zezebaebae)
- `affiliates@onzenna.com` (onzenna)

## Commands

### 인덱싱
```bash
python tools/gmail_rag.py --backfill                          # 전체 백필
python tools/gmail_rag.py --backfill --account zezebaebae     # 단일 계정
python tools/gmail_rag.py --sync                              # 증분 동기화
python tools/gmail_rag.py --status                            # 상태 확인
```

### 검색
```bash
python tools/gmail_rag.py --query "sample shipment"           # 시맨틱 검색
python tools/gmail_rag.py --query "commission" --account onzenna  # 계정 필터
python tools/gmail_rag.py --thread "thread_id"                # 스레드 조회
```

### 중복 체크
```bash
python tools/gmail_rag.py --check-contact "email@example.com"
python tools/gmail_rag.py --check-domain "example.com"
```

### 이메일 작성
```bash
python tools/gmail_rag_compose.py --to "email" --intent "의도"
python tools/gmail_rag_compose.py --thread-id "id" --intent "의도"
python tools/gmail_rag_compose.py --to "email" --intent "..." --lang ko
python tools/gmail_rag_compose.py --to "email" --intent "..." --dry-run
```

### 발송 (기존 도구)
```bash
python tools/send_gmail.py --to "email" --subject "Subject" --body-file .tmp/gmail_rag/last_draft.html
```

## Architecture
```
Gmail API → Voyage AI (voyage-3-lite) → ChromaDB (local)
                                         + SQLite (contacts.db)
Query → embed → ChromaDB search → thread expansion → Claude Sonnet draft
```

## Data
- ChromaDB: `.tmp/gmail_rag/chroma_db/`
- Contacts: `.tmp/gmail_rag/contacts.db`
- State: `.tmp/gmail_rag/index_state.json`
- Drafts: `.tmp/gmail_rag/last_draft.html`

## Dependencies
- `chromadb`, `voyageai` (in requirements.txt)
- `VOYAGE_API_KEY`, `ANTHROPIC_API_KEY` (in ~/.wat_secrets)

## Trigger Keywords
이메일 지니, Gmail RAG, 이메일 검색, 이메일 컨텍스트, 이메일 작성, 중복 체크, 이전 이메일, email context, compose email, dedup check


---

## 보고 규칙 (전 에이전트 공통)

세은에게 보고할 때: **표 + 설명 2-3줄**로 끝낸다. 장황한 과정 설명 금지. 결과만 간단명료하게.
