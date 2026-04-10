#!/usr/bin/env python3
"""Debug: UserPromptSubmit stdin에 뭐가 오는지 확인"""
import sys
import json
import datetime

raw = sys.stdin.read()
with open(".tmp/hook_debug.txt", "a", encoding="utf-8") as f:
    f.write(f"\n--- {datetime.datetime.now()} ---\n")
    f.write(raw)
    f.write("\n")

print(json.dumps({"continue": True}))