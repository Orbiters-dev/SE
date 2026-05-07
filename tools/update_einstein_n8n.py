"""SE Operations Hub에 아인슈타인 기능 노드 추가 + 리포터 제거"""
import json, sys, os
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(PROJ, ".tmp", "se_ops_hub_current.json"), "r", encoding="utf-8") as f:
    wf = json.load(f)

nodes = wf["nodes"]
connections = wf.get("connections", {})

# 1. Remove reporter sticky
reporter_name = "\U0001f7e5 \ub9ac\ud3ec\ud130 Section"
nodes = [n for n in nodes if n.get("name") != reporter_name]
if reporter_name in connections:
    del connections[reporter_name]
print("Removed reporter section")

# 2. Update header 7 -> 6
for n in nodes:
    if "\U0001f3e0" in n.get("name", ""):
        c = n["parameters"]["content"]
        c = c.replace("\uc5d0\uc774\uc804\ud2b8 7\uba85", "\uc5d0\uc774\uc804\ud2b8 6\uba85")
        n["parameters"]["content"] = c
        print("Header: 7 -> 6")

# 3. Update einstein sticky with auto-schedule info
einstein_content = (
    "## \u2b1c \uc544\uc778\uc288\ud0c0\uc778 \u2014 \ud6a8\uc728/\ucc3d\uc758\uc131 \uac10\uc0ac\n\n"
    "**\uc5ed\ud560**: \uc790\ub3d9 \ud5ec\uc2a4\uccb4\ud06c + \ud504\ub85c\uc138\uc2a4 \uc9c4\ub2e8 + \uac1c\uc120 \uc81c\uc548\n\n"
    "**\uc790\ub3d9 \uc2a4\ucf00\uc904**:\n"
    "\u2022 **\uc8fc\uac04 \ud5ec\uc2a4\uccb4\ud06c**: \ub9e4\uc8fc \uc6d4 09:00 KST\n"
    "  \u2192 7\uc77c\uac04 Actions \uc131\uacf5\ub960, \ubc18\ubcf5 \uc5d0\ub7ec, \uc5d0\uc774\uc804\ud2b8 \ud65c\ub3d9\ub3c4\n"
    "\u2022 **\uc77c\uc77c \ubbf8\ub2c8\uccb4\ud06c**: \ub9e4\uc77c 18:00 KST\n"
    "  \u2192 \ub2f9\uc77c \uc2e4\ud589 \ud604\ud669, \uc2e4\ud328 \uc791\uc5c5 \uc54c\ub9bc\n\n"
    "**\ubd84\uc11d \ud56d\ubaa9**:\n"
    "\u2022 \ubc18\ubcf5 \uc5d0\ub7ec \ud0d0\uc9c0 (mistakes.md \ud30c\uc2f1)\n"
    "\u2022 GitHub Actions \uc2e4\ud328\uc728 > 30% \uacbd\uace0\n"
    "\u2022 \uc5d0\uc774\uc804\ud2b8\ubcc4 \ud65c\ub3d9\ub3c4 (git log)\n"
    "\u2022 \ubbf8\uc644\ub8cc \uc791\uc5c5 \ucd94\uc801 (session_*.md)\n\n"
    "**\ub3c4\uad6c**: `tools/run_einstein.py`\n"
    "**Actions**: `einstein_weekly.yml`, `einstein_daily.yml`\n"
    "**\ub9ac\ud3ec\ud2b8**: Teams \uc804\uc1a1"
)

einstein_x = 2000
einstein_y = 4400
for n in nodes:
    if "\uc544\uc778\uc288\ud0c0\uc778" in n.get("name", ""):
        n["parameters"]["content"] = einstein_content
        pos = n.get("position", [2000, 4400])
        einstein_x = pos[0]
        einstein_y = pos[1]
        print(f"Updated einstein sticky at ({einstein_x}, {einstein_y})")

# 4. Add functional nodes for Einstein
new_nodes = [
    {
        "parameters": {
            "rule": {"interval": [{"triggerAtHour": 0, "triggerAtDay": 1}]}
        },
        "id": "einstein-weekly-schedule",
        "name": "Einstein Weekly (Mon 09:00 KST)",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [einstein_x, einstein_y + 280]
    },
    {
        "parameters": {
            "jsCode": (
                "// Einstein Weekly Health Check\n"
                "// Tool: python tools/run_einstein.py --mode weekly\n"
                "// Analyzes: 7-day Actions, mistakes.md, sessions, git log\n"
                "// Output: Teams full report\n"
                "return [{json: {agent: 'einstein', mode: 'weekly'}}];"
            )
        },
        "id": "einstein-weekly-info",
        "name": "Weekly Analysis Metadata",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [einstein_x + 300, einstein_y + 280]
    },
    {
        "parameters": {
            "rule": {"interval": [{"triggerAtHour": 9}]}
        },
        "id": "einstein-daily-schedule",
        "name": "Einstein Daily (18:00 KST)",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [einstein_x, einstein_y + 430]
    },
    {
        "parameters": {
            "jsCode": (
                "// Einstein Daily Mini Check\n"
                "// Tool: python tools/run_einstein.py --mode daily\n"
                "// Analyzes: 1-day status, new errors\n"
                "// Output: Teams short summary\n"
                "return [{json: {agent: 'einstein', mode: 'daily'}}];"
            )
        },
        "id": "einstein-daily-info",
        "name": "Daily Check Metadata",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [einstein_x + 300, einstein_y + 430]
    },
]

nodes.extend(new_nodes)

# 5. Add connections
connections["Einstein Weekly (Mon 09:00 KST)"] = {
    "main": [[{"node": "Weekly Analysis Metadata", "type": "main", "index": 0}]]
}
connections["Einstein Daily (18:00 KST)"] = {
    "main": [[{"node": "Daily Check Metadata", "type": "main", "index": 0}]]
}

# 6. Save
payload = {
    "name": wf["name"],
    "nodes": nodes,
    "connections": connections,
    "settings": wf.get("settings", {}),
    "staticData": wf.get("staticData", None),
}

out = os.path.join(PROJ, ".tmp", "se_ops_hub_final.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)

print(f"Final: {len(nodes)} nodes")
print(f"Saved: {out}")
