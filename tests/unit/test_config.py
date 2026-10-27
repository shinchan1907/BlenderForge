"""Tests for BlenderForge configuration and environment discovery."""

from pathlib import Path
from blenderforge.config import OperatingMode, BlenderForgeConfig, load_config


def test_default_config(tmp_path: Path):
    cfg = BlenderForgeConfig(base_dir=tmp_path, data_dir=tmp_path / ".blenderforge")
    assert cfg.operating_mode == OperatingMode.INSPECT
    assert cfg.default_timeout_sec == 60.0
    cfg.ensure_directories()
    assert (tmp_path / ".blenderforge").is_dir()
    assert (tmp_path / ".blenderforge" / "workspaces").is_dir()
    assert (tmp_path / ".blenderforge" / "artifacts").is_dir()


def test_load_config_with_override(tmp_path: Path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("default_timeout_sec: 120.0\noperating_mode: experiment\n", encoding="utf-8")
    cfg = load_config(config_file=config_file)
    assert cfg.default_timeout_sec == 120.0
    assert cfg.operating_mode == OperatingMode.EXPERIMENT


def test_resolve_blender_executable():
    cfg = BlenderForgeConfig()
    exe = cfg.resolve_blender_executable()
    # If Blender is installed on this machine, exe should exist
    assert exe is not None
    assert exe.is_file()
    assert "blender" in exe.name.lower()
