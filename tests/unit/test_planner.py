"""Tests for the Unified Intelligent Planner."""

from pathlib import Path
from blenderforge.config import BlenderForgeConfig, OperatingMode
from blenderforge.orchestrator.planner import ExecutionStrategyType, UnifiedPlanner
from blenderforge.skills.compiler import SkillCompiler
from blenderforge.skills.models import SkillStatus
from blenderforge.skills.registry import SkillRegistry
from blenderforge.storage.db import DatabaseManager


def test_planner_selects_validated_skill(tmp_path: Path):
    cfg = BlenderForgeConfig(base_dir=tmp_path, data_dir=tmp_path / ".blenderforge")
    cfg.ensure_directories()
    db = DatabaseManager(cfg.db_path)
    planner = UnifiedPlanner(cfg, db)

    # Register a validated skill
    reg = SkillRegistry(db)
    compiler = SkillCompiler(db)
    skill = compiler.compile_skill(
        skill_id="modeling.procedural_pipe",
        name="Procedural Pipe Generator",
        domain="modeling",
        strategy="Generate hollow cylinder curve",
        code="import bpy\nbpy.ops.mesh.primitive_cylinder_add()",
    )
    validated_skill = compiler.promote_skill(skill, SkillStatus.VALIDATED, {"passed": True})
    reg.save_skill(validated_skill)

    # Ask planner for procedural pipe
    plan = planner.formulate_plan("Build a procedural pipe for mechanical duct")
    assert plan.selected_strategy == ExecutionStrategyType.VALIDATED_SKILL
    assert plan.steps[0].target == "modeling.procedural_pipe"


def test_planner_selects_rea_for_reverse_engineering(tmp_path: Path):
    cfg = BlenderForgeConfig(base_dir=tmp_path, data_dir=tmp_path / ".blenderforge")
    cfg.ensure_directories()
    db = DatabaseManager(cfg.db_path)
    planner = UnifiedPlanner(cfg, db)

    plan = planner.formulate_plan("Reverse engineer external Blender add-on and analyze operators")
    assert plan.selected_strategy == ExecutionStrategyType.REA_RESEARCH
    assert plan.required_mode == OperatingMode.INSPECT
