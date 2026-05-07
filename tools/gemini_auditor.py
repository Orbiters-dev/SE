#!/usr/bin/env python3
"""
Gemini Auditor — Google Gemini-based independent evaluator
Same interface as CodexAuditor, different provider for adversarial audit.

Usage:
    from gemini_auditor import GeminiAuditor
    auditor = GeminiAuditor()
    result = auditor.audit(task_type="dm", content=draft, context={...})
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime

# .env load
env_path = Path(__file__).parent.parent / ".env"
if not env_path.exists():
    env_path = Path("c:/Users/orbit/Desktop/seeun/.env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from google import genai
from google.genai import types

# Import shared rules
from codex_auditor import AUDIT_RULES


class GeminiAuditor:
    """Google Gemini-based independent auditor agent"""

    def __init__(self, model: str = "gemini-2.5-flash"):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.provider = "gemini"
        self.log_dir = Path(__file__).parent.parent / ".tmp" / "auditor_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def audit(self, task_type: str, content: str, context: dict = None,
              extra_rules: str = None) -> dict:
        rules = AUDIT_RULES.get(task_type, AUDIT_RULES["general"])

        system_prompt = rules["system"]
        if extra_rules:
            system_prompt += f"\n\n[Additional Rules]\n{extra_rules}"

        # Auto-inject size metadata for code audits
        line_count = content.count("\n") + 1
        byte_size = len(content.encode("utf-8"))
        size_meta = f"[Size] {line_count} lines, {byte_size} bytes"

        user_prompt = "Audit the following output.\n\n"
        user_prompt += f"{size_meta}\n\n"
        if context:
            user_prompt += f"[Context]\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        user_prompt += f"[Output]\n{content}\n\n"
        user_prompt += rules["check_format"]

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )

            result_text = response.text.strip()

            # Extract JSON if wrapped in markdown
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            result = json.loads(result_text)
            result["_provider"] = self.provider
            result["_model"] = self.model
            self._save_log(task_type, content, result)
            return result

        except json.JSONDecodeError as e:
            error_result = {
                "pass": False,
                "score": 0,
                "violations": [{"rule": "JSON_PARSE_ERROR", "location": "auditor",
                                "fix": f"Gemini returned invalid JSON: {e}"}],
                "error": str(e),
                "_provider": self.provider,
                "_model": self.model,
            }
            self._save_log(task_type, content, error_result)
            return error_result
        except Exception as e:
            error_result = {
                "pass": False,
                "score": 0,
                "violations": [{"rule": "SYSTEM_ERROR", "location": "auditor", "fix": str(e)}],
                "error": str(e),
                "_provider": self.provider,
                "_model": self.model,
            }
            self._save_log(task_type, content, error_result)
            return error_result

    def audit_loop(self, task_type: str, content: str, context: dict = None,
                   extra_rules: str = None, max_loops: int = 2,
                   builder_fix_fn=None) -> dict:
        loops = []
        current_content = content

        for i in range(max_loops):
            result = self.audit(task_type, current_content, context, extra_rules)
            loops.append({
                "loop": i + 1,
                "result": result,
                "content_before": current_content
            })

            if result.get("pass", False):
                return {
                    "final_content": current_content,
                    "loops": loops,
                    "final_pass": True,
                    "final_score": result.get("score", 100)
                }

            if builder_fix_fn and callable(builder_fix_fn):
                current_content = builder_fix_fn(
                    current_content, result.get("violations", [])
                )
            else:
                improved = (result.get("improved_draft")
                           or result.get("improved_code")
                           or current_content)
                if improved and improved != current_content:
                    current_content = improved
                else:
                    break

        final_result = loops[-1]["result"] if loops else {}
        return {
            "final_content": current_content,
            "loops": loops,
            "final_pass": final_result.get("pass", False),
            "final_score": final_result.get("score", 0)
        }

    def _save_log(self, task_type: str, content: str, result: dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"gemini_{task_type}_{timestamp}.json"
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "task_type": task_type,
            "provider": self.provider,
            "model": self.model,
            "content_preview": content[:500],
            "result": result
        }
        log_file.write_text(
            json.dumps(log_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
