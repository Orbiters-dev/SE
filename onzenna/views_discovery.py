"""
Content Discovery Search API
=============================
Real-time keyword search (IG + TikTok) with Google Trends expansion,
PG cache check, profile enrichment, and optional background HT evaluation.

Endpoints:
  POST /api/onzenna/discovery/search/
  GET  /api/onzenna/discovery/results/<job_id>/
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .views import _cors_headers, _json_body

# ── Paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
JOBS_DIR = PROJECT_ROOT / ".tmp" / "discovery" / "jobs"


# ─────────────────────────────────────────────
#  POST /api/onzenna/discovery/search/
# ─────────────────────────────────────────────

@csrf_exempt
def discovery_search(request):
    """
    Real-time keyword search → filter → cache-split → enrich → return.

    Body:
      keyword      : str   (required)
      platforms     : "tiktok" | "instagram" | "both" (default: "both")
      use_trends    : bool  (default: true)
      trends_geo    : str   (default: "US")
      max_results   : int   (default: 100, max: 500)
      min_views     : int   (default: 100000)
      limit         : int   (default: 30, max: 100)
      enrich        : bool  (default: true)
      evaluate      : bool  (default: false)
      region        : "us" | "jp" (default: "us")
    """
    if request.method == "OPTIONS":
        return _cors_headers(request, HttpResponse(status=204))

    if request.method != "POST":
        return _cors_headers(request, JsonResponse({"error": "POST required"}, status=405))

    try:
        body = _json_body(request)
    except Exception:
        return _cors_headers(request, JsonResponse({"error": "Invalid JSON"}, status=400))

    keyword = (body.get("keyword") or "").strip()
    if not keyword:
        return _cors_headers(request, JsonResponse({"error": "keyword is required"}, status=400))

    platforms = body.get("platforms", "both")
    use_trends = body.get("use_trends", True)
    trends_geo = body.get("trends_geo", "US")
    max_results = min(int(body.get("max_results", 100)), 500)
    min_views = int(body.get("min_views", 100_000))
    limit = min(int(body.get("limit", 30)), 100)
    enrich = body.get("enrich", True)
    evaluate = body.get("evaluate", False)
    region = body.get("region", "us").lower()

    try:
        # Lazy imports — heavy modules only when needed
        sys.path.insert(0, str(TOOLS_DIR))
        sys.path.insert(0, str(TOOLS_DIR / "ci"))
        from discover_content import (
            expand_keywords_from_trends,
            discover,
            filter_and_rank,
            enrich_profiles,
            CATEGORY_KEYWORDS,
        )

        # ── Step 1: Keyword expansion ──
        keywords_tt = [keyword]
        hashtags_ig = [keyword.replace(" ", "")]

        if use_trends:
            try:
                expanded = expand_keywords_from_trends(keyword, geo=trends_geo)
                keywords_tt = expanded
                hashtags_ig = [kw.replace(" ", "") for kw in expanded]
            except Exception as e:
                pass  # fall through with seed keyword

        # Check category fallbacks
        cat_lower = keyword.lower()
        if cat_lower in CATEGORY_KEYWORDS:
            cat_kw = CATEGORY_KEYWORDS[cat_lower]
            for kw in cat_kw.get("tiktok", []):
                if kw not in keywords_tt:
                    keywords_tt.append(kw)
            for ht in cat_kw.get("instagram", []):
                if ht not in hashtags_ig:
                    hashtags_ig.append(ht)

        # ── Step 2: Apify discovery ──
        raw_results = discover(keywords_tt, hashtags_ig, platform=platforms, max_results=max_results)
        raw_count = len(raw_results)

        # ── Step 3: Filter + rank ──
        top_results = filter_and_rank(raw_results, min_views=min_views, limit=limit)
        filtered_count = len(top_results)

        # ── Step 4: PG cache split ──
        cached, new = _split_cached_vs_new(top_results)
        cached_count = len(cached)
        new_count = len(new)

        # ── Step 5: Enrich profiles (new posts only) ──
        if enrich and new:
            try:
                new = enrich_profiles(new)
            except Exception as e:
                pass  # enrichment is optional

        # ── Step 6: PG sync (insert new posts) ──
        if new:
            _pg_sync(new, region)

        # ── Step 7: Merge cached + new for response ──
        all_results = cached + new

        # ── Step 8: Cost estimate ──
        cost = _estimate_cost(raw_count, new_count, evaluate, enrich)

        # ── Step 9: Optional background evaluator ──
        job_id = None
        if evaluate and all_results:
            job_id = _launch_evaluator(all_results, keyword)

        # ── Build response ──
        # Strip raw Apify data for response size
        response_results = []
        for r in all_results:
            cleaned = {k: v for k, v in r.items() if k != "raw"}
            response_results.append(cleaned)

        resp = JsonResponse({
            "results": response_results,
            "keywords_used": {
                "tiktok": keywords_tt[:20],
                "instagram": hashtags_ig[:20],
            },
            "job_id": job_id,
            "cost_estimate": cost,
            "stats": {
                "raw_count": raw_count,
                "filtered_count": filtered_count,
                "cached_count": cached_count,
                "new_count": new_count,
            },
        })
        return _cors_headers(request, resp)

    except Exception as e:
        return _cors_headers(request, JsonResponse({"error": str(e)}, status=500))


# ─────────────────────────────────────────────
#  GET /api/onzenna/discovery/results/<job_id>/
# ─────────────────────────────────────────────

@csrf_exempt
def discovery_results(request, job_id):
    """Check status / get results of a background evaluation job."""
    if request.method == "OPTIONS":
        return _cors_headers(request, HttpResponse(status=204))

    if request.method != "GET":
        return _cors_headers(request, JsonResponse({"error": "GET required"}, status=405))

    manifest = _read_job(job_id)
    if not manifest:
        return _cors_headers(request, JsonResponse({
            "job_id": job_id,
            "status": "not_found",
        }, status=404))

    resp = JsonResponse({
        "job_id": job_id,
        "status": manifest.get("status", "unknown"),
        "progress": manifest.get("progress", {}),
        "results": manifest.get("results", []),
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
    })
    return _cors_headers(request, resp)


# ─────────────────────────────────────────────
#  Helper functions
# ─────────────────────────────────────────────

def _split_cached_vs_new(posts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Check PG for existing posts by URL. Return (cached, new)."""
    if not posts:
        return [], []

    urls = [p["post_url"] for p in posts if p.get("post_url")]
    if not urls:
        return [], posts

    try:
        from django.db import connection
        placeholders = ",".join(["%s"] * len(urls))
        sql = f"""
            SELECT url, username, views_30d, brand_fit_score,
                   content_quality_score, ci_analysis, transcript, region
            FROM gk_content_posts
            WHERE url = ANY(ARRAY[{placeholders}])
        """
        with connection.cursor() as cursor:
            cursor.execute(sql, urls)
            rows = cursor.fetchall()

        cached_urls = {}
        for row in rows:
            cached_urls[row[0]] = {
                "pg_username": row[1],
                "pg_views_30d": row[2],
                "pg_brand_fit_score": float(row[3]) if row[3] else None,
                "pg_content_quality_score": float(row[4]) if row[4] else None,
                "pg_ci_analysis": row[5],
                "pg_transcript": row[6],
                "pg_region": row[7],
            }

        cached = []
        new = []
        for p in posts:
            url = p.get("post_url", "")
            if url in cached_urls:
                merged = {**p, **cached_urls[url], "source": "cache"}
                cached.append(merged)
            else:
                p["source"] = "new"
                new.append(p)

        return cached, new

    except Exception as e:
        # DB unavailable — treat all as new
        for p in posts:
            p["source"] = "new"
        return [], posts


def _pg_sync(new_posts: list[dict], region: str):
    """Insert new discovery posts into gk_content_posts."""
    if not new_posts:
        return

    try:
        from django.db import connection
        now = datetime.now(timezone.utc).isoformat()

        with connection.cursor() as cursor:
            for p in new_posts:
                post_url = p.get("post_url", "")
                if not post_url:
                    continue

                post_id = post_url.rstrip("/").split("/")[-1].split("?")[0]
                username = p.get("username", "")
                platform = p.get("platform", "")
                views = p.get("views", 0)
                likes = p.get("likes", 0)
                comments = p.get("comments", 0)
                caption = (p.get("caption") or "")[:500]

                cursor.execute("""
                    INSERT INTO gk_content_posts
                        (post_id, username, url, platform, views_30d,
                         likes, comments, caption, region, source, collected_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE SET
                        views_30d = GREATEST(gk_content_posts.views_30d, EXCLUDED.views_30d),
                        likes = GREATEST(gk_content_posts.likes, EXCLUDED.likes),
                        comments = GREATEST(gk_content_posts.comments, EXCLUDED.comments),
                        collected_at = EXCLUDED.collected_at
                """, [
                    post_id, username, post_url, platform, views,
                    likes, comments, caption, region, "discovery", now,
                ])

    except Exception as e:
        pass  # PG sync failure is non-fatal


def _estimate_cost(total_raw: int, new_count: int, evaluate: bool, enrich: bool) -> dict:
    """Estimate USD cost breakdown."""
    search_cost = round(total_raw * 0.0004, 4)  # ~$0.04/100 items
    enrich_cost = round(new_count * 0.02, 2) if enrich else 0
    vision_cost = round(new_count * 0.06, 2) if evaluate else 0
    whisper_cost = round(new_count * 0.006, 3) if evaluate else 0
    audio_cost = round(new_count * 0.01, 3) if evaluate else 0

    return {
        "search_apify": f"${search_cost:.2f}",
        "profile_enrich": f"${enrich_cost:.2f}",
        "vision_ht": f"${vision_cost:.2f}",
        "whisper": f"${whisper_cost:.3f}",
        "gemini_audio": f"${audio_cost:.3f}",
        "total": f"${search_cost + enrich_cost + vision_cost + whisper_cost + audio_cost:.2f}",
    }


def _launch_evaluator(posts: list[dict], keyword: str) -> str:
    """Write manifest + launch background evaluator subprocess. Return job_id."""
    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "job_id": job_id,
        "keyword": keyword,
        "status": "running",
        "progress": {"total": len(posts), "done": 0, "failed": 0},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "results": [],
        "posts": [{k: v for k, v in p.items() if k != "raw"} for p in posts],
    }

    manifest_path = job_dir / "manifest.json"
    _atomic_write_json(manifest_path, manifest)

    # Launch background subprocess
    script = TOOLS_DIR / "run_discovery_evaluator.py"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    python_exe = sys.executable
    cmd = [python_exe, str(script), "--job-id", job_id]

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )

    return job_id


def _read_job(job_id: str) -> dict | None:
    """Read manifest.json for a job."""
    manifest_path = JOBS_DIR / job_id / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write_json(path: Path, data: dict):
    """Atomic JSON write via tempfile + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        shutil.move(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
