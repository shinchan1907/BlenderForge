"""Configuration management and environment discovery for BlenderForge."""

from __future__ import annotations

import os
import shutil
import sys
from enum import Enum
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class OperatingMode(str, Enum):
    INSPECT = "inspect"          # Read-only discovery and inventory (default)
    EXPERIMENT = "experiment"    # Isolated tests on disposable files
    DEVELOP = "develop"          # Controlled changes in designated project copy
    PRODUCTION = "production"    # User-authorized edits and exports
    PRIVILEGED = "privileged"    # Destructive actions, package installs, network access


class BlenderForgeConfig(BaseModel):
    """Core configuration for BlenderForge."""
    blender_path: Optional[str] = Field(
        default=None,
        description="Path to Blender executable. If None, auto-discovery is used."
    )
    operating_mode: OperatingMode = Field(
        default=OperatingMode.INSPECT,
        description="Current operational security mode."
    )
    base_dir: Path = Field(
        default_factory=lambda: Path(os.getcwd()),
        description="Root working directory of the project."
    )
    data_dir: Path = Field(
        default_factory=lambda: Path(os.getcwd()) / ".blenderforge",
        description="Local data and storage directory."
    )
    workspaces_dir: Optional[Path] = Field(
        default=None,
        description="Isolated disposable workspaces directory."
    )
    artifacts_dir: Optional[Path] = Field(
        default=None,
        description="Verified output artifacts directory."
    )
    db_path: Optional[Path] = Field(
        default=None,
        description="Path to SQLite metadata database."
    )
    allowed_output_dirs: List[Path] = Field(
        default_factory=list,
        description="Explicit allowlisted output directories."
    )
    default_timeout_sec: float = Field(
        default=60.0,
        description="Subprocess and experiment timeout in seconds."
    )

    @model_validator(mode="after")
    def populate_dependent_paths(self) -> "BlenderForgeConfig":
        if self.workspaces_dir is None:
            self.workspaces_dir = self.data_dir / "workspaces"
        if self.artifacts_dir is None:
            self.artifacts_dir = self.data_dir / "artifacts"
        if self.db_path is None:
            self.db_path = self.data_dir / "blenderforge.db"
        if not self.allowed_output_dirs:
            self.allowed_output_dirs = [self.artifacts_dir, self.workspaces_dir]
        return self

    def ensure_directories(self) -> None:
        """Ensure necessary storage directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.workspaces_dir:
            self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        if self.artifacts_dir:
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def resolve_blender_executable(self) -> Optional[Path]:
        """Auto-detect or resolve Blender executable across platforms."""
        if self.blender_path:
            p = Path(self.blender_path)
            if p.is_file():
                return p.resolve()

        # Check environment variable
        env_path = os.environ.get("BLENDER_PATH")
        if env_path:
            p = Path(env_path)
            if p.is_file():
                return p.resolve()

        # Check system PATH
        which_path = shutil.which("blender")
        if which_path:
            return Path(which_path).resolve()

        # Check standard Windows paths
        if sys.platform == "win32":
            common_roots = [
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation",
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Blender Foundation",
                Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")) / "Programs" / "Blender Foundation",
            ]
            for root in common_roots:
                if root.exists():
                    dirs = sorted(root.glob("Blender*"), reverse=True)
                    for d in dirs:
                        exe = d / "blender.exe"
                        if exe.is_file():
                            return exe.resolve()

        # Standard macOS paths
        elif sys.platform == "darwin":
            mac_paths = [
                Path("/Applications/Blender.app/Contents/MacOS/Blender"),
                Path.home() / "Applications/Blender.app/Contents/MacOS/Blender",
            ]
            for p in mac_paths:
                if p.is_file():
                    return p.resolve()

        # Standard Linux paths
        else:
            linux_paths = [
                Path("/usr/bin/blender"),
                Path("/usr/local/bin/blender"),
                Path("/snap/bin/blender"),
            ]
            for p in linux_paths:
                if p.is_file():
                    return p.resolve()

        return None


def load_config(config_file: Optional[Path] = None, mode_override: Optional[OperatingMode] = None) -> BlenderForgeConfig:
    """Load configuration from file or default."""
    config_data = {}
    if config_file and config_file.exists():
        import json
        import yaml
        content = config_file.read_text(encoding="utf-8")
        if config_file.suffix in (".yaml", ".yml"):
            config_data = yaml.safe_load(content) or {}
        else:
            config_data = json.loads(content)

    config = BlenderForgeConfig(**config_data)
    if mode_override:
        config.operating_mode = mode_override

    config.ensure_directories()
    return config
