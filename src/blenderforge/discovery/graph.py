"""Capability graph representing Blender features, MCP tools, and workflows as nodes and edges."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from blenderforge.storage.db import DatabaseManager


class NodeType(str, Enum):
    MCP_TOOL = "mcp_tool"
    API_OPERATOR = "api_operator"
    RNA_TYPE = "rna_type"
    NODE_TYPE = "node_type"
    MODIFIER = "modifier"
    CONSTRAINT = "constraint"
    WORKFLOW = "workflow"
    VALIDATION_RULE = "validation_rule"
    SKILL = "skill"
    BENCHMARK_RESULT = "benchmark_result"


class RelationType(str, Enum):
    REQUIRES_CONTEXT = "requires_context"
    ACCEPTS_INPUT = "accepts_input"
    MODIFIES_DATA = "modifies_data"
    PRODUCES_OUTPUT = "produces_output"
    ALTERNATIVE_TO = "alternative_to"
    VALIDATED_BY = "validated_by"
    SUPPORTED_IN_VERSION = "supported_in_version"
    FAILS_WHEN = "fails_when"
    IMPROVED_BY = "improved_by"


class CapabilityNode(BaseModel):
    id: str
    node_type: NodeType
    name: str
    identifier: str
    blender_version: Optional[str] = None
    description: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CapabilityEdge(BaseModel):
    id: Optional[int] = None
    source_id: str
    target_id: str
    relation_type: RelationType
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CapabilityGraph:
    """Graph manager backed by SQLite relational tables."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def add_node(self, node: CapabilityNode) -> None:
        self.add_nodes_batch([node])

    def add_nodes_batch(self, nodes: List[CapabilityNode]) -> None:
        if not nodes:
            return
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.executemany(
                """
                INSERT INTO capability_nodes (id, node_type, name, identifier, blender_version, description, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    node_type = excluded.node_type,
                    name = excluded.name,
                    identifier = excluded.identifier,
                    blender_version = excluded.blender_version,
                    description = excluded.description,
                    payload_json = excluded.payload_json
                """,
                [
                    (
                        n.id,
                        n.node_type.value,
                        n.name,
                        n.identifier,
                        n.blender_version,
                        n.description,
                        json.dumps(n.payload, ensure_ascii=False),
                        n.created_at,
                    )
                    for n in nodes
                ]
            )
            conn.commit()

    def add_edge(self, edge: CapabilityEdge) -> int:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO capability_edges (source_id, target_id, relation_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    edge.source_id,
                    edge.target_id,
                    edge.relation_type.value,
                    json.dumps(edge.payload, ensure_ascii=False),
                    edge.created_at,
                )
            )
            conn.commit()
            return cur.lastrowid or 0

    def get_node(self, node_id: str) -> Optional[CapabilityNode]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM capability_nodes WHERE id = ?", (node_id,))
            row = cur.fetchone()
            if not row:
                return None
            return CapabilityNode(
                id=row["id"],
                node_type=NodeType(row["node_type"]),
                name=row["name"],
                identifier=row["identifier"],
                blender_version=row["blender_version"],
                description=row["description"],
                payload=json.loads(row["payload_json"] or "{}"),
                created_at=row["created_at"],
            )

    def find_edges(self, source_id: Optional[str] = None, target_id: Optional[str] = None, relation_type: Optional[RelationType] = None) -> List[CapabilityEdge]:
        query = "SELECT * FROM capability_edges WHERE 1=1"
        params: List[Any] = []
        if source_id:
            query += " AND source_id = ?"
            params.append(source_id)
        if target_id:
            query += " AND target_id = ?"
            params.append(target_id)
        if relation_type:
            query += " AND relation_type = ?"
            params.append(relation_type.value)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            return [
                CapabilityEdge(
                    id=r["id"],
                    source_id=r["source_id"],
                    target_id=r["target_id"],
                    relation_type=RelationType(r["relation_type"]),
                    payload=json.loads(r["payload_json"] or "{}"),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def find_alternatives(self, node_id: str) -> List[CapabilityNode]:
        """Find alternative approaches to a capability."""
        edges = self.find_edges(source_id=node_id, relation_type=RelationType.ALTERNATIVE_TO)
        nodes: List[CapabilityNode] = []
        for e in edges:
            alt = self.get_node(e.target_id)
            if alt:
                nodes.append(alt)
        return nodes
