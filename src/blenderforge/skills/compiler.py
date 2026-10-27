"""Skill compilation, syntax validation, and evidence-gated promotion."""

from __future__ import annotations

import ast
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from blenderforge.skills.models import SkillDefinition, SkillStatus
from blenderforge.storage.db import DatabaseManager


class SkillCompilationError(Exception):
    pass


class SkillCompiler:
    """Compiles verified execution strategies into versioned skills."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def compile_skill(
        self,
        skill_id: str,
        name: str,
        domain: str,
        strategy: str,
        code: str,
        expected_outputs: Optional[List[str]] = None,
        preconditions: Optional[List[str]] = None,
        initial_status: SkillStatus = SkillStatus.EXPERIMENTAL,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> SkillDefinition:
        """Validate code syntax, hash content, and compile new skill."""
        # 1. Validate Python AST syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise SkillCompilationError(f"Skill code syntax error at line {e.lineno}: {e.msg}") from e

        # 2. Compute code hash
        code_hash = hashlib.sha256(code.strip().encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).isoformat()

        skill = SkillDefinition(
            id=skill_id,
            name=name,
            domain=domain,
            status=initial_status,
            version="1.0.0",
            supported_versions=[">=4.0"],
            preconditions=preconditions or [],
            strategy=strategy,
            code=code,
            expected_outputs=expected_outputs or [],
            code_hash=code_hash,
            evidence=evidence or {},
            created_at=now,
            updated_at=now,
        )

        return skill

    def promote_skill(
        self,
        skill: SkillDefinition,
        target_status: SkillStatus,
        benchmark_evidence: Dict[str, Any]
    ) -> SkillDefinition:
        """
        Enforce strict machine-verifiable gate:
        Promotion to 'validated' or 'stable' requires passing benchmark results.
        """
        if target_status in (SkillStatus.VALIDATED, SkillStatus.STABLE):
            if not benchmark_evidence or not benchmark_evidence.get("passed"):
                raise PermissionError(
                    f"Cannot promote skill '{skill.id}' to '{target_status.value}': "
                    f"Missing passing machine-verifiable benchmark evidence. Received: {benchmark_evidence}"
                )

        skill.status = target_status
        skill.evidence.update({"promotion_record": benchmark_evidence})
        skill.updated_at = datetime.now(timezone.utc).isoformat()
        return skill
