"""Versioned skill definitions and lifecycle status."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SkillStatus(str, Enum):
    PROPOSED = "proposed"
    EXPERIMENTAL = "experimental"
    VALIDATED = "validated"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class SkillDefinition(BaseModel):
    """Complete specification of a reusable, verified Blender capability."""
    id: str = Field(..., description="Unique skill ID (e.g. 'modeling.bevel_cube.v1').")
    name: str = Field(..., description="Human-readable title.")
    domain: str = Field(..., description="Domain (e.g. modeling, shading, animation, 3d_printing).")
    status: SkillStatus = Field(default=SkillStatus.EXPERIMENTAL)
    version: str = Field(default="1.0.0")
    supported_versions: List[str] = Field(default_factory=lambda: [">=4.0"])
    preconditions: List[str] = Field(default_factory=list)
    strategy: str = Field(..., description="Detailed markdown strategy and explanation.")
    code: str = Field(..., description="Verified executable Python snippet.")
    expected_outputs: List[str] = Field(default_factory=list)
    code_hash: str = Field(...)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
