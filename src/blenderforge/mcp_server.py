"""BlenderForge MCP Server exposing local-first Blender capabilities over standard MCP stdio."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from blenderforge.config import BlenderForgeConfig, load_config
from blenderforge.discovery.blender_api import BlenderDiscoveryEngine
from blenderforge.discovery.rea_bridge import REABridge
from blenderforge.evaluation.benchmark_runner import BenchmarkRunner
from blenderforge.evaluation.validators import validate_mesh_topology
from blenderforge.skills.registry import SkillRegistry
from blenderforge.storage.db import DatabaseManager

app = Server("blenderforge-mcp")


@app.list_tools()
async def list_tools() -> List[types.Tool]:
    """Declare available BlenderForge tools."""
    return [
        types.Tool(
            name="blenderforge_doctor",
            description="Inspect local Blender installation, Python environment, and database readiness.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="blenderforge_introspect",
            description="Perform runtime API introspection on the installed Blender build without mutating scene state.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="blenderforge_search_skills",
            description="Search the verified Blender skill library using FTS5 full-text search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or natural language task."}
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="blenderforge_validate_mesh",
            description="Perform deterministic manifold, connectivity, and topological checks on mesh statistics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "vertex_count": {"type": "integer"},
                    "edge_count": {"type": "integer"},
                    "face_count": {"type": "integer"},
                    "non_manifold_edges": {"type": "integer", "default": 0},
                },
                "required": ["vertex_count", "edge_count", "face_count"],
            },
        ),
        types.Tool(
            name="blenderforge_rea_status",
            description="Inspect Reverse Engineer Anything (REA) status, catalog size, and provider health.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="blenderforge_run_benchmark",
            description="Execute the locked capability benchmark suite across Blender and tools.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
    """Handle incoming MCP tool execution."""
    cfg = load_config()
    db = DatabaseManager(cfg.db_path)

    if name == "blenderforge_doctor":
        exe = cfg.resolve_blender_executable()
        result = {
            "blender_available": exe is not None,
            "blender_path": str(exe) if exe else None,
            "operating_mode": cfg.operating_mode.value,
            "db_path": str(cfg.db_path),
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "blenderforge_introspect":
        engine = BlenderDiscoveryEngine(cfg, db)
        data = engine.run_introspection()
        summary = {
            "version": data.get("blender", {}).get("version_string"),
            "sha256": data.get("sha256"),
            "modifiers_count": len(data.get("modifiers", [])),
            "geo_nodes_count": len(data.get("nodes", {}).get("geometry_nodes", [])),
        }
        return [types.TextContent(type="text", text=json.dumps(summary, indent=2))]

    elif name == "blenderforge_search_skills":
        reg = SkillRegistry(db)
        skills = reg.search_skills(arguments.get("query", ""))
        res = [s.model_dump() for s in skills]
        return [types.TextContent(type="text", text=json.dumps(res, indent=2))]

    elif name == "blenderforge_validate_mesh":
        report = validate_mesh_topology(
            vertex_count=arguments.get("vertex_count", 0),
            edge_count=arguments.get("edge_count", 0),
            face_count=arguments.get("face_count", 0),
            non_manifold_edges=arguments.get("non_manifold_edges", 0),
        )
        return [types.TextContent(type="text", text=json.dumps(report.model_dump(), indent=2))]

    elif name == "blenderforge_rea_status":
        rea = REABridge(db)
        status = {
            "available": rea.is_available(),
            "version": rea.get_version(),
            "capabilities": rea.list_capabilities(),
        }
        return [types.TextContent(type="text", text=json.dumps(status, indent=2))]

    elif name == "blenderforge_run_benchmark":
        bench = BenchmarkRunner(cfg, db)
        report = bench.run_all()
        return [types.TextContent(type="text", text=json.dumps(report.model_dump(), indent=2))]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="blenderforge-mcp",
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
