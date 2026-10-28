# -*- coding: utf-8 -*-
"""
투고완료 폼 업로드 영상 자동 개명 (SA 폴링 방식 — Apps Script 불요)
=================================================================
규칙: YYYYMMDD(투고일)_{stainless|fliptop|ppsu}_@핸들[_(n)].ext (소문자)
스코프: 투고완료 탭 F열(動画の元データ)에 링크된 파일 ID만 —
        응답 폴더의 폼 외 파일(수동 아카이브 등)은 건드리지 않음.
멱등: 목표 파일명과 이미 일치하면 스킵. 매 실행 전량 재스캔이라 밀린 것도 캐치업.

실행: python -X utf8 tools/rename_form_uploads.py [--dry-run]
스케줄: Task Scheduler 'InfluencerFormUploadRename' (매시 :35)
"""
import os
import re
import sys
import time
import argparse

sys.stdout.reconfigure(encoding="utf-8")

from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_PATH = os.environ.get(
    "GOOGLE_SA_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "credentials", "google_service_account.json"))
SHEET_ID = "1Gd8JrWm-nOzscmL2tPLTW23EoC_QGtA07C0xMY6Jr8E"
TOKOU_TAB = "투고완료"
BASIC_TAB = "기본정보"

# 투고완료 탭 컬럼 (0-base): A=Timestamp B=お名前 D=投稿日 F=動画の元データ L=お受け取り商品(조합)
COL_TS, COL_NAME, COL_POST_DATE, COL_FILES, COL_PRODUCT = 0, 1, 3, 5, 11

FILE_ID_RE = re.compile(r"[?&]id=([-\w]{20,})|/d/([-\w]{20,})")


def product_key(s):
    # rename_uploads.gs와 동일한 우선순위
    if not s:
        return "unknown"
    if "ステンレス" in s:
        return "stainless"
    if "ワンタッチ" in s:
        return "fliptop"
    if "PPSU" in s:
        return "ppsu"
    return "unknown"


def norm_name(s):
    return re.sub(r"[\s　]", "", str(s or ""))


def parse_ymd(s):
    """'8/24/2026' 또는 '2026-08-24' → '20260824'. 실패 시 ''"""
    s = str(s or "").strip().split(" ")[0]
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        return f"{m.group(3)}{int(m.group(1)):02d}{int(m.group(2)):02d}"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    return ""


def extract_handle(cell):
    """기본정보 C열 → IG 핸들 (첫 줄, @/＠/URL 제거)"""
    first = str(cell or "").strip().split("\n")[0]
    first = re.sub(r"^.*instagram\.com/", "", first)
    first = re.sub(r"^[@＠\s　]+", "", first)
    first = re.sub(r"[/?\s　].*$", "", first)
    return first.strip()


def sanitize(s):
    """파일명에 부적합한 문자 제거"""
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", str(s))


def with_retry(fn, attempts=3):
    """일시적 API 오류(quota/5xx/네트워크)만 재시도 — 지수 백오프. 그 외 예외는 즉시 전파."""
    from googleapiclient.errors import HttpError
    for a in range(attempts):
        try:
            return fn()
        except HttpError as e:
            if e.resp.status not in (429, 500, 502, 503, 504) or a == attempts - 1:
                raise
            print(f"[retry {a + 1}] HTTP {e.resp.status}")
            time.sleep(2 ** a)
        except OSError as e:
            if a == attempts - 1:
                raise
            print(f"[retry {a + 1}] {e}")
            time.sleep(2 ** a)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    creds = service_account.Credentials.from_service_account_file(
        SA_PATH, scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive",
        ])
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    tokou = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"'{TOKOU_TAB}'!A2:L",
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [])
    basic = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"'{BASIC_TAB}'!B2:C",
        valueRenderOption="FORMATTED_VALUE").execute().get("values", [])

    handle_by_name = {}
    for row in basic:
        if len(row) >= 2 and row[0]:
            h = extract_handle(row[1])
            if h:
                handle_by_name.setdefault(norm_name(row[0]), h)

    assigned = set()  # 이번 실행에서 배정한 목표명 (행 간 충돌 방지)
    renamed = skipped = failed = 0

    def cell(row, i):
        return row[i] if i < len(row) else ""

    for row in tokou:
        name = cell(row, COL_NAME)
        post_date = cell(row, COL_POST_DATE)
        f_cell = cell(row, COL_FILES)
        product = cell(row, COL_PRODUCT)
        ids = [a or b for a, b in FILE_ID_RE.findall(str(f_cell or ""))]
        if not ids:
            continue

        ymd = parse_ymd(post_date) or parse_ymd(cell(row, COL_TS))
        if not ymd:
            print(f"[skip-row] 날짜 파싱 실패: {name} / {post_date!r}")
            continue
        prod = product_key(product)
        handle = handle_by_name.get(norm_name(name))

        for i, fid in enumerate(ids):
            try:
                f = with_retry(lambda: drive.files().get(
                    fileId=fid, fields="name,capabilities(canRename)",
                    supportsAllDrives=True).execute())
            except Exception as e:
                print(f"[fail] 조회 실패 {fid}: {e}")
                failed += 1
                continue
            cur = f["name"]
            m = re.search(r"\.[A-Za-z0-9]+$", cur)
            ext = m.group(0).lower() if m else ""
            if handle:
                tag = sanitize(f"@{handle}")
            else:
                # 폼1 미제출 등 핸들 미해결 — 기존 파일명에 수동 기입된 @핸들이 있으면 존중
                m2 = re.search(r"_(@[\w.\-]+?)(?:_\(\d+\))?(?:\.[A-Za-z0-9]+)?$", cur)
                tag = m2.group(1) if m2 else sanitize(norm_name(name))
            base = f"{ymd}_{prod}_{tag}"
            suffix = f"_({i + 1})" if len(ids) > 1 else ""
            target = f"{base}{suffix}{ext}"
            n = 1
            while target in assigned:  # 동일인 동일날 별도 제출 행 충돌 회피
                n += 1
                target = f"{base}{suffix}_v{n}{ext}"
            assigned.add(target)
            if cur == target:
                skipped += 1
                continue
            if not f.get("capabilities", {}).get("canRename"):
                print(f"[fail] canRename=False: {cur}")
                failed += 1
                continue
            if args.dry_run:
                print(f"[dry] {cur} → {target}")
                renamed += 1
                continue
            try:
                with_retry(lambda: drive.files().update(
                    fileId=fid, body={"name": target},
                    supportsAllDrives=True).execute())
                print(f"[ok] {cur} → {target}")
                renamed += 1
            except Exception as e:
                print(f"[fail] rename 실패 {fid}: {e}")
                failed += 1

    print(f"완료: renamed={renamed} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
