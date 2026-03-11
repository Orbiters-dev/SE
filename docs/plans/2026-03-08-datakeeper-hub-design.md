# Data Keeper Hub Architecture

**Date:** 2026-03-08
**Status:** Approved
**Author:** WJ

---

## Problem

Each team member's Claude agent independently scrapes APIs (Amazon, Meta, Google, etc.), causing:
- Duplicate API calls across team
- Inconsistent data between agents
- Risk of corrupting shared PostgreSQL (`gk_*` tables)
- No visibility into what data exists team-wide

## Solution

Data Keeper becomes the **single source of truth**. All advertising/sales data flows through it. Team agents consume from a shared read-only cache and auto-register new data sources via signal files.

---

## Architecture

### Data Flow

```
Team agent requests data
        │
        ▼
Check Shared/datakeeper/manifest.json
        │
        ├── Channel EXISTS ──→ Read from Shared/datakeeper/latest/
        │                      (Data Keeper already collecting. Zero API calls.)
        │
        └── Channel NOT FOUND ──→ Agent scrapes API directly
                                   │
                                   ▼
                            Auto-generate signal.yaml
                                   │
                                   ▼
                            Data Keeper detects on next run
                                   │
                                   ▼
                            Channel registered → PG collection starts
                                   │
                                   ▼
                            Exported to Shared/datakeeper/latest/
                                   │
                                   ▼
                            Next request → Channel EXISTS → Read from Shared
```

Once Data Keeper loops in, that channel is permanently handled. Every future request from any team member hits the Shared cache — never the raw API again.

### Three Layers

#### Layer 1: Shared Data Store (Read-Only Distribution)

```
Shared/datakeeper/
├── latest/                  ← Fresh data (JSON), updated 2x daily
│   ├── amazon_ads_daily.json
│   ├── amazon_sales_daily.json
│   ├── meta_ads_daily.json
│   ├── google_ads_daily.json
│   ├── ga4_daily.json
│   ├── klaviyo_daily.json
│   ├── shopify_orders_daily.json
│   └── manifest.json        ← Freshness + row counts per channel
├── data_signals/            ← New source requests (YAML)
└── README.md                ← Schema docs, usage guide
```

- Data Keeper exports PG data to `Shared/datakeeper/latest/` after each collection run
- `manifest.json` contains per-channel metadata: last updated, row count, date range
- Team agents read from here — never from PG directly for bulk data

#### Layer 2: Auto-Detection via Signals

When a team agent scrapes a new API not in manifest, it auto-drops a signal file:

```yaml
# Shared/datakeeper/data_signals/tiktok_ads.yaml
channel: tiktok_ads
requested_by: seeun
created: 2026-03-09
api_endpoint: https://business-api.tiktok.com/...
credentials_needed:
  - TIKTOK_ACCESS_TOKEN
  - TIKTOK_ADVERTISER_ID
sample_data_path: 세은테스트/.tmp/tiktok_sample.json
status: pending    # pending → approved → collecting
```

Signal lifecycle:
1. `pending` — Team agent created signal, Data Keeper detected it
2. `approved` — WJ reviewed, credentials added, channel code implemented
3. `collecting` — Data Keeper actively collecting this channel

Data Keeper scans `data_signals/` each run and includes new signals in Communicator status emails.

#### Layer 3: PG Protection

| Role | PG Read | PG Write (`gk_*`) | Shared Read | Signal Write |
|------|---------|-------------------|-------------|-------------|
| Data Keeper | Yes | Yes | Yes (export) | - |
| Team agents | Yes (API) | **No** | Yes | Yes |

- `gk_*` tables: Data Keeper is the sole writer
- Team agents can query orbitools API for read-only access
- All writes go through Data Keeper → automatic audit trail
- Signal files tracked via git history for accountability

---

## Team Rules (Shared CLAUDE.md)

Every team member's Claude agent must follow these rules:

1. **Need advertising/sales data?** → Check `Shared/datakeeper/latest/` and `manifest.json` first
2. **Channel exists in manifest?** → Read from `latest/` directly. Do NOT call the API.
3. **Channel not in manifest?** → Scrape directly, then auto-generate a signal YAML in `Shared/datakeeper/data_signals/`
4. **Never** write to PostgreSQL `gk_*` tables directly
5. **Never** modify files in `Shared/datakeeper/latest/` — read-only

---

## Manifest Schema

```json
{
  "last_updated": "2026-03-08T08:00:00Z",
  "channels": {
    "amazon_ads_daily": {
      "status": "collecting",
      "last_collected": "2026-03-08T08:00:00Z",
      "row_count": 5230,
      "date_range": ["2024-01-01", "2026-03-08"],
      "brands": ["Naeiae", "Orbitool", "GROSMIMI"]
    },
    "meta_ads_daily": {
      "status": "collecting",
      "last_collected": "2026-03-08T08:00:00Z",
      "row_count": 1089,
      "date_range": ["2024-01-01", "2026-03-08"],
      "brands": ["ONZENNA"]
    }
  }
}
```

---

## Implementation Scope

### Phase 1: Shared Export + Manifest
- Data Keeper exports JSON to `Shared/datakeeper/latest/` after each run
- Generate `manifest.json` with channel metadata
- Create `Shared/datakeeper/README.md` with usage guide

### Phase 2: Signal Detection
- Data Keeper scans `Shared/datakeeper/data_signals/` each run
- New `pending` signals included in Communicator email alerts
- Signal status lifecycle management

### Phase 3: Team CLAUDE.md
- Write shared rules to `Shared/CLAUDE.md` or `Shared/datakeeper/CLAUDE.md`
- Each team folder's agent inherits these rules
- Enforce "check manifest first, signal if new" pattern

### Phase 4: Read-Only API
- Add read-only endpoints to orbitools API for team agents
- `/api/datakeeper/query/?channel=X&date_from=Y&date_to=Z`
- No write endpoints exposed to team agents

---

## Folder Structure (Team-Wide)

```
ORBITERS CLAUDE/
├── Shared/
│   └── datakeeper/
│       ├── latest/              ← Read-only JSON cache (updated 2x daily)
│       ├── data_signals/        ← Team signal files (YAML)
│       ├── manifest.json        ← Channel freshness metadata
│       └── README.md            ← Usage guide
├── WJ Test1/                    ← Data Keeper source code + GitHub Actions
├── Calvin Test/                 ← Team member (reads from Shared)
├── HC Test/                     ← Team member (reads from Shared)
├── 동균 테스트/                  ← Team member (reads from Shared)
├── 세은테스트/                   ← Team member (reads from Shared)
└── ...
```
