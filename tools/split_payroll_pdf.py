"""
split_payroll_pdf.py

세무사가 보내준 전체 직원 급여명세서 PDF를
직원 1명당 1개 파일로 분리합니다.

출력 파일명 형식: {사원명}_{YYMM}_급여명세서.pdf
예시: 유희찬_2601_급여명세서.pdf

사용법:
    py -3 tools/split_payroll_pdf.py <PDF경로>
    py -3 tools/split_payroll_pdf.py "오비터스(주)_1월 급여명세서.pdf"
"""

import sys
import re
import os
from pathlib import Path

# Windows 터미널 한글 출력을 위한 인코딩 설정
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    print("[ERROR] pypdf가 설치되지 않았습니다.")
    print("   설치 명령어: pip install pypdf")
    sys.exit(1)


def extract_info_from_page(page) -> dict:
    """PDF 페이지에서 사원명과 급여 년월을 추출합니다."""
    raw_text = page.extract_text() or ""

    # 문자 사이 공백이 삽입된 PDF 포맷에 대응: 모든 공백 제거 후 패턴 적용
    text = re.sub(r'\s+', '', raw_text)

    # 사원명 추출: "사원명:유희찬"
    name_match = re.search(r'사원명[:：](\S+?)입사일', text)
    if not name_match:
        name_match = re.search(r'사원명[:：](\S+)', text)
    name = name_match.group(1).strip() if name_match else None

    # 년월 추출: "2026년01월분" → "2601"
    date_match = re.search(r'(\d{4})년(\d{2})월분', text)
    if date_match:
        year = date_match.group(1)[2:]   # "2026" → "26"
        month = date_match.group(2)       # "01"
        yymm = f"{year}{month}"
    else:
        yymm = "0000"

    return {"name": name, "yymm": yymm, "text": text}


def split_payroll_pdf(pdf_path: str) -> list:
    """
    전체 급여명세서 PDF를 직원별로 분리합니다.

    Returns:
        저장된 파일 경로 목록
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"[ERROR] 파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    print(f"[OK] 총 {total_pages}페이지 PDF 로드: {pdf_path.name}")

    # 출력 디렉토리 생성
    output_dir = Path(".tmp") / "payroll_split"
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []

    for i, page in enumerate(reader.pages):
        info = extract_info_from_page(page)
        name = info["name"]
        yymm = info["yymm"]

        if not name:
            print(f"  [WARNING] 페이지 {i+1}: 사원명 추출 실패 → page_{i+1:02d}_미확인.pdf")
            name = f"page_{i+1:02d}_미확인"

        filename = f"{name}_{yymm}_급여명세서.pdf"
        output_path = output_dir / filename

        writer = PdfWriter()
        writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)

        saved_files.append(str(output_path))
        print(f"  [{i+1}/{total_pages}] 저장: {filename}")

    print(f"\n[완료] {len(saved_files)}개 파일 생성 → {output_dir}/")
    return saved_files


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: py -3 tools/split_payroll_pdf.py <PDF경로>")
        print("예시:   py -3 tools/split_payroll_pdf.py \"오비터스(주)_1월 급여명세서.pdf\"")
        sys.exit(1)

    pdf_path = sys.argv[1]
    split_payroll_pdf(pdf_path)
