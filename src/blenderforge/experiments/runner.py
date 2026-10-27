"""Repeatable experiment runner executing candidates in isolated disposable workspaces."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from blenderforge.config import BlenderForgeConfig, OperatingMode
from blenderforge.execution.sandbox import SandboxManager, SecurityError, redact_secrets
from blenderforge.experiments.comparator import WorkflowComparator
from blenderforge.experiments.models import (
    CleanupPolicy,
    ExperimentManifest,
    ExperimentReport,
    StrategyEvaluationResult,
)
from blenderforge.storage.db import DatabaseManager


WRAPPER_TEMPLATE = """
import bpy
import bmesh
import json
import sys
import time

# Initialize empty scene
bpy.ops.wm.read_factory_settings(use_empty=True)

metrics = {{}}
status = "success"
error_msg = ""
t0 = time.perf_counter()

try:
    # Execute strategy script
{strategy_code}

except Exception as e:
    status = "failed"
    error_msg = str(e)

t1 = time.perf_counter()
metrics["exec_time_sec"] = t1 - t0

# Collect scene and evaluated mesh metrics
metrics["objects_count"] = len(bpy.data.objects)
total_verts = 0
total_faces = 0
total_edges = 0
non_manifold_count = 0

try:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            eval_obj = obj.evaluated_get(depsgraph)
            eval_mesh = None
            try:
                eval_mesh = eval_obj.to_mesh()
                total_verts += len(eval_mesh.vertices)
                total_edges += len(eval_mesh.edges)
                total_faces += len(eval_mesh.polygons)
            except Exception:
                if obj.data:
                    total_verts += len(obj.data.vertices)
                    total_edges += len(obj.data.edges)
                    total_faces += len(obj.data.polygons)
            finally:
                if eval_mesh:
                    eval_obj.to_mesh_clear()
except Exception:
    pass

metrics["vertices"] = total_verts
metrics["edges"] = total_edges
metrics["faces"] = total_faces
metrics["non_manifold_edges"] = non_manifold_count

output_data = {{
    "status": status,
    "error": error_msg,
    "metrics": metrics
}}

with open(r"{metrics_file}", "w", encoding="utf-8") as f:
    json.dump(output_data, f, indent=2)

if status != "success":
    sys.exit(1)
"""


class ExperimentRunner:
    """Manages the isolated execution and evaluation of candidate workflows."""

    def __init__(self, config: BlenderForgeConfig, db: DatabaseManager):
        self.config = config
        self.db = db
        self.sandbox = SandboxManager(config)

    def run_experiment(self, manifest: ExperimentManifest) -> ExperimentReport:
        """Run all strategies in manifest within isolated workspaces and compare results."""
        blender_exe = self.config.resolve_blender_executable()
        if not blender_exe:
            raise FileNotFoundError("Blender executable not available.")

        # Block state-changing experiments if in INSPECT mode
        if self.config.operating_mode == OperatingMode.INSPECT:
            raise SecurityError(
                f"Experiments require at least '{OperatingMode.EXPERIMENT.value}' mode; "
                f"current mode is '{self.config.operating_mode.value}'."
            )

        workspace = self.sandbox.create_disposable_workspace(manifest.id)
        results: List[StrategyEvaluationResult] = []

        try:
            for strategy in manifest.strategies:
                res = self._execute_strategy(blender_exe, workspace, manifest, strategy)
                results.append(res)
        finally:
            if manifest.cleanup_policy == CleanupPolicy.ALWAYS:
                self.sandbox.cleanup_workspace(workspace)
            elif manifest.cleanup_policy == CleanupPolicy.ON_SUCCESS:
                if all(r.success for r in results):
                    self.sandbox.cleanup_workspace(workspace)

        pareto = WorkflowComparator.identify_pareto_frontier(results)
        summary = WorkflowComparator.generate_comparison_summary(results)

        report = ExperimentReport(
            manifest_id=manifest.id,
            objective=manifest.objective,
            blender_version=str(blender_exe),
            results=results,
            pareto_optimal_strategies=pareto,
            comparison_summary=summary,
        )

        self._persist_experiment(manifest, report)
        return report

    def _execute_strategy(
        self,
        blender_exe: Path,
        workspace: Path,
        manifest: ExperimentManifest,
        strategy: Any
    ) -> StrategyEvaluationResult:
        """Execute a single strategy script inside a fresh Blender process."""
        strategy_slug = strategy.name.replace(" ", "_").lower()
        script_file = workspace / f"run_{strategy_slug}.py"
        metrics_file = workspace / f"metrics_{strategy_slug}.json"

        # Compute SHA256 of candidate script
        script_hash = hashlib.sha256(strategy.script_content.encode("utf-8")).hexdigest()

        # Format indented script code inside template
        indented_code = "\n".join("    " + line for line in strategy.script_content.splitlines())
        wrapper_code = WRAPPER_TEMPLATE.format(
            strategy_code=indented_code,
            metrics_file=str(metrics_file)
        )
        script_file.write_text(wrapper_code, encoding="utf-8")

        start_time = time.perf_counter()
        cmd = [
            str(blender_exe),
            "--background",
            "--factory-startup",
            "--python",
            str(script_file)
        ]

        exit_code = 0
        stdout_txt = ""
        stderr_txt = ""
        failure_class = None

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=manifest.timeout_sec,
                check=False
            )
            exit_code = proc.returncode
            stdout_txt = redact_secrets(proc.stdout)
            stderr_txt = redact_secrets(proc.stderr)
            if exit_code != 0:
                failure_class = "BlenderExecutionError"
        except subprocess.TimeoutExpired:
            exit_code = -1
            failure_class = "TimeoutExpired"
            stderr_txt = f"Execution exceeded timeout limit ({manifest.timeout_sec}s)."
        except Exception as e:
            exit_code = -2
            failure_class = type(e).__name__
            stderr_txt = str(e)

        duration = time.perf_counter() - start_time

        # Read metrics JSON
        metrics = {}
        if metrics_file.exists():
            try:
                metrics_data = json.loads(metrics_file.read_text(encoding="utf-8"))
                metrics = metrics_data.get("metrics", {})
                if metrics_data.get("status") != "success":
                    failure_class = failure_class or "ScriptException"
            except Exception:
                pass

        success = (exit_code == 0) and (failure_class is None)

        return StrategyEvaluationResult(
            strategy_name=strategy.name,
            success=success,
            duration_sec=duration,
            exit_code=exit_code,
            script_hash=script_hash,
            stdout_snippet=stdout_txt[-1000:],
            stderr_snippet=stderr_txt[-1000:],
            metrics=metrics,
            failure_classification=failure_class,
        )

    def _persist_experiment(self, manifest: ExperimentManifest, report: ExperimentReport) -> None:
        """Store experiment run metadata in SQLite."""
        now = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            for r in report.results:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO experiments (
                        id, objective, blender_version, status, duration_sec,
                        metrics_json, exit_code, stdout_snippet, stderr_snippet, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{manifest.id}:{r.strategy_name}:{int(time.time())}",
                        manifest.objective,
                        report.blender_version,
                        "success" if r.success else "failed",
                        r.duration_sec,
                        json.dumps(r.metrics),
                        r.exit_code,
                        r.stdout_snippet[:500],
                        r.stderr_snippet[:500],
                        now
                    )
                )
            conn.commit()
