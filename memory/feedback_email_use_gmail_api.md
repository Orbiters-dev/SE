---
name: 이메일 발송은 Gmail API로 (SMTP/PW 금지)
description: 이메일 발송 시 SMTP 비밀번호 방식 금지. tools/send_gmail.py (Gmail API OAuth) 사용. 세은 반복 지시.
type: feedback
---

이메일 발송은 **반드시 Gmail API (`tools/send_gmail.py`)**로.
SMTP 비밀번호(SENDER_PASSWORD) 사용 금지.

**Why:** 2026-04-24 세은 "야 PW가 아니라 api로 보내라고 몇 번 처 말함? 진짜 미쳤네". `.env`의 SENDER_PASSWORD가 비어있는데도 SMTP 시도해서 실패 보고함. send_gmail.py가 OAuth 토큰으로 이미 동작 중이었음.

**How to apply:**
- `python tools/send_gmail.py --to <addr> --subject <s> --body <html>` 사용
- `--body-file <path>` 로 HTML 파일 전송 가능
- `--attachment <path>` 로 첨부 가능
- SENDER_EMAIL/SENDER_PASSWORD/SMTP_SERVER 같은 환경변수 의존 금지
- credentials/gmail_oauth_credentials.json + gmail_token.json 으로 인증 (이미 설정됨)
- 발신자: orbiters11@gmail.com (DEFAULT_SENDER)
