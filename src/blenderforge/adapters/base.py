"""Base adapter interface and policy enforcement for MCP servers."""

from __future__ import annotations

import abc
import asyncio
import time
from typing import Any, Dict, List, Optional
import jsonschema

from blenderforge.adapters.models import DiscoveredTool, ServerConfig, ToolCallResult
from blenderforge.config import OperatingMode


MUTATION_KEYWORDS = {
    "create", "add", "delete", "remove", "set", "modify", "update", "apply",
    "transform", "execute", "run", "import", "export", "render", "save",
    "clear", "generate", "build", "link", "unlink", "join", "split"
}

READ_KEYWORDS = {
    "get", "list", "inspect", "read", "check", "describe", "find", "search",
    "show", "query", "version", "status", "info"
}


def classify_tool_mutation(name: str, description: Optional[str] = None) -> bool:
    """Heuristically classify whether a tool causes state mutations."""
    lower_name = name.lower().replace("-", "_")
    parts = lower_name.split("_")

    # If any token matches mutation keywords
    for p in parts:
        if p in MUTATION_KEYWORDS:
            return True
        if p in READ_KEYWORDS:
            return False

    if description:
        lower_desc = description.lower()
        if any(f" {kw} " in f" {lower_desc} " for kw in MUTATION_KEYWORDS):
            return True

    # Default to False (safe/read-only) unless identified as mutating
    return False


class BaseMCPAdapter(abc.ABC):
    """Abstract provider-neutral adapter for Model Context Protocol servers."""

    def __init__(self, config: ServerConfig):
        self.config = config
        self.is_connected = False
        self._lock = asyncio.Lock()  # Serializes requests to prevent race conditions on shared instance

    @abc.abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the MCP server."""
        pass

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close connection cleanly."""
        pass

    @abc.abstractmethod
    async def list_tools(self) -> List[DiscoveredTool]:
        """Discover tools declared by the server."""
        pass

    @abc.abstractmethod
    async def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Underlying raw tool call implementation."""
        pass

    async def call_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        operating_mode: OperatingMode,
        tools_cache: Optional[List[DiscoveredTool]] = None
    ) -> ToolCallResult:
        """
        Validate schema, enforce operating mode permissions, serialize mutations,
        and execute tool with timeout.
        """
        start_time = time.perf_counter()
        tool_id = f"{self.config.id}:{name}"

        # Resolve tool metadata
        tool = None
        if tools_cache:
            for t in tools_cache:
                if t.name == name:
                    tool = t
                    break

        if tool is None:
            is_mutation = classify_tool_mutation(name)
        else:
            is_mutation = tool.is_mutation

        # Enforce security policy: No mutations in INSPECT mode
        if is_mutation and operating_mode == OperatingMode.INSPECT:
            return ToolCallResult(
                tool_id=tool_id,
                success=False,
                error=f"PermissionDenied: Tool '{name}' is a state-changing mutation, which is blocked in '{operating_mode.value}' mode.",
                duration_sec=time.perf_counter() - start_time
            )

        # Validate arguments against input schema if schema is available
        if tool and tool.input_schema:
            try:
                jsonschema.validate(instance=arguments, schema=tool.input_schema)
            except jsonschema.ValidationError as val_err:
                return ToolCallResult(
                    tool_id=tool_id,
                    success=False,
                    error=f"SchemaValidationError: {val_err.message}",
                    duration_sec=time.perf_counter() - start_time
                )

        # Execute under lock to serialize access to the Blender instance
        async with self._lock:
            try:
                async with asyncio.timeout(self.config.timeout_sec):
                    data = await self._execute_tool(name, arguments)
                    return ToolCallResult(
                        tool_id=tool_id,
                        success=True,
                        data=data,
                        duration_sec=time.perf_counter() - start_time
                    )
            except asyncio.TimeoutError:
                return ToolCallResult(
                    tool_id=tool_id,
                    success=False,
                    error=f"TimeoutError: Tool call exceeded {self.config.timeout_sec}s.",
                    duration_sec=time.perf_counter() - start_time
                )
            except Exception as e:
                return ToolCallResult(
                    tool_id=tool_id,
                    success=False,
                    error=f"{type(e).__name__}: {str(e)}",
                    duration_sec=time.perf_counter() - start_time
                )
