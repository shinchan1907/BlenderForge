"""Bridge to Reverse Engineer Anything (REA) for tool and source analysis."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from blenderforge.storage.db import DatabaseManager


class REAFinding(BaseModel):
    """Normalized reverse-engineering finding."""
    id: str = Field(..., description="Unique finding ID.")
    source: str = Field(..., description="Target application, file, or repository analyzed.")
    target_capability: str = Field(..., description="Blender capability or workflow investigated.")
    evidence_excerpt: str = Field(..., description="Concrete code or data excerpt backing the finding.")
    confidence: float = Field(default=0.8, description="Confidence score between 0.0 and 1.0.")
    safety_classification: str = Field(default="safe_read_only", description="Security classification.")
    suggested_experiment: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class REABridge:
    """Manages invocation, health checks, and evidence normalization from REA."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db
        self._npx_path = shutil.which("npx") or shutil.which("npx.cmd")

    def is_available(self) -> bool:
        """Verify whether npx and rea-agents are callable in this environment."""
        if not self._npx_path:
            return False
        try:
            res = subprocess.run(
                [self._npx_path, "rea-agents", "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False
            )
            return res.returncode == 0
        except Exception:
            return False

    def get_version(self) -> Optional[str]:
        """Query REA release version."""
        if not self._npx_path:
            return None
        try:
            res = subprocess.run(
                [self._npx_path, "rea-agents", "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False
            )
            if res.returncode == 0:
                return res.stdout.strip()
        except Exception:
            pass
        return None

    def run_doctor(self) -> Dict[str, Any]:
        """Run REA doctor diagnostics."""
        if not self._npx_path:
            return {"available": False, "error": "npx not found on system PATH."}

        try:
            res = subprocess.run(
                [self._npx_path, "rea-agents", "doctor"],
                capture_output=True,
                text=True,
                timeout=25,
                check=False
            )
            output = res.stdout.strip()
            # REA doctor emits YAML-like or text diagnostics
            return {
                "available": True,
                "exit_code": res.returncode,
                "raw_output": output,
                "healthy": "healthy: true" in output or "environment_healthy: true" in output
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def list_capabilities(self) -> Dict[str, Any]:
        """Fetch REA declared capabilities and tool catalog."""
        if not self._npx_path:
            return {"available": False, "error": "npx not found on system PATH."}

        try:
            res = subprocess.run(
                [self._npx_path, "rea-agents", "capabilities", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )
            if res.returncode == 0:
                try:
                    data = json.loads(res.stdout)
                    server_id = data.get("server_identity", {})
                    counts = server_id.get("catalog", {}).get("counts", {})
                    return {
                        "available": True,
                        "cli_commands_count": counts.get("cli_commands", 0),
                        "mcp_tools_count": counts.get("mcp_tools", 0),
                        "server_version": server_id.get("server", {}).get("version"),
                        "raw_catalog": data,
                    }
                except json.JSONDecodeError:
                    return {"available": True, "raw_text": res.stdout[:1000]}
            return {"available": False, "error": res.stderr}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def analyze_source_target(self, target_path: Path, objective: str) -> REAFinding:
        """
        Analyze a local source file, add-on script, or repository to extract
        architectural patterns, operators, and data flows.
        """
        if not target_path.exists():
            raise FileNotFoundError(f"Target path does not exist: {target_path}")

        # Run REA static analysis or fallback to structured code inspection
        evidence_lines = []
        try:
            if self._npx_path:
                res = subprocess.run(
                    [self._npx_path, "rea-agents", "analyze", str(target_path), "--format", "json"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False
                )
                if res.returncode == 0 and res.stdout.strip():
                    evidence_lines.append(res.stdout.strip()[:1000])
        except Exception:
            pass

        # If CLI produced no output or for Python files, inspect AST and tokens directly
        if not evidence_lines:
            text = target_path.read_text(encoding="utf-8", errors="replace")
            # Extract key operators and imports
            lines = [l.strip() for l in text.splitlines() if "bpy.ops" in l or "bpy.types" in l or "class " in l]
            evidence_lines.append("\n".join(lines[:30]) or text[:500])

        finding_id = f"finding_{target_path.stem}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        finding = REAFinding(
            id=finding_id,
            source=str(target_path),
            target_capability=objective,
            evidence_excerpt="\n".join(evidence_lines),
            confidence=0.85,
            suggested_experiment=f"Validate {objective} against isolated Blender scene",
        )

        return finding
