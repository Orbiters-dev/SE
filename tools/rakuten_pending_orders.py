"""RMS 発送待ち (ORDER_PROGRESS=300) 페이지 → KSE row 형식 주문 리스트 반환.

kse_order_summary.build_summary 와 호환되는 dict 리스트를 반환한다.
"""
import io
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "tools"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from rakuten_check_processing import login_rms

PENDING_LIST_URL = (
    "https://order-rp.rms.rakuten.co.jp/order-rb/order-list-sc/init"
    "?&SEARCH_MODE=1&ORDER_PROGRESS=300&DISPLAY_MODE=0"
)
DETAIL_URL = (
    "https://order-rp.rms.rakuten.co.jp/order-rb/individual-order-detail-sc/init"
    "?orderNumber={order_no}"
)

TMP = ROOT / ".tmp"

# ── 일본어 → 영어 카테고리 키워드 변환 (kse_order_summary.classify_product 호환용) ──
# build_summary는 itemTitleKr lower-case 영문 키워드로 분류한다.
def _normalize_title(jp_title: str, jp_option: str) -> str:
    """일본어 상품명 + 옵션 → 영어 키워드 + 사이즈가 들어간 정규화 상품명.

    classify_product 가 잡을 수 있는 영문 키워드 ("stainless", "ppsu", "ワンタッチ" 등) 와
    실제 사이즈 (옵션의 サイズ:NNNml 우선) 를 결합한다.
    """
    parts: list[str] = []
    title = jp_title or ""

    # 카테고리 키워드
    if "ステンレス" in title or "stainless" in title.lower():
        parts.append("Stainless")
    if "ppsu" in title.lower() or "ＰＰＳＵ" in title:
        parts.append("PPSU")
    if "ワンタッチ" in title or "Flip" in title or "one touch" in title.lower():
        parts.append("ワンタッチ")
    if "ストロー" in title or "straw" in title.lower():
        parts.append("Straw")
    if "Replacement" in title or "交換用ストロー" in title:
        parts.append("Replacement Straw")
    if "Silicone" in title or "シリコン" in title:
        if "nipple" in title.lower() or "乳首" in title:
            parts.append("Silicone Nipple")

    # 사이즈: 옵션의 サイズ:NNNml / 容量:NNNml 우선, 없으면 상품명에서
    size_m = re.search(r"(?:サイズ|容量)\s*[:：]\s*(\d+)\s*ml", jp_option or "", re.IGNORECASE)
    if not size_m:
        # 상품명에 단일 사이즈만 있을 때 (예: "300ml") — "200ml / 300ml" 같은 다중은 무시
        sizes = re.findall(r"(\d+)\s*ml", title, re.IGNORECASE)
        size = sizes[0] if len(sizes) == 1 else None
    else:
        size = size_m.group(1)
    if size:
        parts.append(f"{size}ml")

    return " ".join(parts) if parts else title


def fetch_pending_orders(headless: bool = True) -> list[dict]:
    """RMS 발송대기 주문 → KSE row 호환 dict 리스트."""
    from playwright.sync_api import sync_playwright

    rows: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=200)
        context = browser.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        try:
            print("[Rakuten] RMS 로그인...")
            if not login_rms(page):
                print(f"  [ERROR] 로그인 실패: {page.url}")
                return rows
            print(f"  로그인 OK")

            print(f"[Rakuten] 発送待ち 리스트 이동...")
            page.goto(PENDING_LIST_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            html = page.content()

            # 주문번호 수집
            order_nums = sorted(set(re.findall(r"\d{6}-\d{8}-\d+", html)))
            print(f"  発送待ち: {len(order_nums)}건")

            for i, order_no in enumerate(order_nums, 1):
                print(f"  [{i}/{len(order_nums)}] {order_no} 상세 진입...")
                try:
                    page.goto(DETAIL_URL.format(order_no=order_no),
                              wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)

                    # 상품 row 추출 (DOM evaluate)
                    products = page.evaluate("""() => {
                        const result = [];
                        const trs = document.querySelectorAll('tr.opp-thick-border-green');
                        trs.forEach(tr => {
                            const tds = tr.querySelectorAll('td');
                            if (tds.length < 8) return;
                            // 상품명: 첫 셀의 첫 a 링크
                            const titleAnchor = tds[0].querySelector('a.rms-span-open-in-new');
                            const title = titleAnchor ? titleAnchor.innerText.trim() : '';
                            // 옵션: 첫 셀의 div 들 중 'カラー:' 'サイズ:' 만
                            const optDivs = tds[0].querySelectorAll('div.rms-table-column-line div');
                            const opts = [];
                            optDivs.forEach(d => {
                                const t = (d.innerText || '').trim();
                                if (/^(カラー|色|サイズ|容量|バリエーション)[:：]/.test(t)) opts.push(t);
                            });
                            // 個数: 8번째 td (index 7)
                            const qtyEl = tds[7].querySelector('.rms-text-bold');
                            const qty = qtyEl ? parseInt(qtyEl.innerText.trim(), 10) : 1;
                            result.push({title, options: opts.join(' '), qty});
                        });
                        return result;
                    }""")

                    if not products:
                        print(f"    [WARN] 상품 row 미발견: {order_no}")
                        continue

                    for p in products:
                        normalized = _normalize_title(p["title"], p["options"])
                        rows.append({
                            "market": "rakutenjp",
                            "itemTitleKr": normalized,
                            "option": p["options"],
                            "orderQty": p["qty"] or 1,
                            "orderNo": order_no,
                            "optionCode": "",
                        })
                        print(f"    + {normalized} | {p['options']} | x{p['qty']}")
                except Exception as e:
                    print(f"    [WARN] {order_no} 추출 실패: {e}")
                    continue

            return rows
        finally:
            page.wait_for_timeout(500)
            context.close()
            browser.close()


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--out", default=str(TMP / "rakuten_pending_rows.json"))
    args = ap.parse_args()

    rows = fetch_pending_orders(headless=not args.headed)
    Path(args.out).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n총 {len(rows)} 행 → {args.out}")


if __name__ == "__main__":
    main()
