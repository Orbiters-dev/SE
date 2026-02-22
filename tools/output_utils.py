"""output_utils.py — Centralized output path management for WJ Test1.

All final Excel outputs → Data Storage/{workflow}/
All intermediate data → .tmp/
Naming: {base_name}_{YYYY-MM-DD}_v{N}.xlsx (auto-incrementing version)
"""

import os
import re
import glob
from datetime import datetime

# ── Root paths ─────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
DATA_STORAGE = os.path.join(ROOT, "Data Storage")
INTERMEDIATE = os.path.join(ROOT, ".tmp")
POLAR_DATA = os.path.join(INTERMEDIATE, "polar_data")

# ── Workflow → subfolder mapping ────────────────────────────────────
WORKFLOW_DIRS = {
    "polar": "polar",
    "cs": "cs",
    "influencer": "influencer",
    "marketing": "marketing",
    "export": "export",
    "misc": "misc",
}


def get_next_version(directory: str, base_pattern: str, extension: str = ".xlsx") -> int:
    """Scan directory for {base_pattern}_v{N}{ext} and return next version number."""
    if not os.path.isdir(directory):
        return 1
    pattern = os.path.join(directory, f"{base_pattern}_v*{extension}")
    existing = glob.glob(pattern)
    if not existing:
        return 1
    versions = []
    for f in existing:
        match = re.search(r'_v(\d+)' + re.escape(extension) + r'$', f)
        if match:
            versions.append(int(match.group(1)))
    return max(versions) + 1 if versions else 1


def get_output_path(workflow: str, base_name: str,
                    date_str: str = None,
                    extension: str = ".xlsx") -> str:
    """Build versioned output path for a final deliverable.

    Returns: Data Storage/{workflow}/{base_name}_{YYYY-MM-DD}_v{N}.xlsx
    Auto-increments version if same date files exist.
    """
    subdir = WORKFLOW_DIRS.get(workflow, workflow)
    out_dir = os.path.join(DATA_STORAGE, subdir)
    os.makedirs(out_dir, exist_ok=True)

    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    base_with_date = f"{base_name}_{date_str}"
    version = get_next_version(out_dir, base_with_date, extension)
    filename = f"{base_with_date}_v{version}{extension}"
    return os.path.join(out_dir, filename)


def get_latest_file(workflow: str, base_name: str,
                    extension: str = ".xlsx") -> str | None:
    """Find the most recent versioned file for a workflow/base_name.

    Scans Data Storage/{workflow}/ for {base_name}_*_v*{ext},
    returns the one with the latest date and highest version.
    Returns None if no file found.
    """
    subdir = WORKFLOW_DIRS.get(workflow, workflow)
    out_dir = os.path.join(DATA_STORAGE, subdir)
    if not os.path.isdir(out_dir):
        return None

    pattern = os.path.join(out_dir, f"{base_name}_*_v*{extension}")
    files = glob.glob(pattern)
    if not files:
        return None

    # Parse date and version from each file, sort descending
    parsed = []
    for f in files:
        fname = os.path.basename(f)
        match = re.search(
            r'_(\d{4}-\d{2}-\d{2})_v(\d+)' + re.escape(extension) + r'$',
            fname
        )
        if match:
            parsed.append((match.group(1), int(match.group(2)), f))

    if not parsed:
        return None

    # Sort by date desc, then version desc
    parsed.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return parsed[0][2]


def get_intermediate_path(subdir: str, filename: str) -> str:
    """Build path for intermediate/temp data in .tmp/.

    Returns: .tmp/{subdir}/{filename}
    """
    if subdir:
        out_dir = os.path.join(INTERMEDIATE, subdir)
    else:
        out_dir = INTERMEDIATE
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, filename)


def get_backup_path(original_path: str) -> str:
    """Generate a timestamped backup path next to the original file.

    E.g.: file.xlsx → file_backup_2026-02-22_1430.xlsx
    """
    base, ext = os.path.splitext(original_path)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    return f"{base}_backup_{ts}{ext}"
