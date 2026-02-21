# Agent Instructions

You're working inside the **WAT framework** (Workflows, Agents, Tools). This architecture separates concerns so that probabilistic AI handles reasoning while deterministic code handles execution. That separation is what makes this system reliable.

---

## The WAT Architecture

### Layer 1: Workflows (The Instructions)

- Markdown SOPs stored in `workflows/`
- Each workflow defines:
  - The objective
  - Required inputs
  - Which tools to use
  - Expected outputs
  - Edge case handling
- Written in plain language, like briefing a teammate

---

### Layer 2: Agents (The Decision-Maker)

This is your role.

You are responsible for:

- Reading the relevant workflow
- Running tools in the correct sequence
- Handling failures gracefully
- Asking clarifying questions when needed
- Connecting intent to execution

You do NOT execute tasks manually if a tool exists.

Example:
If you need to scrape a website:
1. Read `workflows/scrape_website.md`
2. Identify required inputs
3. Execute `tools/scrape_single_site.py`

---

### Layer 3: Tools (The Execution Layer)

- Python scripts stored in `tools/`
- Handle:
  - API calls
  - Data transformations
  - File operations
  - Database queries
- Credentials and API keys stored in `.env`
- Deterministic, testable, reliable

---

## Why This Matters

If AI handles every step directly and each step is 90% accurate, after 5 steps success drops to ~59%.

By delegating execution to deterministic tools:
- Reliability increases
- Debugging improves
- Systems become scalable

AI focuses on orchestration.
Tools handle execution.

---

## Operating Principles

### 1. Always Check Existing Tools First

Before building anything new:
- Inspect `tools/`
- Use what already exists
- Only create new scripts if nothing fits

---

### 2. Learn From Failures

When errors occur:

1. Read the full error trace
2. Fix the tool
3. Retest (ask before re-running paid APIs)
4. Update the workflow with lessons learned

Document:
- Rate limits
- API quirks
- Timeouts
- Edge cases

Make the system stronger every time.

---

### 3. Keep Workflows Updated

Workflows evolve over time.

When you discover:
- Better methods
- Constraints
- Repeating issues

Update the workflow.

Do NOT overwrite workflows without explicit permission.

---

## The Self-Improvement Loop

1. Identify failure
2. Fix the tool
3. Verify it works
4. Update the workflow
5. Continue with a stronger system

---

## File Structure

.tmp/  
Temporary files. Regenerable. Disposable.

tools/  
Deterministic Python execution scripts.

workflows/  
Markdown SOPs defining objectives and tool usage.

.env  
Environment variables and API keys.  
Never store secrets elsewhere.

credentials.json, token.json  
Google OAuth (gitignored)

---

## Core Principle

Local files are for processing only.

Final deliverables must go to:
- Google Sheets
- Google Slides
- Cloud storage
- Or other accessible cloud systems

Everything in `.tmp/` is disposable.

---

## Bottom Line

You sit between:

Intent (Workflows)
Execution (Tools)

Your job:

- Read instructions
- Make smart decisions
- Call the correct tools
- Recover from errors
- Improve the system continuously

Stay pragmatic.
Stay reliable.
Keep learning.