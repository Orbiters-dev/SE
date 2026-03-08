# Data Keeper Hub Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Data Keeper export collected data to Shared folder, generate manifest, detect new data signals from team, and enforce read-only access for team agents.

**Architecture:** Data Keeper's main() gets a post-collection step that exports JSON + manifest to `Shared/datakeeper/latest/`. A signal scanner checks `Shared/datakeeper/data_signals/` for new YAML requests. Team CLAUDE.md enforces "check manifest first" rule.

**Tech Stack:** Python, JSON, YAML (PyYAML or manual parsing), Synology Drive (file sync)

---

### Task 1: Add Shared export to data_keeper.py

**Files:**
- Modify: `tools/data_keeper.py` (main function, after collection loop)

**Step 1: Add SHARED_DIR config constant**

After `CACHE_DIR` definition (~line 37), add:

```python
# Shared folder for team-wide access (Synology Drive syncs this)
SHARED_DIR = os.path.join(DIR, "..", "..", "Shared", "datakeeper", "latest")
SIGNALS_DIR = os.path.join(DIR, "..", "..", "Shared", "datakeeper", "data_signals")
```

**Step 2: Add `_export_to_shared()` function**

After `_push_to_pg()` function, add a function that:
- Copies each channel's cache JSON to `SHARED_DIR/{table}.json`
- Generates `manifest.json` with channel metadata (last_collected, row_count, date_range, brands)

```python
def _export_to_shared():
    """Export collected data + manifest to Shared folder for team access."""
    if not os.path.isdir(os.path.join(SHARED_DIR, "..")):
        print("  [Shared] Shared/datakeeper/ not found, skipping export")
        return

    os.makedirs(SHARED_DIR, exist_ok=True)
    manifest = {"last_updated": datetime.now(timezone.utc).isoformat(), "channels": {}}

    for channel, (table, _) in CHANNEL_COLLECTORS.items():
        cache_path = os.path.join(CACHE_DIR, f"{table}.json")
        if not os.path.exists(cache_path):
            continue

        with open(cache_path, "r", encoding="utf-8") as f:
            rows = json.load(f)

        if not rows:
            continue

        # Copy to shared
        shared_path = os.path.join(SHARED_DIR, f"{table}.json")
        with open(shared_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, default=str, ensure_ascii=False)

        # Build manifest entry
        dates = sorted(set(r.get("date", "") for r in rows if r.get("date")))
        brands = sorted(set(r.get("brand", "") for r in rows if r.get("brand")))
        manifest["channels"][table] = {
            "status": "collecting",
            "last_collected": datetime.now(timezone.utc).isoformat(),
            "row_count": len(rows),
            "date_range": [dates[0], dates[-1]] if dates else [],
            "brands": brands,
        }

        print(f"  [Shared] {table}: {len(rows)} rows exported")

    # Write manifest
    manifest_path = os.path.join(SHARED_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str, ensure_ascii=False)
    print(f"  [Shared] manifest.json updated ({len(manifest['channels'])} channels)")
```

**Step 3: Call `_export_to_shared()` in main()**

In `main()`, after the collection loop and before the final print, add:

```python
    # Export to Shared folder for team access
    print("\n[Shared Export]")
    _export_to_shared()
```

**Step 4: Run and verify**

Run: `python tools/data_keeper.py --status` (should still work)
Verify: `Shared/datakeeper/latest/manifest.json` exists after a collection run

**Step 5: Commit**

```bash
git add tools/data_keeper.py
git commit -m "feat(data-keeper): export collected data to Shared folder with manifest"
```

---

### Task 2: Add signal scanner to data_keeper.py

**Files:**
- Modify: `tools/data_keeper.py`

**Step 1: Add `_scan_signals()` function**

```python
def _scan_signals():
    """Scan Shared/datakeeper/data_signals/ for new channel requests."""
    if not os.path.isdir(SIGNALS_DIR):
        return []

    signals = []
    for fname in os.listdir(SIGNALS_DIR):
        if not fname.endswith((".yaml", ".yml")):
            continue
        fpath = os.path.join(SIGNALS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            # Simple YAML parsing (no PyYAML dependency needed)
            sig = {}
            for line in content.strip().split("\n"):
                if ":" in line and not line.strip().startswith("#"):
                    key, val = line.split(":", 1)
                    sig[key.strip()] = val.strip()
            if sig.get("status") == "pending":
                signals.append({"file": fname, **sig})
        except Exception as e:
            print(f"  [Signal] Error reading {fname}: {e}")

    return signals
```

**Step 2: Call scanner in main() and print alerts**

After `_export_to_shared()` call:

```python
    # Scan for new data signals
    signals = _scan_signals()
    if signals:
        print(f"\n[Signals] {len(signals)} pending request(s):")
        for sig in signals:
            print(f"  - {sig.get('channel', '?')} (by {sig.get('requested_by', '?')}) [{sig['file']}]")
```

**Step 3: Commit**

```bash
git add tools/data_keeper.py
git commit -m "feat(data-keeper): scan data_signals for new channel requests"
```

---

### Task 3: Add signal alerts to Communicator

**Files:**
- Modify: `tools/run_communicator.py`

**Step 1: Add signal scanning to communicator**

Add a function to scan `Shared/datakeeper/data_signals/` and include pending signals in the email alert section.

**Step 2: Commit**

```bash
git add tools/run_communicator.py
git commit -m "feat(communicator): include data signal alerts in status email"
```

---

### Task 4: Write Team CLAUDE.md

**Files:**
- Create: `Shared/datakeeper/CLAUDE.md`

**Step 1: Write the team rules file**

This file gets picked up by any Claude agent working in the Shared folder or whose CLAUDE.md references it.

**Step 2: Commit**

Not git-tracked (Synology Drive), so no commit needed.

---

### Task 5: Update GitHub Actions workflow

**Files:**
- Modify: `.github/workflows/data_keeper.yml`

**Step 1: No changes needed**

The Shared export runs inside `data_keeper.py` which already runs in the workflow. However, since GitHub Actions runs on ubuntu (not the NAS), the Shared folder won't exist there — the export gracefully skips with "Shared/datakeeper/ not found". The export only works when run locally or on the NAS where Synology Drive is mounted.

The primary path for team data is: GitHub Actions → PG → local `data_keeper.py --status` or direct PG API read.

For Shared folder updates, we need a local scheduled task or a post-workflow hook.

---

### Task 6: Add local export script

**Files:**
- Create: `tools/export_to_shared.py`

**Step 1: Write a standalone script that pulls from PG and exports to Shared**

This script runs locally (where Synology Drive is mounted) and can be scheduled via Windows Task Scheduler or run manually.

**Step 2: Commit**

```bash
git add tools/export_to_shared.py
git commit -m "feat: add export_to_shared.py for local Shared folder updates"
```
