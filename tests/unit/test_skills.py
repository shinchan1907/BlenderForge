"""Tests for skill compilation, FTS5 retrieval, and promotion gate."""

import pytest
from pathlib import Path
from blenderforge.skills.compiler import SkillCompiler, SkillCompilationError
from blenderforge.skills.models import SkillStatus
from blenderforge.skills.registry import SkillRegistry
from blenderforge.storage.db import DatabaseManager


def test_skill_compiler_valid(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test.db")
    compiler = SkillCompiler(db)

    code = "import bpy\nbpy.ops.mesh.primitive_cube_add(size=2.0)"
    skill = compiler.compile_skill(
        skill_id="modeling.cube_v1",
        name="Primitive Cube",
        domain="modeling",
        strategy="Create a unit cube",
        code=code,
    )

    assert skill.status == SkillStatus.EXPERIMENTAL
    assert skill.code_hash is not None
    assert len(skill.code_hash) == 64


def test_skill_compiler_syntax_error(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test.db")
    compiler = SkillCompiler(db)

    invalid_code = "def broken(:"
    with pytest.raises(SkillCompilationError):
        compiler.compile_skill(
            skill_id="broken_skill",
            name="Broken",
            domain="test",
            strategy="invalid",
            code=invalid_code,
        )


def test_skill_promotion_gate(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test.db")
    compiler = SkillCompiler(db)
    registry = SkillRegistry(db)

    skill = compiler.compile_skill(
        skill_id="modeling.bevel_cube",
        name="Procedural Bevel Cube",
        domain="modeling",
        strategy="Bevel cube modifier",
        code="import bpy\nbpy.ops.mesh.primitive_cube_add()",
    )
    registry.save_skill(skill)

    # Attempt to promote without benchmark evidence -> must raise PermissionError
    with pytest.raises(PermissionError):
        compiler.promote_skill(skill, SkillStatus.VALIDATED, benchmark_evidence={})

    with pytest.raises(PermissionError):
        compiler.promote_skill(skill, SkillStatus.VALIDATED, benchmark_evidence={"passed": False})

    # Promote with passing benchmark evidence -> succeeds
    promoted = compiler.promote_skill(skill, SkillStatus.VALIDATED, benchmark_evidence={"passed": True, "score": 1.0})
    assert promoted.status == SkillStatus.VALIDATED
    registry.save_skill(promoted)

    # Verify search in registry
    results = registry.search_skills("bevel cube")
    assert len(results) >= 1
    assert results[0].id == "modeling.bevel_cube"
    assert results[0].status == SkillStatus.VALIDATED
