"""Tests for SQLite database storage and audit logging."""

import json
from pathlib import Path
from blenderforge.storage.db import DatabaseManager


def test_database_init(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db = DatabaseManager(db_file)
    assert db_file.exists()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_migrations")
        row = cursor.fetchone()
        assert row is not None
        assert row["version"] == 1


def test_audit_logging(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db = DatabaseManager(db_file)

    row_id = db.log_audit(
        mode="inspect",
        action="test_action",
        actor="pytest",
        status="success",
        target="scene_01",
        details={"key": "value"}
    )
    assert row_id > 0

    events = db.get_audit_events(limit=10)
    assert len(events) == 1
    assert events[0]["action"] == "test_action"
    assert events[0]["details"] == {"key": "value"}
    assert events[0]["actor"] == "pytest"


def test_fts5_skills_search(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db = DatabaseManager(db_file)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO skills (
                id, name, domain, status, version, supported_versions_json,
                preconditions_json, strategy_json, code, expected_outputs_json,
                code_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "skill_cube_01",
                "Procedural Bevel Cube",
                "modeling",
                "validated",
                "1.0.0",
                json.dumps([">=4.0"]),
                json.dumps([]),
                "Create a mesh cube with non-destructive bevel modifier stack",
                "bpy.ops.mesh.primitive_cube_add()",
                json.dumps(["cube_obj"]),
                "hash123",
                "2026-10-27T00:00:00Z",
                "2026-10-27T00:00:00Z"
            )
        )
        conn.commit()

        # Query via FTS5
        cursor.execute("SELECT id, name FROM skills_fts WHERE skills_fts MATCH 'bevel'")
        row = cursor.fetchone()
        assert row is not None
        assert row["id"] == "skill_cube_01"
        assert row["name"] == "Procedural Bevel Cube"
