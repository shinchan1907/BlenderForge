"""Blender runtime API introspection orchestrator and inventory persistence."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from blenderforge.config import BlenderForgeConfig
from blenderforge.discovery.graph import CapabilityGraph, CapabilityNode, NodeType
from blenderforge.storage.db import DatabaseManager


class BlenderDiscoveryEngine:
    """Orchestrates runtime discovery via background Blender process."""

    def __init__(self, config: BlenderForgeConfig, db: DatabaseManager):
        self.config = config
        self.db = db
        self.graph = CapabilityGraph(db)

    def run_introspection(self, script_path: Optional[Path] = None) -> Dict[str, Any]:
        """Execute non-destructive introspection inside Blender and store results."""
        blender_exe = self.config.resolve_blender_executable()
        if not blender_exe:
            raise FileNotFoundError("Blender executable could not be resolved.")

        if not script_path:
            candidate1 = self.config.base_dir / "blender_scripts" / "introspect.py"
            # Fallback to package repository root
            candidate2 = Path(__file__).resolve().parents[3] / "blender_scripts" / "introspect.py"
            if candidate1.exists():
                script_path = candidate1
            elif candidate2.exists():
                script_path = candidate2
            else:
                script_path = candidate1

        if not script_path.exists():
            raise FileNotFoundError(f"Introspection script not found at {script_path}")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            cmd = [
                str(blender_exe),
                "--background",
                "--factory-startup",
                "--python",
                str(script_path),
                "--",
                "--output-json",
                str(tmp_path),
            ]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.default_timeout_sec,
                check=False
            )
            if res.returncode != 0:
                raise RuntimeError(f"Blender introspection process failed (exit {res.returncode}): {res.stderr}")

            if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                raise RuntimeError("Introspection did not generate output file.")

            content = tmp_path.read_text(encoding="utf-8")
            data: Dict[str, Any] = json.loads(content)
            self._persist_inventory(data)
            return data
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def _persist_inventory(self, data: Dict[str, Any]) -> str:
        """Persist inventory to database and populate capability graph nodes."""
        b_info = data.get("blender", {})
        version_str = b_info.get("version_string", "unknown")
        build_hash = b_info.get("build_hash", "unknown")
        py_version = b_info.get("python_version", "unknown")
        platform_str = b_info.get("build_platform", "unknown")
        raw_hash = data.get("sha256", "hash")

        inv_id = f"blender-{version_str}-{build_hash[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        # Save to api_inventories
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO api_inventories (id, blender_version, blender_build, python_version, platform, created_at, metadata_json, raw_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    metadata_json = excluded.metadata_json,
                    raw_hash = excluded.raw_hash
                """,
                (
                    inv_id,
                    version_str,
                    build_hash,
                    py_version,
                    platform_str,
                    now,
                    json.dumps(data, ensure_ascii=False),
                    raw_hash
                )
            )
            conn.commit()

        # Batch ingest nodes into CapabilityGraph
        nodes_to_insert = []
        # 1. Modifiers
        for m in data.get("modifiers", []):
            nodes_to_insert.append(CapabilityNode(
                id=f"modifier:{m['identifier']}",
                node_type=NodeType.MODIFIER,
                name=m["name"],
                identifier=m["identifier"],
                blender_version=version_str,
                description=m.get("description"),
            ))

        # 2. Geometry Nodes
        for gn in data.get("nodes", {}).get("geometry_nodes", []):
            nodes_to_insert.append(CapabilityNode(
                id=f"node:{gn}",
                node_type=NodeType.NODE_TYPE,
                name=gn,
                identifier=gn,
                blender_version=version_str,
                description="Geometry Nodes functional node",
            ))

        # 3. Key operators
        for category, ops in data.get("operators", {}).items():
            for op_name, op_details in ops.items():
                nodes_to_insert.append(CapabilityNode(
                    id=op_details["identifier"],
                    node_type=NodeType.API_OPERATOR,
                    name=op_name,
                    identifier=op_details["identifier"],
                    blender_version=version_str,
                    payload={"properties": op_details.get("properties", {})},
                ))

        self.graph.add_nodes_batch(nodes_to_insert)

        return inv_id
