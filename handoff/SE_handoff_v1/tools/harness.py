#!/usr/bin/env python3
"""Compatibility wrapper — all logic lives in `harness_5stage.py`.

The legacy dual-provider Harness (OpenAI/Gemini) was renamed
`harness_legacy_dual_provider.py`. The active implementation is the
3-LLM Generator-Evaluator orchestrator in `harness_5stage.py`, which
exposes the `run` / `status` subcommands the harness_runner hook and
n8n_put_guard hook depend on.

This file forwards CLI invocations to harness_5stage without changing
the entry-point path (`python tools/harness.py ...`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_5stage import main  # noqa: E402  (intentional path insert)

if __name__ == "__main__":
    main()
