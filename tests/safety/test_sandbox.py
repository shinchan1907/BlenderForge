"""Safety and permission boundary verification tests."""

import pytest
from pathlib import Path
from blenderforge.config import BlenderForgeConfig, OperatingMode
from blenderforge.execution.sandbox import SandboxManager, SecurityError, redact_secrets
from blenderforge.experiments.models import CandidateStrategy, ExperimentManifest
from blenderforge.experiments.runner import ExperimentRunner
from blenderforge.storage.db import DatabaseManager


def test_path_traversal_prevention(tmp_path: Path):
    cfg = BlenderForgeConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / ".blenderforge",
        allowed_output_dirs=[tmp_path / ".blenderforge" / "artifacts"]
    )
    cfg.ensure_directories()
    sandbox = SandboxManager(cfg)

    # Allowed path
    safe_target = tmp_path / ".blenderforge" / "artifacts" / "render.png"
    assert sandbox.validate_path_safety(safe_target) == safe_target.resolve()

    # Disallowed traversal targets
    with pytest.raises(SecurityError):
        sandbox.validate_path_safety(Path("C:/Windows/System32/cmd.exe"))

    with pytest.raises(SecurityError):
        sandbox.validate_path_safety(tmp_path / ".." / "outside_dir" / "secret.txt")


def test_secret_redaction():
    text = "Error connecting with token: 'ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890' and api_key='supersecretpassword123'"
    redacted = redact_secrets(text)
    assert "ghp_" not in redacted
    assert "supersecretpassword123" not in redacted
    assert "[REDACTED" in redacted


def test_deny_by_default_in_inspect_mode(tmp_path: Path):
    cfg = BlenderForgeConfig(
        base_dir=tmp_path,
        data_dir=tmp_path / ".blenderforge",
        operating_mode=OperatingMode.INSPECT
    )
    cfg.ensure_directories()
    db = DatabaseManager(cfg.db_path)
    runner = ExperimentRunner(cfg, db)

    manifest = ExperimentManifest(
        id="unsafe_inspect_attempt",
        objective="Attempt scene mutation in inspect mode",
        strategies=[CandidateStrategy(name="Mutate", script_content="import bpy\nbpy.ops.mesh.primitive_cube_add()")],
    )

    with pytest.raises(SecurityError) as exc:
        runner.run_experiment(manifest)
    assert "require at least 'experiment' mode" in str(exc.value)
