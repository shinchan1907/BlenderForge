"""SQLite storage layer with FTS5 search, migrations, and audit logging."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    mode TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    actor TEXT NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS api_inventories (
    id TEXT PRIMARY KEY,
    blender_version TEXT NOT NULL,
    blender_build TEXT,
    python_version TEXT,
    platform TEXT,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    raw_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capability_nodes (
    id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    identifier TEXT NOT NULL,
    blender_version TEXT,
    description TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capability_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_id) REFERENCES capability_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY(target_id) REFERENCES capability_nodes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    transport_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mcp_tools (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    input_schema_json TEXT NOT NULL,
    is_mutation INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(server_id) REFERENCES mcp_servers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    blender_version TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_sec REAL NOT NULL,
    metrics_json TEXT,
    exit_code INTEGER NOT NULL,
    stdout_snippet TEXT,
    stderr_snippet TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    blender_version TEXT NOT NULL,
    run_at TEXT NOT NULL,
    passed INTEGER NOT NULL,
    score REAL NOT NULL,
    duration_sec REAL NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    status TEXT NOT NULL,
    version TEXT NOT NULL,
    supported_versions_json TEXT NOT NULL,
    preconditions_json TEXT NOT NULL,
    strategy_json TEXT NOT NULL,
    code TEXT NOT NULL,
    expected_outputs_json TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    evidence_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Standalone FTS5 table for flexible text search
CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
    id,
    name,
    domain,
    strategy,
    code
);

CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills BEGIN
    INSERT INTO skills_fts(id, name, domain, strategy, code)
    VALUES (new.id, new.name, new.domain, new.strategy_json, new.code);
END;

CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills BEGIN
    DELETE FROM skills_fts WHERE id = old.id;
END;

CREATE TRIGGER IF NOT EXISTS skills_au AFTER UPDATE ON skills BEGIN
    DELETE FROM skills_fts WHERE id = old.id;
    INSERT INTO skills_fts(id, name, domain, strategy, code)
    VALUES (new.id, new.name, new.domain, new.strategy_json, new.code);
END;
"""


class DatabaseManager:
    """Manages SQLite database connections, schema migrations, and queries."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_db(self) -> None:
        """Run schema migrations."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(SCHEMA_V1)
            cursor.execute("SELECT version FROM schema_migrations WHERE version = 1")
            if not cursor.fetchone():
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)",
                    (now,)
                )
            conn.commit()

    def log_audit(
        self,
        mode: str,
        action: str,
        actor: str,
        status: str,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record an immutable audit entry."""
        now = datetime.now(timezone.utc).isoformat()
        details_json = json.dumps(details or {}, ensure_ascii=False)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_events (timestamp, mode, action, target, actor, status, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now, mode, action, target, actor, status, details_json),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_audit_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent audit events."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, timestamp, mode, action, target, actor, status, details_json
                FROM audit_events ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "mode": row["mode"],
                    "action": row["action"],
                    "target": row["target"],
                    "actor": row["actor"],
                    "status": row["status"],
                    "details": json.loads(row["details_json"] or "{}"),
                }
                for row in rows
            ]
