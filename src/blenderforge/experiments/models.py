"""Data models for reproducible Blender experiments and candidate workflows."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CleanupPolicy(str, Enum):
    ALWAYS = "always"
    ON_SUCCESS = "on_success"
    NEVER = "never"


class CandidateStrategy(BaseModel):
    """A distinct approach or workflow to evaluate."""
    name: str = Field(..., description="Unique strategy name (e.g. 'direct_bmesh', 'modifier_stack').")
    description: Optional[str] = None
    script_content: str = Field(..., description="Python script executed inside Blender.")


class ExperimentManifest(BaseModel):
    """Declaration of an isolated, repeatable experiment."""
    id: str
    objective: str
    strategies: List[CandidateStrategy]
    input_fixture: Optional[str] = None
    timeout_sec: float = 60.0
    cleanup_policy: CleanupPolicy = CleanupPolicy.ALWAYS
    capture_preview: bool = False


class StrategyEvaluationResult(BaseModel):
    """Metrics and verification outcome for one strategy."""
    strategy_name: str
    success: bool
    duration_sec: float
    exit_code: int
    script_hash: str
    stdout_snippet: str = ""
    stderr_snippet: str = ""
    metrics: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[str] = Field(default_factory=list)
    failure_classification: Optional[str] = None


class ExperimentReport(BaseModel):
    """Complete multi-candidate experiment report."""
    manifest_id: str
    objective: str
    blender_version: str
    results: List[StrategyEvaluationResult]
    pareto_optimal_strategies: List[str] = Field(default_factory=list)
    comparison_summary: Dict[str, Any] = Field(default_factory=dict)
