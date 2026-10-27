"""Mock MCP adapter for testing, demonstration, and isolated verification."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from blenderforge.adapters.base import BaseMCPAdapter, classify_tool_mutation
from blenderforge.adapters.models import DiscoveredTool, ServerConfig


class MockMCPAdapter(BaseMCPAdapter):
    """Simulated MCP adapter with realistic Blender tools."""

    def __init__(self, config: ServerConfig, mock_tools: Optional[List[Dict[str, Any]]] = None):
        super().__init__(config)
        self.mock_tools_def = mock_tools or [
            {
                "name": "get_scene_info",
                "description": "Returns current active scene information and object counts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "scene_name": {"type": "string"}
                    }
                },
                "is_mutation": False,
            },
            {
                "name": "create_primitive_mesh",
                "description": "Adds a new primitive mesh (cube, sphere, cylinder) to the scene.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "primitive_type": {"type": "string", "enum": ["cube", "sphere", "cylinder"]},
                        "size": {"type": "number"}
                    },
                    "required": ["primitive_type"]
                },
                "is_mutation": True,
            },
            {
                "name": "render_preview",
                "description": "Renders a viewport snapshot or preview frame to an image file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "output_path": {"type": "string"},
                        "resolution_x": {"type": "integer"},
                        "resolution_y": {"type": "integer"}
                    },
                    "required": ["output_path"]
                },
                "is_mutation": True,
            }
        ]

    async def connect(self) -> bool:
        self.is_connected = True
        return True

    async def disconnect(self) -> None:
        self.is_connected = False

    async def list_tools(self) -> List[DiscoveredTool]:
        tools: List[DiscoveredTool] = []
        for defn in self.mock_tools_def:
            is_mut = defn.get("is_mutation", classify_tool_mutation(defn["name"], defn.get("description")))
            tools.append(
                DiscoveredTool(
                    id=f"{self.config.id}:{defn['name']}",
                    server_id=self.config.id,
                    server_name=self.config.name,
                    name=defn["name"],
                    description=defn.get("description"),
                    input_schema=defn.get("input_schema", {}),
                    is_mutation=is_mut,
                )
            )
        return tools

    async def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name == "get_scene_info":
            return {"scene": "Scene", "objects_count": 3, "render_engine": "CYCLES"}
        elif name == "create_primitive_mesh":
            return {"status": "created", "name": f"{arguments.get('primitive_type', 'cube')}_001"}
        elif name == "render_preview":
            return {"status": "rendered", "path": arguments.get("output_path")}
        else:
            raise ValueError(f"Unknown mock tool: {name}")
