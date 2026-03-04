"""
output_utils.py — Shared path utilities for WAT tools.

Functions:
  get_output_path(category, prefix) -> Path
      Generates a versioned output path: Data Storage/{category}/{prefix}_{date}_v{N}.xlsx

  get_intermediate_path(subdir, filename) -> Path
      Returns a .tmp path: .tmp/{subdir}/{filename}

  get_latest_file(category, prefix) -> Path | None
      Finds the most recent versioned file for a given prefix.

  DATA_STORAGE: Path to the 'Data Storage/' directory.
"""

import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_STORAGE = ROOT / "Data Storage"
TMP = ROOT / ".tmp"


def get_output_path(category: str, prefix: str, base_dir: str = None) -> Path:
    """
    Returns a versioned output path.
    Example: get_output_path("polar", "financial_model")
             → Data Storage/polar/financial_model_2026-02-28_v1.xlsx
    If base_dir is given, uses that directory directly (no category subfolder).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if base_dir:
        out_dir = Path(base_dir)
    else:
        out_dir = DATA_STORAGE / category
    out_dir.mkdir(parents=True, exist_ok=True)

    # Find next version number for today
    pattern = re.compile(rf"^{re.escape(prefix)}_{re.escape(today)}_v(\d+)\.xlsx$")
    existing_versions = []
    for f in out_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            existing_versions.append(int(m.group(1)))

    next_version = max(existing_versions, default=0) + 1
    return out_dir / f"{prefix}_{today}_v{next_version}.xlsx"


def get_intermediate_path(subdir: str, filename: str) -> Path:
    """
    Returns a .tmp intermediate path.
    Example: get_intermediate_path("polar_data", "q6.json")
             → .tmp/polar_data/q6.json
    """
    if subdir:
        out_dir = TMP / subdir
    else:
        out_dir = TMP
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / filename


def get_latest_file(category: str, prefix: str) -> Path | None:
    """
    Finds the most recent versioned file matching {prefix}_*.xlsx in Data Storage/{category}/.
    Returns None if no matching file found.
    """
    out_dir = DATA_STORAGE / category
    if not out_dir.exists():
        return None

    pattern = re.compile(rf"^{re.escape(prefix)}_(\d{{4}}-\d{{2}}-\d{{2}})_v(\d+)\.xlsx$")
    candidates = []
    for f in out_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            date_str, version = m.group(1), int(m.group(2))
            candidates.append((date_str, version, f))

    if not candidates:
        return None

    # Sort by date desc, then version desc
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]
