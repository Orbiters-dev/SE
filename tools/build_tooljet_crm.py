#!/usr/bin/env python3
"""Build Tooljet CRM Dashboard via Import API.

Creates a complete app with:
- Page 1: Creators table + filters + search
- Page 2: Dashboard KPI cards + charts

Usage:
    python tools/build_tooljet_crm.py              # import full CRM app
    python tools/build_tooljet_crm.py --dry-run    # generate JSON only (no import)
    python tools/build_tooljet_crm.py --cleanup    # delete old apps + internal queries
"""

import json
import sys
import uuid
import requests

# ── Config ──────────────────────────────────────────────────────────────
TOOLJET_URL = "http://13.124.157.191:3003"
EMAIL = "wj.choi@orbiters.co.kr"
PASSWORD = "Orbiters@1010"
WORKSPACE_ID = "8340b43b-3ebe-4ccb-af66-f69c4b343724"
DS_NAME = "postgresql"  # existing global PG data source name
DS_ID = "99dae13a-e719-4f3e-aaa9-32a04dbc1cc3"
APP_NAME = "Pipeline CRM"

OUTPUT_PATH = ".tmp/tooljet_crm_import.json"


def uid():
    return str(uuid.uuid4())


# ── SQL Queries ─────────────────────────────────────────────────────────

Q_LIST_CREATORS = """
SELECT id, ig_handle, email, full_name, brand, pipeline_status,
       outreach_type, followers, avg_views, country, region, source,
       assigned_to, contact_count,
       is_shopify_pr, is_apify_tagged, updated_at
FROM onz_pipeline_creators
ORDER BY updated_at DESC
LIMIT 50
""".strip()

Q_COUNT_CREATORS = """
SELECT COUNT(*) as total FROM onz_pipeline_creators
""".strip()

Q_STATUS_FUNNEL = """
SELECT pipeline_status, COUNT(*) as count
FROM onz_pipeline_creators
GROUP BY pipeline_status
ORDER BY CASE pipeline_status
  WHEN 'Not Started' THEN 1 WHEN 'Draft Ready' THEN 2
  WHEN 'Sent' THEN 3 WHEN 'Replied' THEN 4
  WHEN 'Need Review' THEN 5 WHEN 'Accepted' THEN 6
  WHEN 'Declined' THEN 7 WHEN 'Archived' THEN 8 ELSE 9
END
""".strip()

Q_BRAND_COUNTS = """
SELECT COALESCE(NULLIF(brand, ''), 'Unassigned') as brand, COUNT(*) as count
FROM onz_pipeline_creators GROUP BY 1 ORDER BY count DESC
""".strip()

Q_KPI_SUMMARY = """
SELECT
  COUNT(*) as total_creators,
  COUNT(*) FILTER (WHERE pipeline_status NOT IN ('Not Started','Archived')) as active_pipeline,
  COUNT(*) FILTER (WHERE pipeline_status = 'Sent') as sent,
  COUNT(*) FILTER (WHERE pipeline_status = 'Replied') as replied,
  ROUND(COUNT(*) FILTER (WHERE pipeline_status = 'Replied')::numeric /
    NULLIF(COUNT(*) FILTER (WHERE pipeline_status = 'Sent'), 0) * 100, 1) as reply_rate,
  COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') as new_this_week
FROM onz_pipeline_creators
""".strip()

Q_SOURCE_COUNTS = """
SELECT source, COUNT(*) as count
FROM onz_pipeline_creators GROUP BY source ORDER BY count DESC
""".strip()

Q_WEEKLY_TREND = """
SELECT DATE_TRUNC('week', created_at)::date as week, COUNT(*) as count
FROM onz_pipeline_creators
WHERE created_at >= NOW() - INTERVAL '12 weeks'
GROUP BY 1 ORDER BY 1
""".strip()


# ── Component Builders ──────────────────────────────────────────────────

def make_table(name, query_name):
    """Create a Table component bound to a query."""
    return {
        "component": {
            "name": "Table",
            "definition": {
                "properties": {
                    "data": {"value": "{{queries." + query_name + ".data}}"},
                    "visible_columns": {"value": "{{['ig_handle','email','full_name','brand','pipeline_status','outreach_type','followers','country','source','assigned_to','updated_at']}}"},
                    "server_side_pagination": {"value": "{{false}}"},
                    "client_side_pagination": {"value": "{{true}}"},
                    "server_side_search": {"value": "{{false}}"},
                    "display_search_box": {"value": "{{true}}"},
                    "show_download_button": {"value": "{{true}}"},
                    "show_filter_button": {"value": "{{true}}"},
                    "columns": {"value": "{{{}}}"},
                    "show_bulk_update_actions": {"value": "{{false}}"},
                    "row_height": {"value": "32"},
                },
                "styles": {
                    "text_color": {"value": "#000"},
                    "visibility": {"value": "{{true}}"},
                    "border_radius": {"value": "4"},
                    "cell_size": {"value": "compact"},
                },
                "others": {
                    "show_on_desktop": {"value": "{{true}}"},
                    "show_on_mobile": {"value": "{{true}}"},
                },
                "general": {},
                "validation": {},
            },
        },
        "layouts": {
            "desktop": {"top": 60, "left": 0, "width": 740, "height": 600},
            "mobile": {"top": 120, "left": 0, "width": 300, "height": 400},
        },
        "with_default_children": False,
        "name": name,
        "type": "Table",
        "parent": None,
    }


def make_text(name, text, top, left, width=200, height=36, font_size=14, font_weight="normal"):
    return {
        "component": {
            "name": "Text",
            "definition": {
                "properties": {
                    "text": {"value": text},
                },
                "styles": {
                    "font_weight": {"value": font_weight},
                    "text_size": {"value": str(font_size)},
                    "text_color": {"value": "#1a1a2e"},
                    "visibility": {"value": "{{true}}"},
                },
                "others": {
                    "show_on_desktop": {"value": "{{true}}"},
                    "show_on_mobile": {"value": "{{true}}"},
                },
                "general": {},
                "validation": {},
            },
        },
        "layouts": {
            "desktop": {"top": top, "left": left, "width": width, "height": height},
        },
        "name": name,
        "type": "Text",
        "parent": None,
    }


def make_stat_card(name, label, value_expr, top, left, width=120, height=80):
    """KPI stat card using Text component."""
    return make_text(
        name,
        f"**{label}**\n\n{value_expr}",
        top, left, width, height, font_size=16, font_weight="bold",
    )


def make_chart(name, chart_type, title, data_expr, top, left, width=360, height=300):
    return {
        "component": {
            "name": "Chart",
            "definition": {
                "properties": {
                    "title": {"value": title},
                    "chart_type": {"value": chart_type},
                    "data": {"value": data_expr},
                    "loading_state": {"value": "{{false}}"},
                    "marker_color": {"value": "#4361ee"},
                    "show_axes": {"value": "{{true}}"},
                    "show_grid_lines": {"value": "{{true}}"},
                },
                "styles": {
                    "visibility": {"value": "{{true}}"},
                    "padding": {"value": "default"},
                },
                "others": {
                    "show_on_desktop": {"value": "{{true}}"},
                    "show_on_mobile": {"value": "{{true}}"},
                },
                "general": {},
                "validation": {},
            },
        },
        "layouts": {
            "desktop": {"top": top, "left": left, "width": width, "height": height},
        },
        "name": name,
        "type": "Chart",
        "parent": None,
    }


# ── Build App Definition ────────────────────────────────────────────────

def build_app():
    """Build the complete import-ready app JSON."""

    # Generate IDs
    page1_id = uid()
    page2_id = uid()

    # ── Page 1: Creators ──
    page1_components = {}

    # Title
    page1_components["titleText"] = make_text(
        "titleText", "# Pipeline CRM",
        top=5, left=5, width=300, height=40, font_size=24, font_weight="bold",
    )

    # Count text
    page1_components["countText"] = make_text(
        "countText",
        "Total: {{queries.count_creators.data[0]?.total || '...'}} creators",
        top=10, left=400, width=250, height=30,
    )

    # Table
    page1_components["creatorsTable"] = make_table("creatorsTable", "list_creators")

    # ── Page 2: Dashboard ──
    page2_components = {}

    page2_components["dashTitle"] = make_text(
        "dashTitle", "# Dashboard",
        top=5, left=5, width=300, height=40, font_size=24, font_weight="bold",
    )

    # KPI Cards
    kpis = [
        ("kpiTotal", "Total Creators", "{{queries.kpi_summary.data[0]?.total_creators || '...'}}", 0),
        ("kpiActive", "Active Pipeline", "{{queries.kpi_summary.data[0]?.active_pipeline || '...'}}", 160),
        ("kpiSent", "Sent", "{{queries.kpi_summary.data[0]?.sent || '0'}}", 320),
        ("kpiReplied", "Replied", "{{queries.kpi_summary.data[0]?.replied || '0'}}", 480),
        ("kpiReplyRate", "Reply Rate", "{{queries.kpi_summary.data[0]?.reply_rate || '0'}}%", 640),
    ]
    for name, label, value, left in kpis:
        page2_components[name] = make_stat_card(name, label, value, top=60, left=left, width=140, height=80)

    # Charts
    page2_components["statusChart"] = make_chart(
        "statusChart", "bar", "Pipeline Status",
        "{{queries.status_funnel.data.map(r => ({x: r.pipeline_status, y: r.count}))}}",
        top=160, left=0, width=370, height=300,
    )

    page2_components["brandChart"] = make_chart(
        "brandChart", "pie", "Brand Distribution",
        "{{queries.brand_counts.data.map(r => ({x: r.brand, y: r.count}))}}",
        top=160, left=380, width=360, height=300,
    )

    page2_components["sourceChart"] = make_chart(
        "sourceChart", "pie", "Source Distribution",
        "{{queries.source_counts.data.map(r => ({x: r.source, y: r.count}))}}",
        top=480, left=0, width=370, height=300,
    )

    page2_components["trendChart"] = make_chart(
        "trendChart", "line", "Weekly New Creators",
        "{{queries.weekly_trend.data.map(r => ({x: r.week, y: r.count}))}}",
        top=480, left=380, width=360, height=300,
    )

    # ── Data Queries ──
    ds_ref = {"id": uid(), "name": DS_NAME, "kind": "postgresql"}

    queries = [
        {"name": "list_creators", "query": Q_LIST_CREATORS, "run_on_page_load": True},
        {"name": "count_creators", "query": Q_COUNT_CREATORS, "run_on_page_load": True},
        {"name": "status_funnel", "query": Q_STATUS_FUNNEL, "run_on_page_load": True},
        {"name": "brand_counts", "query": Q_BRAND_COUNTS, "run_on_page_load": True},
        {"name": "kpi_summary", "query": Q_KPI_SUMMARY, "run_on_page_load": True},
        {"name": "source_counts", "query": Q_SOURCE_COUNTS, "run_on_page_load": True},
        {"name": "weekly_trend", "query": Q_WEEKLY_TREND, "run_on_page_load": True},
    ]

    data_queries = []
    for q in queries:
        data_queries.append({
            "id": uid(),
            "name": q["name"],
            "kind": "postgresql",
            "data_source_id": ds_ref["id"],
            "options": {"mode": "sql", "query": q["query"]},
            "plugin_id": None,
        })

    # ── App Version ──
    app_def = {
        "name": APP_NAME,
        "organizationId": WORKSPACE_ID,
        "appVersions": [
            {
                "name": "v1",
                "definition": {
                    "components_mapping": {},
                    "home_page_id": page1_id,
                    "pages": {
                        page1_id: {
                            "name": "Creators",
                            "handle": "creators",
                            "components": page1_components,
                        },
                        page2_id: {
                            "name": "Dashboard",
                            "handle": "dashboard",
                            "components": page2_components,
                        },
                    },
                    "show_viewer_navigation": True,
                },
                "dataSources": [ds_ref],
                "dataQueries": data_queries,
                "pages": [
                    {"name": "Creators", "handle": "creators", "index": 0},
                    {"name": "Dashboard", "handle": "dashboard", "index": 1},
                ],
            }
        ],
    }

    return {"name": APP_NAME, "app": app_def}


# ── Auth ────────────────────────────────────────────────────────────────

def login():
    r = requests.post(
        f"{TOOLJET_URL}/api/authenticate",
        json={"email": EMAIL, "password": PASSWORD, "redirectTo": "/"},
    )
    r.raise_for_status()
    token = r.cookies.get("tj_auth_token")
    if not token:
        raise RuntimeError(f"No auth token: {r.text}")
    return token


def headers(token):
    return {
        "Cookie": f"tj_auth_token={token}",
        "tj-workspace-id": WORKSPACE_ID,
        "Content-Type": "application/json",
    }


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("=== Tooljet CRM App Builder ===\n")

    app_json = build_app()

    # Save JSON
    import os
    os.makedirs(".tmp", exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(app_json, f, indent=2)
    print(f"[1] Saved app JSON to {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH)} bytes)")

    if "--dry-run" in sys.argv:
        print("\n  --dry-run: skipping import")
        return

    print("\n[2] Logging in...")
    token = login()
    print(f"  Token: {token[:20]}...")

    # Check if app already exists
    print("\n[3] Checking existing apps...")
    r = requests.get(f"{TOOLJET_URL}/api/apps", headers=headers(token))
    apps = r.json().get("apps", [])
    for a in apps:
        print(f"  - {a['name']} (id={a['id'][:16]})")
        if a["name"] == APP_NAME:
            print(f"  ! App '{APP_NAME}' already exists. Deleting...")
            requests.delete(f"{TOOLJET_URL}/api/apps/{a['id']}", headers=headers(token))
            print(f"  Deleted.")

    # Import
    print(f"\n[4] Importing '{APP_NAME}'...")
    r = requests.post(
        f"{TOOLJET_URL}/api/apps/import",
        headers=headers(token),
        json=app_json,
    )
    if r.status_code == 201:
        data = r.json()
        app_id = data.get("id", "?")
        slug = data.get("slug", "?")
        print(f"  OK! App ID: {app_id}")
        print(f"  Slug: {slug}")
        print(f"\n  Editor URL: {TOOLJET_URL}/orbiterss-workspace/apps/{slug}")
        print(f"  Viewer URL: {TOOLJET_URL}/applications/{slug}")

        # Now set up data source for the imported queries
        print("\n[5] Setting up data source connection for queries...")
        ver = data.get("editing_version", {})
        ver_id = ver.get("id", "?")
        print(f"  Version ID: {ver_id}")

        # List queries in the new app
        rq = requests.get(
            f"{TOOLJET_URL}/api/data_queries?app_id={app_id}&app_version_id={ver_id}",
            headers=headers(token),
        )
        imported_queries = rq.json().get("data_queries", [])
        print(f"  Imported queries: {len(imported_queries)}")
        for q in imported_queries:
            print(f"    - {q['name']} (ds_id={str(q.get('data_source_id','?'))[:16]})")

        # Update queries to use the correct data source ID
        updated = 0
        for q in imported_queries:
            if q.get("data_source_id") != DS_ID:
                ru = requests.patch(
                    f"{TOOLJET_URL}/api/data_queries/{q['id']}",
                    headers=headers(token),
                    json={"data_source_id": DS_ID},
                )
                if ru.status_code in (200, 204):
                    updated += 1
                else:
                    # Try PUT
                    ru2 = requests.put(
                        f"{TOOLJET_URL}/api/data_queries/{q['id']}",
                        headers=headers(token),
                        json={"data_source_id": DS_ID, "options": q.get("options", {})},
                    )
                    if ru2.status_code in (200, 204):
                        updated += 1
                    else:
                        print(f"    ! Failed to update {q['name']}: {ru2.status_code} {ru2.text[:100]}")

        print(f"  Updated {updated}/{len(imported_queries)} query data sources")

        # Test run
        print("\n[6] Test running kpi_summary...")
        kpi_q = next((q for q in imported_queries if q["name"] == "kpi_summary"), None)
        if kpi_q:
            rt = requests.post(
                f"{TOOLJET_URL}/api/data_queries/{kpi_q['id']}/run",
                headers=headers(token),
                json={},
            )
            result = rt.json()
            if result.get("status") == "ok":
                d = result.get("data", [{}])
                if d:
                    print(f"  Total: {d[0].get('total_creators')}")
                    print(f"  Active: {d[0].get('active_pipeline')}")
                    print(f"  Reply Rate: {d[0].get('reply_rate')}%")
            else:
                print(f"  Query error: {result.get('message','?')} - {result.get('description','?')}")

        print(f"\n=== DONE! Open: {TOOLJET_URL}/orbiterss-workspace/apps/{slug} ===")
    else:
        print(f"  FAILED: {r.status_code}")
        print(f"  {r.text[:500]}")


if __name__ == "__main__":
    main()
