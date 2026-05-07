"""
n8n API Client — 공통 유틸리티
==============================
모든 n8n API 호출을 이 클라이언트로 통일한다.
반복 실수 방지:
  - M-003: Windows SSL revocation check → ssl 컨텍스트로 해결
  - M-013: POST/PUT 시 active 필드 자동 제거
  - M-014: cp949 인코딩 → utf-8 강제

Usage:
    from n8n_api_client import N8nClient

    n8n = N8nClient()
    workflows = n8n.list_workflows()
    wf = n8n.get_workflow("abc123")
    n8n.create_workflow({"name": "Test", "nodes": [...]})
    n8n.update_workflow("abc123", {"name": "Test", "nodes": [...]})
    n8n.activate_workflow("abc123")
    n8n.deactivate_workflow("abc123")
    executions = n8n.list_executions(workflow_id="abc123", limit=5)
"""

import os
import sys
import json
import ssl
import urllib.request
import urllib.error
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(__file__))
from env_loader import load_env

load_env()

# Windows cp949 stdout fix (M-001)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# SSL context that skips revocation check (M-003)
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# Fields that n8n rejects on POST/PUT (M-013)
_READONLY_FIELDS = {"active", "id", "createdAt", "updatedAt"}


class N8nClient:
    """Stateless n8n REST API client."""

    def __init__(self, base_url: str = "", api_key: str = ""):
        self.base_url = (
            base_url
            or os.getenv("N8N_BASE_URL", "https://n8n.orbiters.co.kr")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("N8N_API_KEY", "")
        if not self.api_key:
            raise ValueError("N8N_API_KEY not set")

    # ── Low-level request ────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[dict] = None,
        timeout: int = 30,
    ) -> Any:
        url = f"{self.base_url}/api/v1{path}"
        body = None
        if data is not None:
            # M-014: ensure utf-8 encoding
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("X-N8N-API-KEY", self.api_key)
        req.add_header("Content-Type", "application/json; charset=utf-8")

        try:
            # M-003: use SSL context that skips revocation check
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(
                f"n8n API {method} {path} → {e.code}: {body_text}"
            ) from e

    @staticmethod
    def _strip_readonly(data: dict) -> dict:
        """Remove read-only fields before POST/PUT (M-013)."""
        return {k: v for k, v in data.items() if k not in _READONLY_FIELDS}

    # ── Workflows ────────────────────────────────────────────────────

    def list_workflows(self, limit: int = 250) -> list[dict]:
        result = self._request("GET", f"/workflows?limit={limit}")
        return result.get("data", result.get("workflows", []))

    def get_workflow(self, wf_id: str) -> dict:
        return self._request("GET", f"/workflows/{wf_id}")

    def create_workflow(self, data: dict) -> dict:
        clean = self._strip_readonly(data)
        return self._request("POST", "/workflows", clean)

    def update_workflow(self, wf_id: str, data: dict) -> dict:
        clean = self._strip_readonly(data)
        # PUT requires "name" (M-013 related)
        if "name" not in clean:
            existing = self.get_workflow(wf_id)
            clean["name"] = existing.get("name", "Unnamed")
        return self._request("PUT", f"/workflows/{wf_id}", clean)

    def delete_workflow(self, wf_id: str) -> dict:
        return self._request("DELETE", f"/workflows/{wf_id}")

    def activate_workflow(self, wf_id: str) -> dict:
        return self._request("PATCH", f"/workflows/{wf_id}", {"active": True})

    def deactivate_workflow(self, wf_id: str) -> dict:
        return self._request("PATCH", f"/workflows/{wf_id}", {"active": False})

    # ── Executions ───────────────────────────────────────────────────

    def list_executions(
        self,
        workflow_id: str = "",
        limit: int = 20,
        status: str = "",
    ) -> list[dict]:
        params = [f"limit={limit}"]
        if workflow_id:
            params.append(f"workflowId={workflow_id}")
        if status:
            params.append(f"status={status}")
        qs = "&".join(params)
        result = self._request("GET", f"/executions?{qs}")
        return result.get("data", result.get("results", []))

    def get_execution(self, exec_id: str) -> dict:
        return self._request("GET", f"/executions/{exec_id}")

    # ── Credentials ──────────────────────────────────────────────────

    def list_credentials(self) -> list[dict]:
        result = self._request("GET", "/credentials")
        return result.get("data", [])

    # ── Convenience ──────────────────────────────────────────────────

    def find_workflow_by_name(self, name: str) -> Optional[dict]:
        """Find first workflow matching name (case-insensitive partial)."""
        for wf in self.list_workflows():
            if name.lower() in wf.get("name", "").lower():
                return wf
        return None

    def scan_workflows_for_text(self, text: str) -> list[dict]:
        """Scan all workflow JSON for a text string (e.g., API key audit)."""
        matches = []
        for wf in self.list_workflows():
            full = self.get_workflow(wf["id"])
            if text in json.dumps(full, ensure_ascii=False):
                matches.append({"id": wf["id"], "name": wf.get("name", "")})
        return matches


# ── Drop-in replacement for legacy n8n_request() ────────────────────
# Usage: from n8n_api_client import n8n_request
# This is a direct replacement for the 23+ local n8n_request() functions
# scattered across setup_n8n_*.py, clone_n8n_to_test.py, etc.

_default_client = None

def n8n_request(method: str, path: str, data: Any = None) -> Any:
    """Drop-in compatible function replacing per-file n8n_request() implementations.

    Handles: SSL skip (M-003), active field strip (M-013), utf-8 (M-014).
    """
    global _default_client
    if _default_client is None:
        _default_client = N8nClient()
    if data is not None and method in ("POST", "PUT"):
        data = N8nClient._strip_readonly(data)
    return _default_client._request(method, path, data)


# ── Quick CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="n8n API Client CLI")
    parser.add_argument("--list", action="store_true", help="List all workflows")
    parser.add_argument("--get", metavar="ID", help="Get workflow by ID")
    parser.add_argument("--executions", metavar="ID", help="List executions for workflow")
    parser.add_argument("--scan", metavar="TEXT", help="Scan all workflows for text")
    parser.add_argument("--credentials", action="store_true", help="List credentials")
    args = parser.parse_args()

    client = N8nClient()

    if args.list:
        for wf in client.list_workflows():
            status = "ON" if wf.get("active") else "OFF"
            print(f"  [{status}] {wf['id']}  {wf.get('name', '?')}")
    elif args.get:
        print(json.dumps(client.get_workflow(args.get), indent=2, ensure_ascii=False))
    elif args.executions:
        for ex in client.list_executions(workflow_id=args.executions):
            print(f"  {ex.get('id')}  {ex.get('status')}  {ex.get('startedAt', '?')}")
    elif args.scan:
        for m in client.scan_workflows_for_text(args.scan):
            print(f"  {m['id']}  {m['name']}")
    elif args.credentials:
        for c in client.list_credentials():
            print(f"  {c.get('id')}  {c.get('name')}  [{c.get('type')}]")
    else:
        parser.print_help()
