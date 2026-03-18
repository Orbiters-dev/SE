"""
Gmail RAG Compose - Context-aware email drafting with duplicate detection.

Uses past email history (via gmail_rag.py) + Claude Sonnet to draft replies.

Usage:
    python tools/gmail_rag_compose.py --to "jane@example.com" --intent "Follow up on sample shipment"
    python tools/gmail_rag_compose.py --thread-id "abc123" --intent "Reply about commission"
    python tools/gmail_rag_compose.py --to "email" --intent "..." --dry-run
    python tools/gmail_rag_compose.py --to "email" --intent "..." --account onzenna
    python tools/gmail_rag_compose.py --to "email" --intent "..." --lang ko  # Korean draft
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from env_loader import load_env
load_env()

from anthropic import Anthropic
from gmail_rag import (
    ACCOUNTS, RAG_DIR,
    query_emails, get_thread_messages, check_contact, check_domain,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
COMPOSE_MODEL = "claude-sonnet-4-20250514"


# ── System Prompts ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an email assistant for ORBI (Orbiters Co., Ltd.), a Korean baby product company.

ORBI operates these brands in the US market:
- Grosmimi (PPSU baby bottles, straw cups, tumblers)
- Onzenna / zezebaebae (DTC brand on onzenna.com)
- Naeiae (baby snacks, sold on Amazon)
- CHA&MOM (mother care products)

Email accounts:
- hello@zezebaebae.com — general inquiries, influencer outreach
- affiliates@onzenna.com — affiliate/influencer program

Your job:
1. Draft professional, concise emails
2. Match the tone/style of past conversations when available
3. Maintain continuity with previous threads
4. Never disclose internal terminology (High Touch/Low Touch tiers) to external contacts
5. Be warm but professional — this is a baby products brand

Format: Return ONLY the email content. No meta-commentary.
If the recipient has been contacted before, acknowledge the prior relationship naturally.
"""

SYSTEM_PROMPT_KO = """당신은 ORBI(오비터스 주식회사)의 이메일 작성 어시스턴트입니다.

ORBI 브랜드:
- 그로미미 (Grosmimi) — PPSU 아기 젖병, 빨대컵, 텀블러
- 온젠나 (Onzenna / zezebaebae) — DTC 브랜드
- 내아이애 (Naeiae) — 아기 간식, Amazon 판매
- 차앤맘 (CHA&MOM) — 산모용품

이메일 계정:
- hello@zezebaebae.com — 일반 문의, 인플루언서 아웃리치
- affiliates@onzenna.com — 제휴/인플루언서 프로그램

규칙:
1. 간결하고 프로페셔널한 이메일 작성
2. 과거 대화 톤/스타일 맞추기
3. 내부 용어(High Touch/Low Touch) 외부 노출 금지
4. 따뜻하지만 전문적인 톤

형식: 이메일 본문만 반환. 메타 코멘트 없이.
"""


# ── Compose Logic ──────────────────────────────────────────────────────────────

def build_context(to_email: str = None, thread_id: str = None,
                  intent: str = "", account: str = None, top_k: int = 7) -> dict:
    """Build context for email drafting."""
    context = {
        "contact_history": None,
        "domain_contacts": [],
        "relevant_emails": [],
        "thread_messages": [],
        "duplicate_warning": False,
    }

    # 1. Check contact history
    if to_email:
        contact = check_contact(to_email)
        if contact:
            context["contact_history"] = contact
            if contact["total_sent"] > 0:
                context["duplicate_warning"] = True

        domain = to_email.split("@")[-1] if "@" in to_email else ""
        if domain:
            context["domain_contacts"] = check_domain(domain)

    # 2. Get thread context
    if thread_id:
        context["thread_messages"] = get_thread_messages(thread_id)

    # 3. Semantic search for relevant past emails
    search_parts = []
    if intent:
        search_parts.append(intent)
    if to_email:
        search_parts.append(to_email)

    if search_parts:
        search_query = " ".join(search_parts)
        try:
            context["relevant_emails"] = query_emails(
                search_query, top_k=top_k, account_filter=account
            )
        except Exception as e:
            print(f"  WARN: Search failed: {e}")

    return context


def format_context_for_claude(context: dict) -> str:
    """Format retrieved context into a prompt section."""
    sections = []

    # Contact history
    if context["contact_history"]:
        c = context["contact_history"]
        sections.append(f"""## Contact History
- Email: {c['email']}
- Name: {c['name']}
- First contact: {c['first_contact_date']}
- Last contact: {c['last_contact_date']}
- Last subject: {c['last_subject']}
- Emails sent to them: {c['total_sent']}
- Emails received from them: {c['total_received']}""")

    # Domain contacts
    if len(context["domain_contacts"]) > 1:
        lines = ["## Other contacts at same domain"]
        for dc in context["domain_contacts"][:5]:
            lines.append(f"- {dc['email']} ({dc['name']}) — sent:{dc['total_sent']} recv:{dc['total_received']}")
        sections.append("\n".join(lines))

    # Thread messages
    if context["thread_messages"]:
        lines = ["## Current Thread (chronological)"]
        for m in context["thread_messages"][-5:]:  # Last 5 messages in thread
            lines.append(f"\n### [{m['direction'].upper()}] {m['from_email']} → {m['to_email']}")
            lines.append(f"Date: {m['date']}")
            lines.append(m["document"][:2000])
        sections.append("\n".join(lines))

    # Relevant past emails
    if context["relevant_emails"]:
        lines = ["## Relevant Past Emails (by similarity)"]
        for r in context["relevant_emails"][:5]:
            score = 1 - r["distance"]
            lines.append(f"\n### [{r['direction'].upper()}] Score: {score:.2f}")
            lines.append(f"Subject: {r['subject']}")
            lines.append(f"From: {r['from_email']} → To: {r['to_email']}")
            lines.append(f"Date: {r['date']}")
            lines.append(r["snippet"][:500])
        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else "(No prior context found)"


def compose_draft(to_email: str = None, thread_id: str = None,
                  intent: str = "", account: str = None,
                  lang: str = "en", dry_run: bool = False) -> dict:
    """Compose an email draft with RAG context."""

    print("Building context...")
    context = build_context(to_email, thread_id, intent, account)

    # Duplicate warning
    if context["duplicate_warning"]:
        c = context["contact_history"]
        print(f"\n  WARNING: Already contacted {to_email}")
        print(f"    Last contact: {c['last_contact_date']}")
        print(f"    Last subject: {c['last_subject']}")
        print(f"    Total sent: {c['total_sent']}")
        print()

    context_text = format_context_for_claude(context)

    # Determine sender
    sender = "hello@zezebaebae.com"
    if account and account in ACCOUNTS:
        sender = ACCOUNTS[account]["email"]

    # Build prompt
    system = SYSTEM_PROMPT_KO if lang == "ko" else SYSTEM_PROMPT

    user_prompt = f"""## Task
Draft an email {"reply" if thread_id else "message"}.

## Sender
{sender}

## Recipient
{to_email or "(see thread)"}

## Intent
{intent}

## Retrieved Context
{context_text}

## Instructions
- {"Reply in the context of the thread above" if thread_id else "Compose a new email"}
- Output format: First line is Subject, then blank line, then body
- Body should be HTML-ready (use <br> for line breaks if needed, or plain text is fine)
- Be concise (3-7 sentences unless more detail is needed)
- {"Write in Korean" if lang == "ko" else "Write in English"}
"""

    if dry_run:
        print("\n=== DRY RUN — Context that would be sent to Claude ===\n")
        print(f"System prompt: {len(system)} chars")
        print(f"User prompt: {len(user_prompt)} chars")
        print(f"\n--- User Prompt ---\n{user_prompt}")
        return {"dry_run": True, "context": context}

    # Call Claude
    print("Generating draft with Claude Sonnet...")
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=COMPOSE_MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )

    draft_text = response.content[0].text

    # Parse subject and body
    lines = draft_text.strip().split("\n", 1)
    subject = lines[0].replace("Subject: ", "").replace("Subject:", "").strip()
    body = lines[1].strip() if len(lines) > 1 else ""

    result = {
        "to": to_email,
        "sender": sender,
        "subject": subject,
        "body": body,
        "context_used": {
            "contact_found": context["contact_history"] is not None,
            "duplicate_warning": context["duplicate_warning"],
            "relevant_emails_count": len(context["relevant_emails"]),
            "thread_messages_count": len(context["thread_messages"]),
        },
        "model": COMPOSE_MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Save draft
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    draft_path = RAG_DIR / "last_draft.json"
    draft_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save HTML version
    html_path = RAG_DIR / "last_draft.html"
    html_path.write_text(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Email Draft</title>
<style>body{{font-family:Arial,sans-serif;max-width:700px;margin:40px auto;padding:20px}}
.meta{{color:#666;font-size:13px;margin-bottom:20px}}
.warning{{background:#fff3cd;border:1px solid #ffc107;padding:10px;border-radius:4px;margin-bottom:15px}}
.body{{white-space:pre-wrap;line-height:1.6}}</style></head>
<body>
<h2>Email Draft</h2>
{"<div class='warning'>DUPLICATE WARNING: Already contacted this address</div>" if context["duplicate_warning"] else ""}
<div class="meta">
  <b>From:</b> {sender}<br>
  <b>To:</b> {to_email or "N/A"}<br>
  <b>Subject:</b> {subject}<br>
  <b>Generated:</b> {result['timestamp']}<br>
  <b>Context:</b> {result['context_used']['relevant_emails_count']} relevant emails,
  {result['context_used']['thread_messages_count']} thread messages
</div>
<hr>
<div class="body">{body}</div>
</body></html>""", encoding="utf-8")

    # Print result
    print(f"\n{'='*60}")
    print(f"  From:    {sender}")
    print(f"  To:      {to_email or 'N/A'}")
    print(f"  Subject: {subject}")
    print(f"{'='*60}")
    print(f"\n{body}\n")
    print(f"{'='*60}")
    print(f"  Draft saved: {draft_path}")
    print(f"  HTML:        {html_path}")
    if context["duplicate_warning"]:
        print(f"  WARNING: Duplicate contact detected!")
    print(f"  Context: {result['context_used']['relevant_emails_count']} emails, "
          f"{result['context_used']['thread_messages_count']} thread msgs")
    print()
    print("  To send: python tools/send_gmail.py --to \"...\" --subject \"...\" --body-file .tmp/gmail_rag/last_draft.html")

    return result


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gmail RAG Compose - Context-aware email drafting")
    parser.add_argument("--to", type=str, help="Recipient email address")
    parser.add_argument("--thread-id", type=str, help="Reply to specific thread")
    parser.add_argument("--intent", type=str, required=True, help="What you want to say/achieve")
    parser.add_argument("--account", type=str, choices=list(ACCOUNTS.keys()),
                        help="Send from specific account (default: zezebaebae)")
    parser.add_argument("--lang", type=str, default="en", choices=["en", "ko", "ja"],
                        help="Language for draft")
    parser.add_argument("--dry-run", action="store_true", help="Preview context without generating")
    parser.add_argument("--top-k", type=int, default=7, help="Number of context emails to retrieve")
    args = parser.parse_args()

    if not args.to and not args.thread_id:
        print("ERROR: Provide --to or --thread-id")
        sys.exit(1)

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in ~/.wat_secrets")
        sys.exit(1)

    compose_draft(
        to_email=args.to,
        thread_id=args.thread_id,
        intent=args.intent,
        account=args.account,
        lang=args.lang,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
