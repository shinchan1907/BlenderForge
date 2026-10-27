"""Tests for BlenderForge CLI commands."""

import json
from pathlib import Path
from click.testing import CliRunner
from blenderforge.cli import cli


def test_cli_doctor(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(tmp_path / "nonexistent.yaml"), "doctor"])
    assert result.exit_code == 0
    assert "BlenderForge Diagnostic Report" in result.output


def test_cli_doctor_json(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "doctor"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "operating_mode" in data
    assert "blender" in data
    assert data["blender"]["available"] is True


def test_cli_audit_show(tmp_path: Path):
    runner = CliRunner()
    # First invoke doctor to write an audit entry
    runner.invoke(cli, ["doctor"])
    # Now inspect audit log
    result = runner.invoke(cli, ["audit", "show"])
    assert result.exit_code == 0
    assert "BlenderForge Audit Log" in result.output
