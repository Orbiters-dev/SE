"""Extract Polar MCP query results for Klaviyo and save as JSON."""
import json, os, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

KL1_SRC = r"C:\Users\user\.claude\projects\c--Users-user-Downloads-ORBITERS-CLAUDE-ORBITERS-CLAUDE\727babd3-d689-46c2-9abd-bbffd1a7a5b3\tool-results\mcp-claude_ai_Polar_Remote_MC-generate_report-1771726930785.txt"
KL2_SRC = r"C:\Users\user\.claude\projects\c--Users-user-Downloads-ORBITERS-CLAUDE-ORBITERS-CLAUDE\727babd3-d689-46c2-9abd-bbffd1a7a5b3\tool-results\mcp-claude_ai_Polar_Remote_MC-generate_report-1771726932052.txt"

for src, dst in [
    (KL1_SRC, "kl1_flow_monthly.json"),
    (KL2_SRC, "kl2_campaign_monthly.json"),
]:
    with open(src, encoding="utf-8") as f:
        wrapper = json.load(f)
    inner = json.loads(wrapper[0]["text"])
    out = {"tableData": inner.get("tableData", []), "totalData": inner.get("totalData", [])}
    out_path = os.path.join(DATA_DIR, dst)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Saved {dst}: {len(out['tableData'])} rows")

print("Done!")
