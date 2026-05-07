"""
send_payroll_emails.py

분리된 급여명세서 PDF를 각 직원 이메일로 발송합니다.
Outlook / Microsoft 365 SMTP 사용.

사용법:
    py -3 tools/send_payroll_emails.py .tmp/payroll_split
    py -3 tools/send_payroll_emails.py .tmp/payroll_split --dry-run
    py -3 tools/send_payroll_emails.py .tmp/payroll_split --name 최원준
"""

import sys
import os
import csv
import smtplib
import re
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    from dotenv import load_dotenv
except ImportError:
    print("[ERROR] python-dotenv가 설치되지 않았습니다. pip install python-dotenv")
    sys.exit(1)

load_dotenv()


def load_employees(csv_path: str = "employees.csv") -> dict:
    employees = {}
    csv_file = Path(csv_path)

    if not csv_file.exists():
        print(f"[ERROR] 직원 명단 파일을 찾을 수 없습니다: {csv_path}")
        sys.exit(1)

    with open(csv_file, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("사원명", "").strip()
            email = row.get("이메일", "").strip()
            if name and email:
                employees[name] = email

    print(f"[OK] 직원 명단 로드: {len(employees)}명")
    return employees


def match_pdfs_to_employees(pdf_dir: str, employees: dict) -> list:
    pdf_dir = Path(pdf_dir)
    pdf_files = list(pdf_dir.glob("*_급여명세서.pdf"))

    if not pdf_files:
        print(f"[ERROR] 급여명세서 PDF 파일이 없습니다: {pdf_dir}")
        sys.exit(1)

    matched = []
    unmatched = []

    for pdf_file in sorted(pdf_files):
        parts = pdf_file.stem.split("_")
        name = parts[0] if len(parts) >= 3 else pdf_file.stem

        email = employees.get(name)
        if email:
            matched.append({"name": name, "email": email, "pdf_path": pdf_file})
        else:
            unmatched.append({"name": name, "pdf_path": pdf_file})

    print(f"\n[매칭] 성공: {len(matched)}명 / 실패: {len(unmatched)}명")

    if unmatched:
        print("[WARNING] 이메일 미등록 직원 (employees.csv 확인 필요):")
        for u in unmatched:
            print(f"   - {u['name']} ({u['pdf_path'].name})")

    return matched


def send_email(smtp, sender_email: str, recipient: dict, dry_run: bool = False):
    name = recipient["name"]
    email = recipient["email"]
    pdf_path = recipient["pdf_path"]
    filename = pdf_path.name

    match = re.search(r'_(\d{2})(\d{2})_', filename)
    year_str = f"20{match.group(1)}년 {match.group(2)}월" if match else "이번달"

    subject = f"[오비터스] {year_str}분 급여명세서"
    body = f"""{name} 님,

안녕하세요. 오비터스 경영지원팀입니다.

{year_str}분 급여명세서를 첨부 파일로 보내드립니다.
확인 후 문의사항이 있으시면 연락주세요.

감사합니다.
오비터스주식회사"""

    if dry_run:
        print(f"   [DRY-RUN] {name} → {email} | {filename}")
        return True

    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{filename}"
            )
            msg.attach(part)

        smtp.sendmail(sender_email, email, msg.as_string())
        print(f"   [OK] {name} → {email}")
        return True

    except Exception as e:
        print(f"   [FAIL] {name} → {email} | {e}")
        return False


def send_all_payroll_emails(pdf_dir: str, dry_run: bool = False, name_filter: str = None):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.office365.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not sender_email or not sender_password:
        print("[ERROR] .env에 SENDER_EMAIL, SENDER_PASSWORD를 설정해주세요.")
        sys.exit(1)

    employees = load_employees()
    recipients = match_pdfs_to_employees(pdf_dir, employees)

    if name_filter:
        recipients = [r for r in recipients if r["name"] == name_filter]
        if not recipients:
            print(f"[ERROR] '{name_filter}' 직원을 찾을 수 없습니다.")
            sys.exit(1)
        print(f"[필터] '{name_filter}'에게만 발송합니다.")

    if not recipients:
        print("[ERROR] 발송 대상이 없습니다.")
        sys.exit(1)

    if dry_run:
        print(f"\n[DRY-RUN] 실제 발송 안함:")
        for r in recipients:
            send_email(None, sender_email, r, dry_run=True)
        print(f"\n총 {len(recipients)}명에게 발송 예정.")
        return

    print(f"\n[발송 시작] SMTP: {smtp_server}:{smtp_port}")
    success = 0
    fail = 0

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(sender_email, sender_password)
            print(f"[OK] SMTP 로그인 성공: {sender_email}\n")

            for recipient in recipients:
                if send_email(smtp, sender_email, recipient):
                    success += 1
                else:
                    fail += 1

    except smtplib.SMTPAuthenticationError:
        print("[ERROR] SMTP 인증 실패. 계정/비밀번호 확인 또는 SMTP AUTH 활성화 필요.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] SMTP 연결 오류: {e}")
        sys.exit(1)

    print(f"\n{'='*40}")
    print(f"발송 성공: {success}명")
    if fail:
        print(f"발송 실패: {fail}명")
    print(f"{'='*40}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: py -3 tools/send_payroll_emails.py <PDF폴더> [--dry-run] [--name 이름]")
        sys.exit(1)

    pdf_dir = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    name_filter = None
    if "--name" in sys.argv:
        idx = sys.argv.index("--name")
        if idx + 1 < len(sys.argv):
            name_filter = sys.argv[idx + 1]

    send_all_payroll_emails(pdf_dir, dry_run=dry_run, name_filter=name_filter)
