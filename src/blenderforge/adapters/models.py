"""Data models for MCP adapters and capability discovery."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TransportType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    MOCK = "mock"


class ServerConfig(BaseModel):
    """Configuration for an external MCP server."""
    id: str = Field(..., description="Unique identifier for the server.")
    name: str = Field(..., description="Human-readable server name.")
    transport: TransportType = Field(default=TransportType.STDIO)
    command: Optional[str] = Field(default=None, description="Executable command for stdio.")
    args: List[str] = Field(default_factory=list, description="Command line arguments.")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables.")
    url: Optional[str] = Field(default=None, description="Endpoint URL for SSE.")
    timeout_sec: float = Field(default=30.0, description="Request timeout in seconds.")


class DiscoveredTool(BaseModel):
    """Normalized MCP tool representation."""
    id: str = Field(..., description="Unique tool identifier, e.g. server_id:tool_name.")
    server_id: str
    server_name: str
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    is_mutation: bool = Field(default=False, description="Whether this tool mutates scene or filesystem state.")


class ToolCallResult(BaseModel):
    """Outcome of an MCP tool invocation."""
    tool_id: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    duration_sec: float = 0.0
