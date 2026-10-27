"""Integration tests executing against the installed Blender build."""

import pytest
from blenderforge.config import BlenderForgeConfig
from blenderforge.discovery.blender_api import BlenderDiscoveryEngine
from blenderforge.storage.db import DatabaseManager


def test_blender_runtime_introspection(tmp_path):
    cfg = BlenderForgeConfig(base_dir=tmp_path, data_dir=tmp_path / ".blenderforge")
    exe = cfg.resolve_blender_executable()
    if not exe:
        pytest.skip("Blender executable not available in this environment.")

    db = DatabaseManager(cfg.db_path)
    engine = BlenderDiscoveryEngine(cfg, db)

    # Run real introspection against installed Blender
    data = engine.run_introspection()

    assert "blender" in data
    assert "version_string" in data["blender"]
    assert "operators" in data
    assert len(data["operators"]) > 0
    assert "modifiers" in data
    assert len(data["modifiers"]) > 0
    assert "nodes" in data
    assert len(data["nodes"]["geometry_nodes"]) > 0

    # Verify database persistence
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM api_inventories")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM capability_nodes")
        assert cur.fetchone()[0] > 100
