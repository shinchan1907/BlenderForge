"""Standard I/O MCP adapter communicating with subprocesses."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from blenderforge.adapters.base import BaseMCPAdapter, classify_tool_mutation
from blenderforge.adapters.models import DiscoveredTool, ServerConfig


class StdioMCPAdapter(BaseMCPAdapter):
    """MCP Adapter that launches and communicates with a child process over stdio."""

    def __init__(self, config: ServerConfig):
        super().__init__(config)
        self._session: Optional[ClientSession] = None
        self._client_cm = None

    async def connect(self) -> bool:
        if not self.config.command:
            raise ValueError(f"Stdio server {self.config.id} must define a command.")

        env = os.environ.copy()
        env.update(self.config.env)

        server_params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env=env,
        )

        try:
            self._client_cm = stdio_client(server_params)
            read_stream, write_stream = await self._client_cm.__aenter__()
            self._session = ClientSession(read_stream, write_stream)
            await self._session.__aenter__()
            await self._session.initialize()
            self.is_connected = True
            return True
        except Exception as e:
            self.is_connected = False
            await self.disconnect()
            raise ConnectionError(f"Failed to connect to stdio MCP server {self.config.id}: {e}") from e

    async def disconnect(self) -> None:
        self.is_connected = False
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None
        if self._client_cm:
            try:
                await self._client_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._client_cm = None

    async def list_tools(self) -> List[DiscoveredTool]:
        if not self._session:
            raise ConnectionError(f"Server {self.config.id} is not connected.")

        result = await self._session.list_tools()
        tools: List[DiscoveredTool] = []
        for t in result.tools:
            name = t.name
            desc = t.description or ""
            schema = t.inputSchema or {}
            is_mut = classify_tool_mutation(name, desc)
            tools.append(
                DiscoveredTool(
                    id=f"{self.config.id}:{name}",
                    server_id=self.config.id,
                    server_name=self.config.name,
                    name=name,
                    description=desc,
                    input_schema=schema,
                    is_mutation=is_mut,
                )
            )
        return tools

    async def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        if not self._session:
            raise ConnectionError(f"Server {self.config.id} is not connected.")
        res = await self._session.call_tool(name, arguments=arguments)
        return [c.model_dump() if hasattr(c, "model_dump") else str(c) for c in res.content]
