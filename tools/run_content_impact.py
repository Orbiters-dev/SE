#!/usr/bin/env python3
"""
Content Impact Modeler (분석이)
──────────────────────────────
Analyzes correlation between influencer content view deltas
and brand sales / search volume.

Modules:
  1. TLCC  — Time-Lagged Cross-Correlation (optimal lag discovery)
  2. Score — Per-post Impact Score
  3. Granger — Granger Causality + OLS regression

Usage:
  python tools/run_content_impact.py                  # full analysis
  python tools/run_content_impact.py --brand grosmimi # single brand
  python tools/run_content_impact.py --module tlcc    # TLCC only
  python tools/run_content_impact.py --dry-run        # data check only
  python tools/run_content_impact.py --preview        # save HTML only
"""

import sys, os, json, argparse, warnings
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore", category=FutureWarning)

# ── paths ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
os.chdir(str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

OUT_DIR = ROOT / ".tmp" / "content_impact"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── brands ─────────────────────────────────────────────────────────
ALL_BRANDS = ["Grosmimi", "CHA&MOM", "Naeiae", "Babyrabbit", "Commemoi", "Goongbe"]

BRAND_SEARCH_KEYWORDS = {
    "Grosmimi":   ["grosmimi", "gros mimi", "그로미미"],
    "CHA&MOM":    ["cha&mom", "chamom", "차앤맘"],
    "Naeiae":     ["naeiae", "나이아이"],
    "Babyrabbit": ["babyrabbit", "baby rabbit"],
    "Commemoi":   ["commemoi"],
    "Goongbe":    ["goongbe", "궁비"],
}

# ── data loading ───────────────────────────────────────────────────

def load_data(days=90):
    """Load all required datasets from DataKeeper."""
    from data_keeper_client import DataKeeper
    dk = DataKeeper()

    print(f"[Data] Loading {days}-day datasets from DataKeeper...")

    data = {}
    tables = [
        ("content_posts", days),
        ("content_metrics_daily", days),
        ("shopify_orders_daily", days),
        ("amazon_sales_daily", days),
        ("gsc_daily", days),
        ("meta_ads_daily", days),
        ("amazon_ads_daily", days),
        ("google_ads_daily", days),
    ]

    for table, d in tables:
        try:
            rows = dk.get(table, days=d)
            data[table] = rows
            print(f"  {table}: {len(rows)} rows")
        except Exception as e:
            print(f"  {table}: FAILED ({e})")
            data[table] = []

    return data


# ── preprocessing ──────────────────────────────────────────────────

import numpy as np
import pandas as pd


def build_view_delta_series(data, brand=None):
    """Build daily view delta per brand from content_metrics_daily."""
    metrics = data.get("content_metrics_daily", [])
    posts = data.get("content_posts", [])

    # post_id -> brand mapping
    post_brand = {}
    for p in posts:
        b = p.get("brand", "")
        if b:
            post_brand[p.get("post_id", p.get("id", ""))] = b

    # aggregate daily views by brand
    daily = defaultdict(lambda: defaultdict(int))  # {date: {brand: total_views}}
    for m in metrics:
        pid = m.get("post_id", "")
        b = post_brand.get(pid, "Unknown")
        if brand and b.lower() != brand.lower():
            continue
        d = str(m.get("date", ""))[:10]
        views = int(m.get("views") or 0)
        daily[d][b] += views

    if not daily:
        return pd.DataFrame()

    # build DataFrame
    dates = sorted(daily.keys())
    brands = sorted({b for day in daily.values() for b in day})
    rows = []
    for d in dates:
        row = {"date": d}
        for b in brands:
            row[b] = daily[d].get(b, 0)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    # compute delta (day-over-day change)
    df_delta = df.diff().dropna()
    return df_delta


def build_sales_series(data, brand=None):
    """Build daily net_sales per brand from Shopify + Amazon."""
    shopify = data.get("shopify_orders_daily", [])
    amazon = data.get("amazon_sales_daily", [])

    daily = defaultdict(lambda: defaultdict(float))

    SKIP_CHANNELS = {"PR", "Amazon"}
    for r in shopify:
        ch = r.get("channel", "")
        if ch in SKIP_CHANNELS:
            continue
        b = r.get("brand", "Other")
        if brand and b.lower() != brand.lower():
            continue
        d = str(r.get("date", ""))[:10]
        daily[d][b] += float(r.get("net_sales") or 0)

    # Amazon sales — map seller to brand
    SELLER_BRAND = {
        "Fleeters": "Naeiae",
        "Orbitool": "Grosmimi",
    }
    for r in amazon:
        seller = r.get("seller_name", "")
        b = "Unknown"
        for key, val in SELLER_BRAND.items():
            if key.lower() in seller.lower():
                b = val
                break
        if brand and b.lower() != brand.lower():
            continue
        d = str(r.get("date", ""))[:10]
        daily[d][b] += float(r.get("ordered_revenue") or 0)

    if not daily:
        return pd.DataFrame()

    dates = sorted(daily.keys())
    brands = sorted({b for day in daily.values() for b in day})
    rows = []
    for d in dates:
        row = {"date": d}
        for b in brands:
            row[b] = daily[d].get(b, 0)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def build_search_series(data, brand=None):
    """Build daily brand search clicks from GSC."""
    gsc = data.get("gsc_daily", [])
    daily = defaultdict(lambda: defaultdict(int))

    for r in gsc:
        query = (r.get("query") or "").lower()
        d = str(r.get("date", ""))[:10]
        clicks = int(r.get("clicks") or 0)

        for b, keywords in BRAND_SEARCH_KEYWORDS.items():
            if brand and b.lower() != brand.lower():
                continue
            if any(kw in query for kw in keywords):
                daily[d][b] += clicks
                break

    if not daily:
        return pd.DataFrame()

    dates = sorted(daily.keys())
    brands = sorted({b for day in daily.values() for b in day})
    rows = []
    for d in dates:
        row = {"date": d}
        for b in brands:
            row[b] = daily[d].get(b, 0)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def build_adspend_series(data, brand=None):
    """Build daily total ad spend (Meta + Amazon + Google)."""
    daily = defaultdict(float)

    for src in ["meta_ads_daily", "amazon_ads_daily", "google_ads_daily"]:
        for r in data.get(src, []):
            d = str(r.get("date", ""))[:10]
            spend = float(r.get("spend") or r.get("cost") or 0)
            daily[d] += spend

    if not daily:
        return pd.Series(dtype=float)

    df = pd.Series(daily, name="ad_spend")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


# ── noise reduction ────────────────────────────────────────────────

def smooth_series(s, window=7):
    """Apply rolling average for noise reduction."""
    return s.rolling(window=window, min_periods=1, center=True).mean()


def remove_outliers_iqr(s, factor=1.5):
    """Remove outliers using IQR method, replace with median."""
    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    median = s.median()
    return s.clip(lower=lower, upper=upper)


def preprocess(s, window=7):
    """Full preprocessing pipeline: outlier removal + smoothing."""
    s = remove_outliers_iqr(s)
    s = smooth_series(s, window)
    return s


# ── Module 1: TLCC ─────────────────────────────────────────────────

def compute_tlcc(x, y, max_lag=14):
    """
    Time-Lagged Cross-Correlation.
    Returns dict of {lag: correlation} for lag in [-max_lag, max_lag].
    Positive lag = x leads y (content precedes sales).
    """
    from scipy import signal

    # align indices
    common = x.index.intersection(y.index)
    if len(common) < 10:
        return {}

    x_vals = x.reindex(common).fillna(0).values
    y_vals = y.reindex(common).fillna(0).values

    # normalize
    x_norm = (x_vals - x_vals.mean()) / (x_vals.std() + 1e-10)
    y_norm = (y_vals - y_vals.mean()) / (y_vals.std() + 1e-10)

    n = len(x_norm)
    correlations = {}

    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            corr = np.corrcoef(x_norm[:n - lag], y_norm[lag:])[0, 1]
        else:
            corr = np.corrcoef(x_norm[-lag:], y_norm[:n + lag])[0, 1]
        if not np.isnan(corr):
            correlations[lag] = round(corr, 4)

    return correlations


def run_tlcc(view_delta, sales, search, brands, max_lag=14):
    """Run TLCC for all brands, return results dict."""
    print("\n[Module 1] Time-Lagged Cross-Correlation")
    print(f"  Max lag: {max_lag} days")

    results = {}
    for brand in brands:
        if brand not in view_delta.columns:
            continue

        vd = preprocess(view_delta[brand])
        brand_results = {"sales": {}, "search": {}}

        # vs sales
        if brand in sales.columns:
            s = preprocess(sales[brand])
            corrs = compute_tlcc(vd, s, max_lag)
            if corrs:
                best_lag = max(corrs, key=corrs.get)
                brand_results["sales"] = {
                    "correlations": corrs,
                    "optimal_lag": best_lag,
                    "max_correlation": corrs[best_lag],
                }
                print(f"  {brand} vs Sales: optimal lag={best_lag}d, r={corrs[best_lag]:.3f}")

        # vs search
        if brand in search.columns:
            sc = preprocess(search[brand])
            corrs = compute_tlcc(vd, sc, max_lag)
            if corrs:
                best_lag = max(corrs, key=corrs.get)
                brand_results["search"] = {
                    "correlations": corrs,
                    "optimal_lag": best_lag,
                    "max_correlation": corrs[best_lag],
                }
                print(f"  {brand} vs Search: optimal lag={best_lag}d, r={corrs[best_lag]:.3f}")

        results[brand] = brand_results

    return results


# ── Module 2: Impact Score ─────────────────────────────────────────

def compute_impact_scores(data):
    """Compute per-post Impact Score."""
    print("\n[Module 2] Content Impact Score")

    posts = data.get("content_posts", [])
    metrics = data.get("content_metrics_daily", [])

    # group metrics by post_id
    post_metrics = defaultdict(list)
    for m in metrics:
        pid = m.get("post_id", "")
        post_metrics[pid].append(m)

    scores = []
    for p in posts:
        pid = p.get("post_id", p.get("id", ""))
        brand = p.get("brand", "")
        handle = p.get("handle", "")
        caption = p.get("caption", "")
        post_date = str(p.get("post_date", p.get("posted_at", "")))[:10]

        if not pid or not brand:
            continue

        pm = sorted(post_metrics.get(pid, []), key=lambda x: str(x.get("date", "")))
        if not pm:
            continue

        # latest metrics
        latest = pm[-1]
        views = int(latest.get("views") or 0)
        likes = int(latest.get("likes") or 0)
        comments = int(latest.get("comments") or 0)

        # view velocity: views / days_since_post
        try:
            days_old = max(1, (datetime.now() - datetime.strptime(post_date, "%Y-%m-%d")).days)
        except (ValueError, TypeError):
            days_old = 30

        view_velocity = views / days_old

        # engagement rate
        engagement_rate = (likes + comments) / max(views, 1)

        # brand fit weight: explicit brand mention in caption = 1.5x
        caption_lower = (caption or "").lower()
        brand_fit = 1.5 if brand.lower() in caption_lower else 1.0

        # decay factor: newer posts get higher weight
        decay = max(0.1, 1.0 - (days_old / 60))

        # final score
        score = view_velocity * engagement_rate * brand_fit * decay * 1000

        scores.append({
            "post_id": pid,
            "brand": brand,
            "handle": handle,
            "post_date": post_date,
            "views": views,
            "likes": likes,
            "comments": comments,
            "view_velocity": round(view_velocity, 1),
            "engagement_rate": round(engagement_rate, 4),
            "brand_fit": brand_fit,
            "decay": round(decay, 2),
            "impact_score": round(score, 2),
        })

    scores.sort(key=lambda x: x["impact_score"], reverse=True)
    print(f"  Scored {len(scores)} posts")
    if scores:
        top = scores[0]
        print(f"  Top: @{top['handle']} ({top['brand']}) score={top['impact_score']:.1f}")

    return scores


# ── Module 3: Granger Causality ────────────────────────────────────

def run_granger(view_delta, sales, search, adspend, brands, max_lag=7):
    """Run Granger causality test + OLS regression."""
    from statsmodels.tsa.stattools import grangercausalitytests
    import statsmodels.api as sm

    print(f"\n[Module 3] Granger Causality (max_lag={max_lag})")

    results = {}
    for brand in brands:
        if brand not in view_delta.columns:
            continue

        brand_results = {"granger_sales": None, "granger_search": None, "regression": None}
        vd = preprocess(view_delta[brand])

        # Granger: view_delta -> sales
        if brand in sales.columns:
            s = preprocess(sales[brand])
            common = vd.index.intersection(s.index)
            if len(common) >= 20:
                df_test = pd.DataFrame({"sales": s.reindex(common), "view_delta": vd.reindex(common)}).dropna()
                if len(df_test) >= 20:
                    try:
                        gc = grangercausalitytests(df_test[["sales", "view_delta"]], maxlag=max_lag, verbose=False)
                        # find best lag by min p-value
                        best_lag = min(gc.keys(), key=lambda k: gc[k][0]["ssr_ftest"][1])
                        p_val = gc[best_lag][0]["ssr_ftest"][1]
                        f_stat = gc[best_lag][0]["ssr_ftest"][0]
                        brand_results["granger_sales"] = {
                            "best_lag": best_lag,
                            "p_value": round(p_val, 4),
                            "f_statistic": round(f_stat, 2),
                            "significant": p_val < 0.05,
                        }
                        sig = "YES" if p_val < 0.05 else "no"
                        print(f"  {brand} view->sales: lag={best_lag}, p={p_val:.4f} ({sig})")
                    except Exception as e:
                        print(f"  {brand} view->sales: Granger failed ({e})")

        # Granger: view_delta -> search
        if brand in search.columns:
            sc = preprocess(search[brand])
            common = vd.index.intersection(sc.index)
            if len(common) >= 20:
                df_test = pd.DataFrame({"search": sc.reindex(common), "view_delta": vd.reindex(common)}).dropna()
                if len(df_test) >= 20:
                    try:
                        gc = grangercausalitytests(df_test[["search", "view_delta"]], maxlag=max_lag, verbose=False)
                        best_lag = min(gc.keys(), key=lambda k: gc[k][0]["ssr_ftest"][1])
                        p_val = gc[best_lag][0]["ssr_ftest"][1]
                        f_stat = gc[best_lag][0]["ssr_ftest"][0]
                        brand_results["granger_search"] = {
                            "best_lag": best_lag,
                            "p_value": round(p_val, 4),
                            "f_statistic": round(f_stat, 2),
                            "significant": p_val < 0.05,
                        }
                        sig = "YES" if p_val < 0.05 else "no"
                        print(f"  {brand} view->search: lag={best_lag}, p={p_val:.4f} ({sig})")
                    except Exception as e:
                        print(f"  {brand} view->search: Granger failed ({e})")

        # OLS regression: sales ~ view_delta_lagged + ad_spend
        if brand in sales.columns:
            s = preprocess(sales[brand])
            optimal_lag = 3  # default, override from TLCC if available
            vd_lagged = vd.shift(optimal_lag)

            common = s.index.intersection(vd_lagged.index)
            if not adspend.empty:
                common = common.intersection(adspend.index)

            if len(common) >= 15:
                df_reg = pd.DataFrame({"sales": s.reindex(common)}).dropna()
                df_reg["view_delta_lag"] = vd_lagged.reindex(common)
                if not adspend.empty:
                    df_reg["ad_spend"] = adspend.reindex(common)
                df_reg = df_reg.dropna()

                if len(df_reg) >= 15:
                    try:
                        X = df_reg.drop("sales", axis=1)
                        X = sm.add_constant(X)
                        y = df_reg["sales"]
                        model = sm.OLS(y, X).fit()

                        brand_results["regression"] = {
                            "r_squared": round(model.rsquared, 4),
                            "adj_r_squared": round(model.rsquared_adj, 4),
                            "coefficients": {
                                k: {"coef": round(v, 4), "p_value": round(model.pvalues[k], 4)}
                                for k, v in model.params.items()
                            },
                            "n_obs": int(model.nobs),
                        }
                        print(f"  {brand} OLS: R²={model.rsquared:.3f}, "
                              f"view_delta coef={model.params.get('view_delta_lag', 0):.4f}")
                    except Exception as e:
                        print(f"  {brand} OLS failed: {e}")

        results[brand] = brand_results

    return results


# ── HTML report ────────────────────────────────────────────────────

def build_html_report(tlcc_results, scores, granger_results, view_delta, sales, search, brands, period):
    """Generate interactive HTML report with Plotly charts."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.io as pio

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Content Impact Analysis</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 20px; background: #f8f9fa; color: #333; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ color: #1a1a2e; border-bottom: 3px solid #16213e; padding-bottom: 10px; }}
  h2 {{ color: #16213e; margin-top: 40px; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin: 20px 0; }}
  .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  .card h3 {{ margin: 0 0 12px; color: #0f3460; }}
  .metric {{ font-size: 28px; font-weight: 700; }}
  .label {{ font-size: 13px; color: #888; margin-top: 4px; }}
  .significant {{ color: #27ae60; }}
  .not-significant {{ color: #e74c3c; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0; background: white; border-radius: 8px; overflow: hidden; }}
  th {{ background: #16213e; color: white; padding: 12px 16px; text-align: left; font-size: 13px; }}
  td {{ padding: 10px 16px; border-bottom: 1px solid #eee; font-size: 13px; }}
  tr:hover td {{ background: #f0f4ff; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .badge-yes {{ background: #d4edda; color: #155724; }}
  .badge-no {{ background: #f8d7da; color: #721c24; }}
  .note {{ background: #fff3cd; padding: 12px 16px; border-radius: 8px; margin: 16px 0; font-size: 13px; }}
  .chart {{ margin: 20px 0; }}
</style></head><body><div class="container">
<h1>Content Impact Analysis</h1>
<p>Period: {period} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<p class="note">Correlation ≠ Causation. 상관관계가 있다고 해서 반드시 인과관계가 있는 것은 아닙니다. Granger test는 예측력을 검정할 뿐, 인과를 증명하지 않습니다.</p>
""")

    # ── Executive Summary Cards ──
    html_parts.append('<h2>Executive Summary</h2><div class="summary-grid">')
    for brand in brands:
        if brand not in tlcc_results:
            continue
        tr = tlcc_results[brand]
        gr = granger_results.get(brand, {})

        sales_corr = tr.get("sales", {}).get("max_correlation", "N/A")
        sales_lag = tr.get("sales", {}).get("optimal_lag", "N/A")
        search_corr = tr.get("search", {}).get("max_correlation", "N/A")

        gs = gr.get("granger_sales", {})
        granger_p = gs.get("p_value", "N/A") if gs else "N/A"
        granger_sig = gs.get("significant", False) if gs else False

        sig_class = "significant" if granger_sig else "not-significant"
        sig_text = "Significant" if granger_sig else "Not Significant"

        html_parts.append(f"""<div class="card">
  <h3>{brand}</h3>
  <div class="metric">{sales_corr if isinstance(sales_corr, str) else f'{sales_corr:.3f}'}</div>
  <div class="label">Peak correlation (views → sales, lag={sales_lag}d)</div>
  <div style="margin-top:12px">
    <span>Search corr: <b>{search_corr if isinstance(search_corr, str) else f'{search_corr:.3f}'}</b></span><br>
    <span>Granger p: <b class="{sig_class}">{granger_p if isinstance(granger_p, str) else f'{granger_p:.4f}'}</b>
      <span class="badge {'badge-yes' if granger_sig else 'badge-no'}">{sig_text}</span>
    </span>
  </div>
</div>""")
    html_parts.append('</div>')

    # ── TLCC Heatmap ──
    html_parts.append('<h2>Cross-Correlation Heatmap (Views → Sales)</h2>')
    heatmap_brands = [b for b in brands if b in tlcc_results and tlcc_results[b].get("sales", {}).get("correlations")]
    if heatmap_brands:
        lags = list(range(-14, 15))
        z = []
        for b in heatmap_brands:
            corrs = tlcc_results[b]["sales"]["correlations"]
            z.append([corrs.get(lag, 0) for lag in lags])

        fig = go.Figure(data=go.Heatmap(
            z=z, x=[str(l) for l in lags], y=heatmap_brands,
            colorscale="RdYlGn", zmid=0,
            text=[[f'{v:.3f}' for v in row] for row in z],
            texttemplate="%{text}", textfont={"size": 9},
        ))
        fig.update_layout(
            xaxis_title="Lag (days, positive = content leads)",
            height=max(200, 60 * len(heatmap_brands) + 100),
            margin=dict(l=120, r=40, t=40, b=60),
        )
        html_parts.append(f'<div class="chart">{pio.to_html(fig, full_html=False, include_plotlyjs="cdn")}</div>')

    # ── Time Series Overlay ──
    html_parts.append('<h2>View Delta vs Sales (7d Rolling)</h2>')
    for brand in brands:
        if brand not in view_delta.columns or brand not in sales.columns:
            continue

        vd_smooth = smooth_series(view_delta[brand])
        s_smooth = smooth_series(sales[brand])

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Scatter(x=vd_smooth.index, y=vd_smooth.values, name="View Delta (7d avg)",
                       line=dict(color="#3498db", width=2)),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=s_smooth.index, y=s_smooth.values, name="Sales (7d avg)",
                       line=dict(color="#e74c3c", width=2)),
            secondary_y=True,
        )
        fig.update_layout(title=brand, height=350, margin=dict(l=60, r=60, t=50, b=40))
        fig.update_yaxes(title_text="View Delta", secondary_y=False)
        fig.update_yaxes(title_text="Sales ($)", secondary_y=True)
        html_parts.append(f'<div class="chart">{pio.to_html(fig, full_html=False, include_plotlyjs=False)}</div>')

    # ── Top Impact Posts ──
    html_parts.append('<h2>Top 15 Impact Posts</h2>')
    html_parts.append("""<table><tr>
      <th>#</th><th>Handle</th><th>Brand</th><th>Date</th>
      <th>Views</th><th>Likes</th><th>Engage%</th><th>Score</th>
    </tr>""")
    for i, s in enumerate(scores[:15], 1):
        html_parts.append(f"""<tr>
      <td>{i}</td><td>@{s['handle']}</td><td>{s['brand']}</td><td>{s['post_date']}</td>
      <td>{s['views']:,}</td><td>{s['likes']:,}</td>
      <td>{s['engagement_rate']*100:.2f}%</td><td><b>{s['impact_score']:.1f}</b></td>
    </tr>""")
    html_parts.append('</table>')

    # ── Granger Results Table ──
    html_parts.append('<h2>Granger Causality Test Results</h2>')
    html_parts.append("""<table><tr>
      <th>Brand</th><th>Target</th><th>Optimal Lag</th>
      <th>F-stat</th><th>p-value</th><th>Significant?</th>
    </tr>""")
    for brand in brands:
        gr = granger_results.get(brand, {})
        for target_key, target_name in [("granger_sales", "Sales"), ("granger_search", "Search")]:
            g = gr.get(target_key)
            if not g:
                continue
            sig_badge = '<span class="badge badge-yes">YES</span>' if g["significant"] \
                else '<span class="badge badge-no">NO</span>'
            html_parts.append(f"""<tr>
              <td>{brand}</td><td>{target_name}</td><td>{g['best_lag']}d</td>
              <td>{g['f_statistic']:.2f}</td><td>{g['p_value']:.4f}</td><td>{sig_badge}</td>
            </tr>""")
    html_parts.append('</table>')

    # ── Regression Results ──
    html_parts.append('<h2>OLS Regression (Sales ~ ViewDelta + AdSpend)</h2>')
    html_parts.append("""<table><tr>
      <th>Brand</th><th>R²</th><th>Adj R²</th><th>N</th>
      <th>ViewDelta Coef</th><th>ViewDelta p</th><th>AdSpend Coef</th><th>AdSpend p</th>
    </tr>""")
    for brand in brands:
        reg = granger_results.get(brand, {}).get("regression")
        if not reg:
            continue
        coefs = reg["coefficients"]
        vd_coef = coefs.get("view_delta_lag", {})
        ad_coef = coefs.get("ad_spend", {})
        html_parts.append(f"""<tr>
          <td>{brand}</td><td>{reg['r_squared']:.4f}</td><td>{reg['adj_r_squared']:.4f}</td>
          <td>{reg['n_obs']}</td>
          <td>{vd_coef.get('coef', 'N/A')}</td><td>{vd_coef.get('p_value', 'N/A')}</td>
          <td>{ad_coef.get('coef', 'N/A')}</td><td>{ad_coef.get('p_value', 'N/A')}</td>
        </tr>""")
    html_parts.append('</table>')

    html_parts.append('</div></body></html>')
    return "\n".join(html_parts)


# ── main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Content Impact Modeler")
    parser.add_argument("--brand", help="Analyze single brand")
    parser.add_argument("--days", type=int, default=90, help="Analysis period (days)")
    parser.add_argument("--max-lag", type=int, default=14, help="Max lag for TLCC")
    parser.add_argument("--module", choices=["tlcc", "score", "granger"], help="Run single module")
    parser.add_argument("--dry-run", action="store_true", help="Data check only")
    parser.add_argument("--preview", action="store_true", help="Save HTML without email")
    args = parser.parse_args()

    print("=" * 60)
    print("  Content Impact Modeler (분석이)")
    print("=" * 60)

    # 1. Load data
    data = load_data(args.days)

    # 2. Build time series
    print("\n[Preprocessing] Building time series...")
    view_delta = build_view_delta_series(data, args.brand)
    sales = build_sales_series(data, args.brand)
    search = build_search_series(data, args.brand)
    adspend = build_adspend_series(data, args.brand)

    print(f"  View delta: {len(view_delta)} days, {len(view_delta.columns)} brands")
    print(f"  Sales: {len(sales)} days, {len(sales.columns) if not sales.empty else 0} brands")
    print(f"  Search: {len(search)} days, {len(search.columns) if not search.empty else 0} brands")
    print(f"  Ad spend: {len(adspend)} days")

    if args.dry_run:
        print("\n[Dry Run] Data check complete. Exiting.")
        return

    brands = sorted(set(view_delta.columns) & set(b for b in ALL_BRANDS))
    if args.brand:
        brands = [b for b in brands if b.lower() == args.brand.lower()]
    if not brands:
        print("\nNo brands with view data found. Need more content_metrics_daily data.")
        return

    print(f"\n[Brands] Analyzing: {', '.join(brands)}")

    # 3. Run modules
    tlcc_results = {}
    scores = []
    granger_results = {}

    if not args.module or args.module == "tlcc":
        tlcc_results = run_tlcc(view_delta, sales, search, brands, args.max_lag)

    if not args.module or args.module == "score":
        scores = compute_impact_scores(data)
        if args.brand:
            scores = [s for s in scores if s["brand"].lower() == args.brand.lower()]

    if not args.module or args.module == "granger":
        granger_results = run_granger(view_delta, sales, search, adspend, brands)

    # 4. Save results
    today = datetime.now().strftime("%Y-%m-%d")
    period = f"{(datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')} ~ {today}"

    # JSON summary
    summary = {
        "generated": today,
        "period": period,
        "brands": {},
        "noise_reduction": "7d_rolling + iqr_outlier_removal",
    }
    for brand in brands:
        brand_summary = {
            "tlcc_sales": tlcc_results.get(brand, {}).get("sales", {}),
            "tlcc_search": tlcc_results.get(brand, {}).get("search", {}),
            "granger": granger_results.get(brand, {}),
            "top_posts": [s for s in scores if s["brand"] == brand][:5],
            "total_impact_score": sum(s["impact_score"] for s in scores if s["brand"] == brand),
        }
        summary["brands"][brand] = brand_summary

    json_path = OUT_DIR / f"impact_summary_{today}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[Output] JSON: {json_path}")

    # HTML report
    html = build_html_report(tlcc_results, scores, granger_results, view_delta, sales, search, brands, period)
    html_path = OUT_DIR / f"impact_report_{today}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Output] HTML: {html_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for brand in brands:
        bs = summary["brands"].get(brand, {})
        sales_r = bs.get("tlcc_sales", {}).get("max_correlation", "N/A")
        sales_lag = bs.get("tlcc_sales", {}).get("optimal_lag", "N/A")
        search_r = bs.get("tlcc_search", {}).get("max_correlation", "N/A")
        g_sales = bs.get("granger", {}).get("granger_sales", {})
        g_sig = g_sales.get("significant", False) if g_sales else False
        total_score = bs.get("total_impact_score", 0)

        print(f"\n  {brand}:")
        print(f"    Views→Sales:  r={sales_r}, lag={sales_lag}d")
        print(f"    Views→Search: r={search_r}")
        print(f"    Granger sig:  {'YES' if g_sig else 'NO'}")
        print(f"    Total Impact: {total_score:.1f}")


if __name__ == "__main__":
    main()
