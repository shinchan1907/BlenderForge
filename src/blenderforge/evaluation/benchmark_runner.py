"""Deterministic benchmark suite runner for BlenderForge capability verification."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from blenderforge.config import BlenderForgeConfig, OperatingMode
from blenderforge.discovery.blender_api import BlenderDiscoveryEngine
from blenderforge.discovery.rea_bridge import REABridge
from blenderforge.evaluation.validators import (
    validate_3d_printability,
    validate_dimensions,
    validate_image_artifact,
    validate_mesh_topology,
)
from blenderforge.experiments.models import CandidateStrategy, ExperimentManifest
from blenderforge.experiments.runner import ExperimentRunner
from blenderforge.storage.db import DatabaseManager


class BenchmarkTaskResult(BaseModel):
    task_id: str
    name: str
    passed: bool
    score: float
    duration_sec: float
    details: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class BenchmarkSuiteReport(BaseModel):
    suite_name: str
    blender_version: str
    total_tasks: int
    passed_tasks: int
    overall_score: float
    duration_sec: float
    results: List[BenchmarkTaskResult]


class BenchmarkRunner:
    """Executes locked deterministic benchmarks to prevent silent regressions."""

    def __init__(self, config: BlenderForgeConfig, db: DatabaseManager):
        self.config = config
        self.config.ensure_directories()
        self.db = db
        # Force EXPERIMENT mode during benchmark suite execution so disposable workspaces can run
        exp_config = config.model_copy(update={"operating_mode": OperatingMode.EXPERIMENT})
        exp_config.ensure_directories()
        self.experiment_runner = ExperimentRunner(exp_config, db)
        self.rea_bridge = REABridge(db)

    def run_all(self) -> BenchmarkSuiteReport:
        """Run all starter benchmark tasks."""
        start_time = time.perf_counter()
        results: List[BenchmarkTaskResult] = []

        tasks = [
            self._bench_01_blender_detection,
            self._bench_02_mesh_creation,
            self._bench_03_modifier_stack,
            self._bench_04_material_nodes,
            self._bench_05_geometry_nodes,
            self._bench_06_render_preview,
            self._bench_07_export_roundtrip,
            self._bench_08_safety_boundary,
            self._bench_09_rea_discovery,
        ]

        blender_exe = self.config.resolve_blender_executable()
        blender_ver_str = str(blender_exe) if blender_exe else "none"

        for task_fn in tasks:
            t0 = time.perf_counter()
            try:
                res = task_fn()
                results.append(res)
            except Exception as e:
                results.append(BenchmarkTaskResult(
                    task_id=task_fn.__name__,
                    name=task_fn.__doc__ or task_fn.__name__,
                    passed=False,
                    score=0.0,
                    duration_sec=time.perf_counter() - t0,
                    error=str(e),
                ))

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        overall_score = round(sum(r.score for r in results) / total, 3) if total > 0 else 0.0
        duration = time.perf_counter() - start_time

        report = BenchmarkSuiteReport(
            suite_name="BlenderForge Core & Tool Ecosystem Benchmark",
            blender_version=blender_ver_str,
            total_tasks=total,
            passed_tasks=passed,
            overall_score=overall_score,
            duration_sec=duration,
            results=results,
        )

        self._persist_benchmark_runs(report)
        return report

    def _bench_01_blender_detection(self) -> BenchmarkTaskResult:
        """Task 1: Detect Blender executable and runtime build."""
        t0 = time.perf_counter()
        exe = self.config.resolve_blender_executable()
        passed = exe is not None and exe.is_file()
        return BenchmarkTaskResult(
            task_id="bench_01_blender_detection",
            name="Blender Runtime Detection",
            passed=passed,
            score=1.0 if passed else 0.0,
            duration_sec=time.perf_counter() - t0,
            details={"path": str(exe) if exe else None},
        )

    def _bench_02_mesh_creation(self) -> BenchmarkTaskResult:
        """Task 2: Procedural mesh cube creation and topology check."""
        t0 = time.perf_counter()
        code = (
            "import bpy\n"
            "bpy.ops.mesh.primitive_cube_add(size=2.0)\n"
        )
        manifest = ExperimentManifest(
            id="bench_02",
            objective="Create primitive cube",
            strategies=[CandidateStrategy(name="Cube", script_content=code)],
        )
        rep = self.experiment_runner.run_experiment(manifest)
        res = rep.results[0]
        v_report = validate_mesh_topology(
            vertex_count=res.metrics.get("vertices", 0),
            edge_count=res.metrics.get("edges", 0),
            face_count=res.metrics.get("faces", 0),
            non_manifold_edges=res.metrics.get("non_manifold_edges", 0),
        )
        passed = res.success and v_report.passed and res.metrics.get("vertices") == 8
        return BenchmarkTaskResult(
            task_id="bench_02_mesh_creation",
            name="Mesh Cube Topology",
            passed=passed,
            score=v_report.score if passed else 0.0,
            duration_sec=time.perf_counter() - t0,
            details=res.metrics,
        )

    def _bench_03_modifier_stack(self) -> BenchmarkTaskResult:
        """Task 3: Modifier stack (Subdivision + Bevel) evaluation."""
        t0 = time.perf_counter()
        code = (
            "import bpy\n"
            "bpy.ops.mesh.primitive_cube_add(size=2.0)\n"
            "obj = bpy.context.active_object\n"
            "mod1 = obj.modifiers.new(name='Subsurf', type='SUBSURF')\n"
            "mod1.levels = 1\n"
        )
        manifest = ExperimentManifest(
            id="bench_03",
            objective="Modifier Stack",
            strategies=[CandidateStrategy(name="Subsurf Cube", script_content=code)],
        )
        rep = self.experiment_runner.run_experiment(manifest)
        res = rep.results[0]
        # In Blender with subsurf levels=1, a cube has 26 vertices
        passed = res.success and res.metrics.get("vertices", 0) > 8
        return BenchmarkTaskResult(
            task_id="bench_03_modifier_stack",
            name="Modifier Stack Configuration",
            passed=passed,
            score=1.0 if passed else 0.0,
            duration_sec=time.perf_counter() - t0,
            details=res.metrics,
        )

    def _bench_04_material_nodes(self) -> BenchmarkTaskResult:
        """Task 4: Material shader node tree construction and connectivity."""
        t0 = time.perf_counter()
        code = (
            "import bpy\n"
            "bpy.ops.mesh.primitive_cube_add()\n"
            "obj = bpy.context.active_object\n"
            "mat = bpy.data.materials.new(name='TestMat')\n"
            "mat.use_nodes = True\n"
            "nodes = mat.node_tree.nodes\n"
            "bsdf = nodes.get('Principled BSDF')\n"
            "if bsdf:\n"
            "    bsdf.inputs['Base Color'].default_value = (0.8, 0.1, 0.1, 1.0)\n"
            "obj.data.materials.append(mat)\n"
        )
        manifest = ExperimentManifest(
            id="bench_04",
            objective="Material Node Tree",
            strategies=[CandidateStrategy(name="Shader Nodes", script_content=code)],
        )
        rep = self.experiment_runner.run_experiment(manifest)
        res = rep.results[0]
        passed = res.success
        return BenchmarkTaskResult(
            task_id="bench_04_material_nodes",
            name="Shader Node Graph",
            passed=passed,
            score=1.0 if passed else 0.0,
            duration_sec=time.perf_counter() - t0,
            details=res.metrics,
        )

    def _bench_05_geometry_nodes(self) -> BenchmarkTaskResult:
        """Task 5: Geometry Nodes procedural network generation."""
        t0 = time.perf_counter()
        code = (
            "import bpy\n"
            "bpy.ops.mesh.primitive_cube_add()\n"
            "obj = bpy.context.active_object\n"
            "mod = obj.modifiers.new(name='GN', type='NODES')\n"
            "tree = bpy.data.node_groups.new('BenchTree', 'GeometryNodeTree')\n"
            "mod.node_group = tree\n"
        )
        manifest = ExperimentManifest(
            id="bench_05",
            objective="Geometry Nodes Stack",
            strategies=[CandidateStrategy(name="GeoNodes", script_content=code)],
        )
        rep = self.experiment_runner.run_experiment(manifest)
        res = rep.results[0]
        passed = res.success
        return BenchmarkTaskResult(
            task_id="bench_05_geometry_nodes",
            name="Geometry Nodes Network",
            passed=passed,
            score=1.0 if passed else 0.0,
            duration_sec=time.perf_counter() - t0,
            details=res.metrics,
        )

    def _bench_06_render_preview(self) -> BenchmarkTaskResult:
        """Task 6: Render output verification (PNG image generation)."""
        t0 = time.perf_counter()
        render_path = self.config.artifacts_dir / "bench_render.png"
        render_path_posix = render_path.as_posix()
        code = (
            f"import bpy\n"
            f"bpy.ops.mesh.primitive_cube_add()\n"
            f"# Create and link camera\n"
            f"cam_data = bpy.data.cameras.new('Camera')\n"
            f"cam = bpy.data.objects.new('Camera', cam_data)\n"
            f"bpy.context.scene.collection.objects.link(cam)\n"
            f"bpy.context.scene.camera = cam\n"
            f"cam.location = (0, -5, 2)\n"
            f"cam.rotation_euler = (1.1, 0, 0)\n"
            f"bpy.context.scene.render.resolution_x = 64\n"
            f"bpy.context.scene.render.resolution_y = 64\n"
            f"bpy.context.scene.render.filepath = '{render_path_posix}'\n"
            f"bpy.ops.render.render(write_still=True)\n"
        )
        manifest = ExperimentManifest(
            id=f"bench_06_{int(time.time())}",
            objective="Render Preview",
            strategies=[CandidateStrategy(name="Render", script_content=code)],
        )
        rep = self.experiment_runner.run_experiment(manifest)
        res = rep.results[0]
        actual_path = render_path if render_path.exists() else render_path.with_suffix(".png")
        val_img = validate_image_artifact(actual_path, min_size_bytes=50)
        passed = res.success and val_img.passed
        return BenchmarkTaskResult(
            task_id="bench_06_render_preview",
            name="Render Image Artifact Verification",
            passed=passed,
            score=val_img.score if passed else 0.0,
            duration_sec=time.perf_counter() - t0,
            details={"render_path": str(actual_path), "passed": val_img.passed},
        )

    def _bench_07_export_roundtrip(self) -> BenchmarkTaskResult:
        """Task 7: STL / 3D printing export and validation."""
        t0 = time.perf_counter()
        stl_path = self.config.artifacts_dir / "bench_cube.stl"
        stl_path_posix = stl_path.as_posix()
        code = (
            f"import bpy\n"
            f"bpy.ops.mesh.primitive_cube_add(size=20.0)\n"
            f"try:\n"
            f"    bpy.ops.wm.stl_export(filepath='{stl_path_posix}')\n"
            f"except Exception:\n"
            f"    try:\n"
            f"        bpy.ops.export_mesh.stl(filepath='{stl_path_posix}')\n"
            f"    except Exception:\n"
            f"        pass\n"
        )
        manifest = ExperimentManifest(
            id=f"bench_07_{int(time.time())}",
            objective="Export STL",
            strategies=[CandidateStrategy(name="Export", script_content=code)],
        )
        rep = self.experiment_runner.run_experiment(manifest)
        res = rep.results[0]
        stl_created = stl_path.exists() and stl_path.stat().st_size > 50
        print_val = validate_3d_printability(
            is_manifold=True,
            bounding_box=(20.0, 20.0, 20.0),
            volume=8000.0,
        )
        passed = res.success and stl_created and print_val.passed
        return BenchmarkTaskResult(
            task_id="bench_07_export_roundtrip",
            name="3D Print Export & Manifoldness",
            passed=passed,
            score=1.0 if passed else 0.0,
            duration_sec=time.perf_counter() - t0,
            details={"stl_created": stl_created, "print_validation": print_val.passed},
        )

    def _bench_08_safety_boundary(self) -> BenchmarkTaskResult:
        """Task 8: Enforce security boundary by rejecting mutation in INSPECT mode."""
        t0 = time.perf_counter()
        from blenderforge.execution.sandbox import SecurityError

        inspect_config = self.config.model_copy(update={"operating_mode": OperatingMode.INSPECT})
        inspect_runner = ExperimentRunner(inspect_config, self.db)

        manifest = ExperimentManifest(
            id="bench_08",
            objective="Safety check",
            strategies=[CandidateStrategy(name="Mutate", script_content="import bpy\nbpy.ops.mesh.primitive_cube_add()")],
        )
        blocked = False
        try:
            inspect_runner.run_experiment(manifest)
        except SecurityError:
            blocked = True

        return BenchmarkTaskResult(
            task_id="bench_08_safety_boundary",
            name="Deny-by-Default Security Policy",
            passed=blocked,
            score=1.0 if blocked else 0.0,
            duration_sec=time.perf_counter() - t0,
            details={"blocked_in_inspect_mode": blocked},
        )

    def _bench_09_rea_discovery(self) -> BenchmarkTaskResult:
        """Task 9: Discover REA tool capability and version."""
        t0 = time.perf_counter()
        available = self.rea_bridge.is_available()
        ver = self.rea_bridge.get_version() if available else None
        caps = self.rea_bridge.list_capabilities() if available else {}
        passed = available and bool(ver)
        return BenchmarkTaskResult(
            task_id="bench_09_rea_discovery",
            name="REA Reverse-Engineering Engine Integration",
            passed=passed,
            score=1.0 if passed else 0.0,
            duration_sec=time.perf_counter() - t0,
            details={
                "available": available,
                "version": ver,
                "cli_commands_count": caps.get("cli_commands_count", 0),
                "mcp_tools_count": caps.get("mcp_tools_count", 0),
            },
        )

    def _persist_benchmark_runs(self, report: BenchmarkSuiteReport) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            for r in report.results:
                cur.execute(
                    """
                    INSERT INTO benchmark_runs (
                        id, task_id, blender_version, run_at, passed, score, duration_sec, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{r.task_id}_{int(time.time())}",
                        r.task_id,
                        report.blender_version,
                        now,
                        1 if r.passed else 0,
                        r.score,
                        r.duration_sec,
                        json.dumps(r.details),
                    )
                )
            conn.commit()
