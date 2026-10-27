"""Adapter Registry for managing multiple MCP servers, tool discovery, and overlap analysis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from blenderforge.adapters.base import BaseMCPAdapter
from blenderforge.adapters.mock_adapter import MockMCPAdapter
from blenderforge.adapters.models import DiscoveredTool, ServerConfig, TransportType
from blenderforge.adapters.sse_adapter import SSEMCPAdapter
from blenderforge.adapters.stdio_adapter import StdioMCPAdapter
from blenderforge.storage.db import DatabaseManager


class AdapterRegistry:
    """Central registry and connection manager for MCP adapters."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._adapters: Dict[str, BaseMCPAdapter] = {}
        self._tools_cache: Dict[str, List[DiscoveredTool]] = {}

    def register_server(self, config: ServerConfig) -> BaseMCPAdapter:
        """Register a server configuration and instantiate its adapter."""
        if config.transport == TransportType.MOCK:
            adapter = MockMCPAdapter(config)
        elif config.transport == TransportType.STDIO:
            adapter = StdioMCPAdapter(config)
        elif config.transport == TransportType.SSE:
            adapter = SSEMCPAdapter(config)
        else:
            raise ValueError(f"Unsupported transport type: {config.transport}")

        self._adapters[config.id] = adapter
        self._persist_server(config, status="registered")
        return adapter

    def get_adapter(self, server_id: str) -> Optional[BaseMCPAdapter]:
        return self._adapters.get(server_id)

    def list_registered_servers(self) -> List[ServerConfig]:
        return [adapter.config for adapter in self._adapters.values()]

    async def discover_all(self) -> Dict[str, List[DiscoveredTool]]:
        """Connect to all registered servers and discover available tools."""
        results: Dict[str, List[DiscoveredTool]] = {}
        for server_id, adapter in self._adapters.items():
            try:
                if not adapter.is_connected:
                    await adapter.connect()
                tools = await adapter.list_tools()
                self._tools_cache[server_id] = tools
                results[server_id] = tools
                self._persist_tools(server_id, tools)
                self._persist_server(adapter.config, status="connected")
            except Exception as e:
                self._persist_server(adapter.config, status=f"error: {str(e)}")
                results[server_id] = []
        return results

    def detect_overlapping_capabilities(self) -> List[Dict[str, Any]]:
        """
        Identify potentially overlapping tools across different servers
        without assuming identical semantics.
        """
        all_tools: List[DiscoveredTool] = []
        for tools in self._tools_cache.values():
            all_tools.extend(tools)

        overlaps: List[Dict[str, Any]] = []
        # Compare pairwise
        for i in range(len(all_tools)):
            for j in range(i + 1, len(all_tools)):
                t1 = all_tools[i]
                t2 = all_tools[j]
                if t1.server_id == t2.server_id:
                    continue

                # Heuristic semantic similarity score
                similarity_reasons = []
                name1_norm = t1.name.lower().replace("-", "_").replace(".", "_")
                name2_norm = t2.name.lower().replace("-", "_").replace(".", "_")

                if name1_norm == name2_norm:
                    similarity_reasons.append("identical_name")
                elif any(tok in name2_norm for tok in name1_norm.split("_") if len(tok) > 3):
                    similarity_reasons.append("common_name_tokens")

                # Both mutation or both read-only
                if t1.is_mutation == t2.is_mutation:
                    similarity_reasons.append("matching_mutation_class")

                if similarity_reasons:
                    overlaps.append({
                        "tool_a": t1.id,
                        "tool_b": t2.id,
                        "server_a": t1.server_name,
                        "server_b": t2.server_name,
                        "similarity_reasons": similarity_reasons,
                        "schema_a_props": list((t1.input_schema.get("properties") or {}).keys()),
                        "schema_b_props": list((t2.input_schema.get("properties") or {}).keys()),
                    })
        return overlaps

    def _persist_server(self, config: ServerConfig, status: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO mcp_servers (id, name, transport_type, config_json, status, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    transport_type = excluded.transport_type,
                    config_json = excluded.config_json,
                    status = excluded.status,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    config.id,
                    config.name,
                    config.transport.value,
                    json.dumps(config.model_dump(), ensure_ascii=False),
                    status,
                    now
                )
            )
            conn.commit()

    def _persist_tools(self, server_id: str, tools: List[DiscoveredTool]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
            for t in tools:
                cur.execute(
                    """
                    INSERT INTO mcp_tools (id, server_id, name, description, input_schema_json, is_mutation, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        t.id,
                        server_id,
                        t.name,
                        t.description or "",
                        json.dumps(t.input_schema, ensure_ascii=False),
                        1 if t.is_mutation else 0,
                        now
                    )
                )
            conn.commit()
