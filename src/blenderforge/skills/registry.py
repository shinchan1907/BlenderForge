"""Skill registry with SQLite storage and FTS5 full-text keyword retrieval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from blenderforge.skills.models import SkillDefinition, SkillStatus
from blenderforge.storage.db import DatabaseManager


class SkillRegistry:
    """Manages skill persistence and semantic retrieval."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def save_skill(self, skill: SkillDefinition) -> None:
        """Insert or update a skill in SQLite and update FTS5 index."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO skills (
                    id, name, domain, status, version, supported_versions_json,
                    preconditions_json, strategy_json, code, expected_outputs_json,
                    code_hash, evidence_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    domain = excluded.domain,
                    status = excluded.status,
                    version = excluded.version,
                    supported_versions_json = excluded.supported_versions_json,
                    preconditions_json = excluded.preconditions_json,
                    strategy_json = excluded.strategy_json,
                    code = excluded.code,
                    expected_outputs_json = excluded.expected_outputs_json,
                    code_hash = excluded.code_hash,
                    evidence_json = excluded.evidence_json,
                    updated_at = excluded.updated_at
                """,
                (
                    skill.id,
                    skill.name,
                    skill.domain,
                    skill.status.value,
                    skill.version,
                    json.dumps(skill.supported_versions),
                    json.dumps(skill.preconditions),
                    skill.strategy,
                    skill.code,
                    json.dumps(skill.expected_outputs),
                    skill.code_hash,
                    json.dumps(skill.evidence),
                    skill.created_at,
                    skill.updated_at,
                )
            )
            conn.commit()

    def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        """Fetch a skill by ID."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_skill(row)

    def list_skills(self, domain: Optional[str] = None, status: Optional[SkillStatus] = None) -> List[SkillDefinition]:
        """List skills with optional filtering."""
        query = "SELECT * FROM skills WHERE 1=1"
        params: List[Any] = []
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY id ASC"

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            return [self._row_to_skill(r) for r in rows]

    def search_skills(self, query: str, limit: int = 10) -> List[SkillDefinition]:
        """Search skills full-text across name, domain, strategy, and code using FTS5."""
        import re
        tokens = [w for w in re.findall(r"[a-zA-Z0-9_]+", query) if len(w) > 2]
        if not tokens:
            return self.list_skills()[:limit]

        fts_query = " OR ".join(tokens)
        fts_sql = """
            SELECT s.* FROM skills s
            JOIN skills_fts f ON s.id = f.id
            WHERE skills_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(fts_sql, (fts_query, limit))
                rows = cur.fetchall()
                if rows:
                    return [self._row_to_skill(r) for r in rows]
            except Exception:
                pass

            # Fallback to simple LIKE search if FTS query fails
            like_sql = "SELECT * FROM skills WHERE name LIKE ? OR strategy_json LIKE ? LIMIT ?"
            cur.execute(like_sql, (f"%{tokens[0]}%", f"%{tokens[0]}%", limit))
            rows = cur.fetchall()
            return [self._row_to_skill(r) for r in rows]

    def _row_to_skill(self, r: Any) -> SkillDefinition:
        return SkillDefinition(
            id=r["id"],
            name=r["name"],
            domain=r["domain"],
            status=SkillStatus(r["status"]),
            version=r["version"],
            supported_versions=json.loads(r["supported_versions_json"]),
            preconditions=json.loads(r["preconditions_json"]),
            strategy=r["strategy_json"],
            code=r["code"],
            expected_outputs=json.loads(r["expected_outputs_json"]),
            code_hash=r["code_hash"],
            evidence=json.loads(r["evidence_json"] or "{}"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
