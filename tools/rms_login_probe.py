#!/usr/bin/env python3
"""RMS 로그인 프로브 — 새 IP(EC2/CI 데이터센터)에서 라쿠텐 RMS 자동 로그인이 성립하는지 1회 실측.

tools/rms_review_playwright.py do_login() 의 Step1~4 를 headless 로 재현하고,
각 단계 스크린샷 + 최종 판정(result.json)을 남긴다. 비밀번호는 어떤 출력에도 찍지 않는다.
재시도 루프 없음 — 계정 보호를 위해 실행당 로그인 시도 1회.

Usage: RAKUTEN_* env 세팅 후  python tools/rms_login_probe.py --out out
"""
import argparse
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

RMS_LOGIN_ID = os.getenv("RAKUTEN_RMS_LOGIN_ID", "")
RMS_LOGIN_PASS = os.getenv("RAKUTEN_RMS_LOGIN_PASSWORD", "")
SSO_USERNAME = os.getenv("RAKUTEN_SSO_USERNAME", "") or os.getenv("RAKUTEN_SSO_ID", "")
SSO_PASSWORD = os.getenv("RAKUTEN_SSO_PASSWORD", "")

MARKERS = {
    "OTP_OR_VERIFY": ["ワンタイム", "認証コード", "確認コード", "verification code", "本人確認", "追加認証"],
    "CAPTCHA": ["captcha", "キャプチャ", "画像認証"],
    "DENIED": ["access denied", "アクセスが拒否", "403 forbidden", "not authorized"],
    "ERROR_PAGE": ["エラーが発生", "しばらくしてから", "メンテナンス"],
}


def page_signals(page):
    url = page.url
    title = ""
    body = ""
    try:
        title = page.title()
    except Exception:
        pass
    try:
        body = page.inner_text("body", timeout=3000)[:6000]
    except Exception:
        pass
    low = (body + " " + title).lower()
    hits = []
    for label, words in MARKERS.items():
        if any(w.lower() in low for w in words):
            hits.append(label)
    return {"url": url, "title": title, "markers": hits, "body_head": body[:800]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    missing = [k for k, v in (
        ("RAKUTEN_RMS_LOGIN_ID", RMS_LOGIN_ID),
        ("RAKUTEN_RMS_LOGIN_PASSWORD", RMS_LOGIN_PASS),
        ("RAKUTEN_SSO_USERNAME/ID", SSO_USERNAME),
        ("RAKUTEN_SSO_PASSWORD", SSO_PASSWORD),
    ) if not v]
    if missing:
        print(f"missing env: {missing}", file=sys.stderr)
        sys.exit(2)

    result = {"outcome": "UNKNOWN", "step_reached": 0, "steps": []}

    def snap(page, step, note):
        try:
            page.screenshot(path=os.path.join(args.out, f"step{step}.png"), full_page=False)
        except Exception:
            pass
        sig = page_signals(page)
        sig["step"] = step
        sig["note"] = note
        result["steps"].append(sig)
        result["step_reached"] = step
        print(f"  step{step} [{note}] url={sig['url']} markers={sig['markers']}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        try:
            print("Step1: RMS 로그인 폼")
            page.goto("https://glogin.rms.rakuten.co.jp", wait_until="domcontentloaded", timeout=45000)
            time.sleep(2)
            page.fill("#rlogin-username-ja", RMS_LOGIN_ID)
            page.fill("#rlogin-password-ja", RMS_LOGIN_PASS)
            page.click("button.rf-button-primary")
            time.sleep(4)
            snap(page, 1, "after rms form submit")

            print("Step2: Rakuten Account SSO")
            page.fill('input[name="username"]', SSO_USERNAME, timeout=15000)
            page.press('input[name="username"]', "Enter")
            time.sleep(3)
            page.locator('input[name="password"]').click(timeout=15000)
            page.keyboard.type(SSO_PASSWORD)
            page.keyboard.press("Enter")
            try:
                page.wait_for_url("https://glogin.rms.rakuten.co.jp/**", timeout=30000)
            except PWTimeout:
                snap(page, 2, "SSO did not return to glogin (verify/otp/captcha?)")
                raise
            time.sleep(2)
            snap(page, 2, "back on glogin after SSO")

            print("Step3: 통지 페이지 next")
            page.locator("button.rf-button-primary").first.click(timeout=15000)
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            time.sleep(3)
            snap(page, 3, "after notice next")

            print("Step4: RMS 링크 클릭")
            page.click('a[href*="mainmenu.rms.rakuten.co.jp"]', timeout=30000)
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            time.sleep(2)
            snap(page, 4, "after RMS link")

            if "mainmenu.rms.rakuten.co.jp" in page.url:
                result["outcome"] = "SUCCESS_RMS"
            else:
                result["outcome"] = "REACHED_STEP4_URL_MISMATCH"
        except Exception as e:
            snap(page, result["step_reached"] + 1 if result["step_reached"] < 4 else 4, f"exception: {type(e).__name__}")
            last = result["steps"][-1]["markers"] if result["steps"] else []
            if "OTP_OR_VERIFY" in last:
                result["outcome"] = "BLOCKED_OTP_OR_VERIFY"
            elif "CAPTCHA" in last:
                result["outcome"] = "BLOCKED_CAPTCHA"
            elif "DENIED" in last:
                result["outcome"] = "BLOCKED_DENIED"
            elif "ERROR_PAGE" in last:
                result["outcome"] = "RAKUTEN_ERROR_PAGE"
            else:
                result["outcome"] = f"FAIL_{type(e).__name__}"
            result["error"] = str(e)[:500]
        finally:
            browser.close()

    with open(os.path.join(args.out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"OUTCOME: {result['outcome']} (step {result['step_reached']})")
    sys.exit(0 if result["outcome"] == "SUCCESS_RMS" else 1)


if __name__ == "__main__":
    main()
