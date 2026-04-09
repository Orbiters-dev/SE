"""
Social Evaluator — Content Score Backtester & Weight Optimizer
==============================================================
Correlates CI sub-scores with actual views/engagement to:
1. BACKTEST: which sub-scores predict virality?
2. OPTIMIZE: learn optimal weights from data
3. PREDICT: estimate views from content signals alone

Usage:
    python tools/social_evaluator.py --backtest
    python tools/social_evaluator.py --optimize
    python tools/social_evaluator.py --predict --post-url "https://..."
    python tools/social_evaluator.py --full
    python tools/social_evaluator.py --dry-run
"""

import os, sys, json, io, math
from pathlib import Path
from datetime import datetime

# Fix encoding
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DIR.parent
sys.path.insert(0, str(DIR))

try:
    from env_loader import load_env
    load_env()
except Exception:
    pass

OUT_DIR = PROJECT_ROOT / ".tmp" / "evaluator"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Sub-score feature names (from ci_analysis JSON)
VISION_FEATURES = [
    "hook_score", "storytelling_score", "authenticity_score",
    "delivery_score", "brand_fit_score",
]
WHISPER_FEATURES = [
    "delivery_verbal_score", "repeat_watchability",
]
BINARY_FEATURES = [
    "has_subtitles", "demo_present", "cta_present", "product_mention",
    "baby_audio_cues",
]
CATEGORICAL_FEATURES = [
    "emotional_tone", "hook_type", "script_structure",
    "persuasion_type", "subject_age", "scene_fit",
]
AUDIO_FEATURES = [
    "voice_energy_score", "speech_pace_score", "audio_hook_timing",
]

ALL_NUMERIC_FEATURES = VISION_FEATURES + WHISPER_FEATURES + AUDIO_FEATURES


# ── Data Loading ────────────────────────────────────────────────────

def fetch_scored_posts(min_views=100) -> list:
    """Get posts from PG that have BOTH ci_analysis AND actual metrics."""
    import requests
    user = os.getenv("ORBITOOLS_USER", "admin")
    pw = os.getenv("ORBITOOLS_PASS", "orbit1234")
    base = "https://orbitools.orbiters.co.kr/api/datakeeper"

    # Fetch large batch
    resp = requests.get(
        f"{base}/query/",
        params={"table": "content_posts", "limit": "5000"},
        auth=(user, pw), timeout=60, verify=False,
    )
    if not resp.ok:
        print(f"  ERROR: PG query failed {resp.status_code}")
        return []

    rows = resp.json().get("rows", [])

    valid = []
    for r in rows:
        views = int(r.get("views_30d", 0) or 0)
        if views < min_views:
            continue

        # Parse ci_analysis
        ci = r.get("ci_analysis")
        if not ci:
            continue
        if isinstance(ci, str):
            try:
                ci = json.loads(ci)
            except Exception:
                continue

        # Must have at least hook_score
        if not ci.get("hook_score"):
            continue

        # Flatten
        row = {
            "username": r.get("username", ""),
            "url": r.get("url", ""),
            "views_30d": views,
            "likes_30d": int(r.get("likes_30d", 0) or 0),
            "comments_30d": int(r.get("comments_30d", 0) or 0),
            "followers": int(r.get("followers", 0) or 0),
            "content_quality_score": int(r.get("content_quality_score", 0) or 0),
            "creator_fit_score": int(r.get("creator_fit_score", 0) or 0),
        }
        # Add all CI sub-scores
        for feat in ALL_NUMERIC_FEATURES:
            row[feat] = float(ci.get(feat, 0) or 0)
        # Audio features live inside nested audio_analysis dict
        audio = ci.get("audio_analysis", {}) or {}
        for feat in AUDIO_FEATURES:
            if row[feat] == 0 and feat in audio:
                row[feat] = float(audio.get(feat, 0) or 0)
        for feat in BINARY_FEATURES:
            val = ci.get(feat)
            if val is None and feat in audio:
                val = audio.get(feat)
            row[feat] = 1.0 if val else 0.0
        for feat in CATEGORICAL_FEATURES:
            row[f"cat_{feat}"] = ci.get(feat, "")

        valid.append(row)

    return valid


# ── Backtest: Correlation Analysis ──────────────────────────────────

def pearson_r(x: list, y: list) -> float:
    """Calculate Pearson correlation coefficient."""
    n = len(x)
    if n < 3:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x) / n)
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y) / n)
    if sx == 0 or sy == 0:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
    return round(cov / (sx * sy), 4)


def run_backtest(posts: list) -> dict:
    """Correlate each sub-score with actual views and engagement."""
    print(f"\n{'='*60}")
    print(f"BACKTEST: {len(posts)} posts with CI scores + actual metrics")
    print(f"{'='*60}\n")

    views = [p["views_30d"] for p in posts]
    log_views = [math.log10(max(v, 1)) for v in views]  # log scale for better correlation
    likes = [p["likes_30d"] for p in posts]
    er = []
    for p in posts:
        v = p["views_30d"]
        er.append((p["likes_30d"] + p["comments_30d"]) / v * 100 if v > 0 else 0)

    results = {"features": {}, "n_posts": len(posts)}

    # Numeric features vs views
    all_features = ALL_NUMERIC_FEATURES + BINARY_FEATURES
    print(f"{'Feature':30s} {'r(views)':>10} {'r(log_views)':>13} {'r(likes)':>10} {'r(ER)':>10}")
    print("-" * 80)

    for feat in all_features:
        vals = [p.get(feat, 0) for p in posts]
        if all(v == 0 for v in vals):
            continue

        r_views = pearson_r(vals, views)
        r_log = pearson_r(vals, log_views)
        r_likes = pearson_r(vals, likes)
        r_er = pearson_r(vals, er)

        results["features"][feat] = {
            "r_views": r_views,
            "r_log_views": r_log,
            "r_likes": r_likes,
            "r_er": r_er,
            "mean": round(sum(vals) / len(vals), 2),
            "std": round((sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals)) ** 0.5, 2),
        }

        # Highlight strong correlations
        marker = ""
        if abs(r_log) >= 0.3:
            marker = " ***"
        elif abs(r_log) >= 0.15:
            marker = " **"
        elif abs(r_log) >= 0.08:
            marker = " *"

        print(f"{feat:30s} {r_views:>10.4f} {r_log:>13.4f} {r_likes:>10.4f} {r_er:>10.4f}{marker}")

    # Composite scores
    print(f"\n{'--- Composite Scores ---':^80}")
    for comp in ["content_quality_score", "creator_fit_score"]:
        vals = [p.get(comp, 0) for p in posts]
        if all(v == 0 for v in vals):
            print(f"  {comp}: all zeros (CI not run yet)")
            continue
        r_log = pearson_r(vals, log_views)
        r_er = pearson_r(vals, er)
        print(f"  {comp:30s} r(log_views)={r_log:.4f}  r(ER)={r_er:.4f}")
        results["features"][comp] = {"r_log_views": r_log, "r_er": r_er}

    # Categorical analysis
    print(f"\n{'--- Categorical Breakdown ---':^80}")
    for cat in CATEGORICAL_FEATURES:
        key = f"cat_{cat}"
        groups = {}
        for p in posts:
            val = p.get(key, "")
            if not val:
                continue
            if val not in groups:
                groups[val] = []
            groups[val].append(p["views_30d"])

        if len(groups) < 2:
            continue

        print(f"\n  {cat}:")
        cat_stats = {}
        for val, view_list in sorted(groups.items(), key=lambda x: -sum(x[1])/len(x[1])):
            avg = sum(view_list) / len(view_list)
            med = sorted(view_list)[len(view_list) // 2]
            cat_stats[val] = {"n": len(view_list), "avg_views": round(avg), "median_views": med}
            print(f"    {val:20s} n={len(view_list):>4}  avg_views={avg:>12,.0f}  median={med:>10,}")

        results["features"][f"cat_{cat}"] = cat_stats

    # Top predictors ranking
    ranked = sorted(
        [(k, v.get("r_log_views", 0)) for k, v in results["features"].items()
         if isinstance(v, dict) and "r_log_views" in v],
        key=lambda x: abs(x[1]), reverse=True,
    )
    print(f"\n{'--- TOP PREDICTORS (by |r| with log_views) ---':^80}")
    for i, (feat, r) in enumerate(ranked[:10], 1):
        direction = "+" if r > 0 else "-"
        strength = "STRONG" if abs(r) >= 0.3 else ("moderate" if abs(r) >= 0.15 else "weak")
        print(f"  {i:>2}. {feat:30s}  r={r:>7.4f}  ({direction}) {strength}")

    results["top_predictors"] = ranked[:10]
    return results


# ── Optimize: Weight Learning ───────────────────────────────────────

def run_optimize(posts: list, backtest_results: dict) -> dict:
    """Learn optimal weights using linear regression."""
    print(f"\n{'='*60}")
    print(f"OPTIMIZE: Learning weights from {len(posts)} posts")
    print(f"{'='*60}\n")

    # Prepare features matrix
    feature_names = [f for f in ALL_NUMERIC_FEATURES + BINARY_FEATURES
                     if any(p.get(f, 0) != 0 for p in posts)]

    if len(feature_names) < 2:
        print("  Not enough non-zero features for regression.")
        return {"status": "insufficient_features"}

    n = len(posts)
    X = []
    y = []
    for p in posts:
        row = [p.get(f, 0) for f in feature_names]
        X.append(row)
        y.append(math.log10(max(p["views_30d"], 1)))  # log views as target

    # Simple least squares (no sklearn dependency)
    # Normal equation: w = (X^T X)^-1 X^T y
    # Add bias column
    X_bias = [[1.0] + row for row in X]
    feature_names_bias = ["bias"] + feature_names

    try:
        weights = _least_squares(X_bias, y)
    except Exception as e:
        print(f"  Regression failed: {e}")
        print("  Falling back to correlation-based weights...")
        # Fallback: use correlation as proxy for weight
        weights = [0.0]  # bias
        for f in feature_names:
            r = backtest_results.get("features", {}).get(f, {}).get("r_log_views", 0)
            weights.append(max(0, r))  # only positive correlations
        feature_names_bias = ["bias"] + feature_names

    # Normalize weights (exclude bias)
    raw_weights = {f: w for f, w in zip(feature_names_bias[1:], weights[1:])}
    total_abs = sum(abs(w) for w in weights[1:]) or 1
    norm_weights = {f: round(w / total_abs * 100, 1) for f, w in raw_weights.items()}

    # Print results
    print(f"{'Feature':30s} {'Raw Weight':>12} {'Normalized %':>14}")
    print("-" * 60)
    for f in sorted(norm_weights, key=lambda x: abs(norm_weights[x]), reverse=True):
        print(f"  {f:28s} {raw_weights[f]:>12.4f} {norm_weights[f]:>13.1f}%")

    # Compare with v1 manual weights
    v1_weights = {
        "authenticity_score": 35.0,
        "storytelling_score": 25.0,
        "hook_score": 20.0,
        "delivery_score": 10.0,
        "delivery_verbal_score": 10.0,
    }

    print(f"\n{'--- v1 (manual) vs v3 (data-driven) ---':^60}")
    print(f"{'Feature':30s} {'v1 weight':>10} {'v3 weight':>10} {'Delta':>10}")
    print("-" * 65)
    for f in sorted(set(list(v1_weights.keys()) + list(norm_weights.keys())),
                    key=lambda x: abs(norm_weights.get(x, 0)), reverse=True):
        v1 = v1_weights.get(f, 0)
        v3 = norm_weights.get(f, 0)
        delta = v3 - v1
        marker = " <--" if abs(delta) > 10 else ""
        print(f"  {f:28s} {v1:>9.1f}% {v3:>9.1f}% {delta:>+9.1f}%{marker}")

    # Prediction accuracy on training data
    predictions = []
    for row in X_bias:
        pred = sum(w * x for w, x in zip(weights, row))
        predictions.append(10 ** pred)  # convert back from log

    actuals = [p["views_30d"] for p in posts]
    mae = sum(abs(a - p) for a, p in zip(actuals, predictions)) / n
    mape = sum(abs(a - p) / max(a, 1) for a, p in zip(actuals, predictions)) / n * 100

    # R² score
    ss_res = sum((a - p) ** 2 for a, p in zip(actuals, predictions))
    ss_tot = sum((a - sum(actuals)/n) ** 2 for a in actuals)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    print(f"\n  Prediction Accuracy (training):")
    print(f"    MAE:  {mae:,.0f} views")
    print(f"    MAPE: {mape:.1f}%")
    print(f"    R²:   {r2:.4f}")

    result = {
        "feature_names": feature_names,
        "raw_weights": raw_weights,
        "normalized_weights": norm_weights,
        "v1_weights": v1_weights,
        "accuracy": {"mae": round(mae), "mape": round(mape, 1), "r2": round(r2, 4)},
        "n_posts": n,
        "model_bias": weights[0],
    }

    # Save
    out_path = OUT_DIR / "optimized_weights.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved to {out_path}")

    return result


def _least_squares(X: list, y: list) -> list:
    """Solve normal equation: w = (X^T X)^-1 X^T y (pure Python, no numpy)."""
    n = len(X)
    m = len(X[0])

    # X^T X
    XtX = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(m)] for i in range(m)]
    # Add ridge regularization to prevent singular matrix
    for i in range(m):
        XtX[i][i] += 0.01

    # X^T y
    Xty = [sum(X[k][i] * y[k] for k in range(n)) for i in range(m)]

    # Gaussian elimination
    aug = [XtX[i][:] + [Xty[i]] for i in range(m)]
    for col in range(m):
        # Find pivot
        max_row = max(range(col, m), key=lambda r: abs(aug[r][col]))
        aug[col], aug[max_row] = aug[max_row], aug[col]

        pivot = aug[col][col]
        if abs(pivot) < 1e-10:
            continue
        for j in range(col, m + 1):
            aug[col][j] /= pivot
        for row in range(m):
            if row == col:
                continue
            factor = aug[row][col]
            for j in range(col, m + 1):
                aug[row][j] -= factor * aug[col][j]

    return [aug[i][m] for i in range(m)]


# ── Predict ─────────────────────────────────────────────────────────

def run_predict(post_url: str = None, ci_signals: dict = None) -> dict:
    """Predict views for a post based on content signals only."""
    # Load optimized weights
    weights_path = OUT_DIR / "optimized_weights.json"
    if not weights_path.exists():
        print("  ERROR: No optimized weights found. Run --optimize first.")
        return {}

    with open(weights_path, "r") as f:
        model = json.load(f)

    weights = model["raw_weights"]
    bias = model.get("model_bias", 0)

    if not ci_signals:
        print("  No CI signals provided. Use --predict with CI data.")
        return {}

    # Calculate predicted log views
    log_pred = bias
    for feat, w in weights.items():
        val = ci_signals.get(feat, 0)
        log_pred += w * val

    predicted_views = int(10 ** log_pred)

    # Confidence based on model R²
    r2 = model["accuracy"]["r2"]
    confidence = "high" if r2 > 0.5 else ("medium" if r2 > 0.2 else "low")

    result = {
        "predicted_views": predicted_views,
        "confidence": confidence,
        "model_r2": r2,
        "signals_used": {f: ci_signals.get(f, 0) for f in weights},
    }

    print(f"\n  Predicted views: {predicted_views:,}")
    print(f"  Confidence: {confidence} (model R²={r2:.4f})")

    return result


# ── HTML Report ─────────────────────────────────────────────────────

def build_report(backtest: dict, optimize: dict, posts: list):
    """Generate HTML backtest report."""
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Social Evaluator Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f8f9fa; }}
h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
h2 {{ color: #16213e; margin-top: 30px; }}
table {{ border-collapse: collapse; width: 100%; margin: 15px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
th {{ background: #16213e; color: white; padding: 12px; text-align: left; }}
td {{ padding: 10px 12px; border-bottom: 1px solid #eee; }}
tr:hover {{ background: #f0f7ff; }}
.strong {{ color: #e94560; font-weight: bold; }}
.moderate {{ color: #f4a261; }}
.weak {{ color: #999; }}
.metric {{ display: inline-block; background: #16213e; color: white; padding: 8px 16px; border-radius: 20px; margin: 5px; font-size: 14px; }}
.section {{ background: white; padding: 20px; border-radius: 8px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
</style></head><body>
<h1>Social Evaluator — Backtest Report</h1>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<div>
<span class="metric">Posts Analyzed: {backtest.get('n_posts', 0)}</span>
<span class="metric">Model R²: {optimize.get('accuracy', {}).get('r2', 'N/A')}</span>
<span class="metric">MAE: {optimize.get('accuracy', {}).get('mae', 'N/A'):,} views</span>
</div>
"""

    # Top predictors
    html += "<h2>Top Predictors of Virality</h2><div class='section'><table>"
    html += "<tr><th>#</th><th>Feature</th><th>Correlation (r)</th><th>Direction</th><th>Strength</th></tr>"
    for i, (feat, r) in enumerate(backtest.get("top_predictors", []), 1):
        direction = "+" if r > 0 else "-"
        if abs(r) >= 0.3:
            cls, strength = "strong", "STRONG"
        elif abs(r) >= 0.15:
            cls, strength = "moderate", "moderate"
        else:
            cls, strength = "weak", "weak"
        html += f"<tr><td>{i}</td><td>{feat}</td><td>{r:.4f}</td><td>{direction}</td><td class='{cls}'>{strength}</td></tr>"
    html += "</table></div>"

    # Weight comparison
    if optimize.get("normalized_weights"):
        html += "<h2>v1 (Manual) vs v3 (Data-Driven) Weights</h2><div class='section'><table>"
        html += "<tr><th>Feature</th><th>v1 Weight</th><th>v3 Weight</th><th>Delta</th></tr>"
        v1w = optimize.get("v1_weights", {})
        v3w = optimize.get("normalized_weights", {})
        for f in sorted(set(list(v1w.keys()) + list(v3w.keys())),
                        key=lambda x: abs(v3w.get(x, 0)), reverse=True):
            v1 = v1w.get(f, 0)
            v3 = v3w.get(f, 0)
            delta = v3 - v1
            cls = "strong" if abs(delta) > 10 else ""
            html += f"<tr><td>{f}</td><td>{v1:.1f}%</td><td>{v3:.1f}%</td><td class='{cls}'>{delta:+.1f}%</td></tr>"
        html += "</table></div>"

    html += "</body></html>"

    out_path = OUT_DIR / "backtest_report.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n  Report saved to {out_path}")


# ── Main ────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Social Evaluator — Backtest + Optimize + Predict")
    parser.add_argument("--backtest", action="store_true", help="Run correlation analysis")
    parser.add_argument("--optimize", action="store_true", help="Learn optimal weights")
    parser.add_argument("--predict", action="store_true", help="Predict views for a post")
    parser.add_argument("--full", action="store_true", help="Run backtest + optimize + report")
    parser.add_argument("--dry-run", action="store_true", help="Show data availability only")
    parser.add_argument("--post-url", help="Post URL for prediction")
    parser.add_argument("--min-views", type=int, default=100, help="Minimum views filter")
    args = parser.parse_args()

    if not any([args.backtest, args.optimize, args.predict, args.full, args.dry_run]):
        args.dry_run = True

    print("=" * 60)
    print("  Social Evaluator — Content Score Backtester")
    print("=" * 60)

    # Load data
    print("\nLoading scored posts from PG...")
    posts = fetch_scored_posts(min_views=args.min_views)
    print(f"  Found {len(posts)} posts with CI scores + actual metrics")

    if args.dry_run:
        print(f"\n  Data summary:")
        print(f"    Total posts with CI + views: {len(posts)}")
        if posts:
            views = [p["views_30d"] for p in posts]
            print(f"    View range: {min(views):,} — {max(views):,}")
            print(f"    Median views: {sorted(views)[len(views)//2]:,}")

            # Check which features have data
            for feat in ALL_NUMERIC_FEATURES + BINARY_FEATURES:
                non_zero = sum(1 for p in posts if p.get(feat, 0) != 0)
                pct = non_zero / len(posts) * 100 if posts else 0
                status = "OK" if pct > 50 else ("sparse" if pct > 10 else "EMPTY")
                print(f"    {feat:30s}  {non_zero:>5}/{len(posts)}  ({pct:.0f}%)  {status}")

        if len(posts) < 100:
            print(f"\n  WARNING: {len(posts)} posts is too few for reliable analysis.")
            print(f"  Need 100+ for correlation, 500+ for regression.")
            print(f"  Run CI pipeline on more posts first:")
            print(f"    python tools/analyze_video_content.py --region us --max 500")
        return

    if len(posts) < 10:
        print("\n  ERROR: Need at least 10 scored posts. Run CI pipeline first.")
        return

    backtest_results = {}
    optimize_results = {}

    if args.backtest or args.full:
        backtest_results = run_backtest(posts)
        # Save
        with open(OUT_DIR / "backtest_results.json", "w") as f:
            json.dump(backtest_results, f, indent=2, ensure_ascii=False)

    if args.optimize or args.full:
        if not backtest_results:
            # Load from file
            bp = OUT_DIR / "backtest_results.json"
            if bp.exists():
                with open(bp) as f:
                    backtest_results = json.load(f)
        optimize_results = run_optimize(posts, backtest_results)

    if args.full:
        build_report(backtest_results, optimize_results, posts)

    if args.predict:
        # For now, need CI signals as JSON
        print("\n  Predict mode requires CI signals.")
        print("  Run: python tools/social_evaluator.py --predict --post-url <url>")
        print("  (Will auto-fetch CI signals from PG if post was analyzed)")


if __name__ == "__main__":
    main()
