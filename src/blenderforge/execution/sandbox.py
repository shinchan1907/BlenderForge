"""Execution security, workspace isolation, and path safety validation."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import List, Optional

from blenderforge.config import BlenderForgeConfig


SECRET_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer|auth)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"), r"\1: [REDACTED]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[REDACTED_API_KEY]"),
]


def redact_secrets(text: str) -> str:
    """Filter out tokens, keys, and credentials from logs safely."""
    if not text:
        return ""
    redacted = text
    for pattern, repl in SECRET_PATTERNS:
        try:
            redacted = pattern.sub(repl, redacted)
        except Exception:
            pass
    return redacted


class SecurityError(Exception):
    """Raised when an operation violates security boundaries."""
    pass


class SandboxManager:
    """Manages isolated workspaces and enforces path traversal guards."""

    def __init__(self, config: BlenderForgeConfig):
        self.config = config

    def create_disposable_workspace(self, experiment_id: str) -> Path:
        """Create a dedicated, isolated directory for an experiment run."""
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", experiment_id)
        workspace = (self.config.workspaces_dir / safe_id).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def validate_path_safety(self, target_path: Path, permitted_roots: Optional[List[Path]] = None) -> Path:
        """
        Ensure target_path resolves strictly within allowlisted directories.
        Prevents directory traversal and unauthorized filesystem modifications.
        """
        resolved = target_path.resolve()
        allowed = permitted_roots or self.config.allowed_output_dirs

        is_safe = False
        for root in allowed:
            try:
                resolved.relative_to(root.resolve())
                is_safe = True
                break
            except ValueError:
                continue

        if not is_safe:
            raise SecurityError(
                f"Path safety violation: '{target_path}' resolves outside allowed boundaries: "
                f"{[str(r.resolve()) for r in allowed]}"
            )

        return resolved

    def cleanup_workspace(self, workspace: Path) -> None:
        """Safely remove a disposable workspace."""
        try:
            if workspace.exists() and workspace.is_dir():
                shutil.rmtree(workspace)
        except Exception:
            pass
