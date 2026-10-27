"""Tests for MCP adapters, security mode policy enforcement, and registry."""

import pytest
from blenderforge.adapters.base import classify_tool_mutation
from blenderforge.adapters.mock_adapter import MockMCPAdapter
from blenderforge.adapters.models import ServerConfig, TransportType
from blenderforge.adapters.registry import AdapterRegistry
from blenderforge.config import OperatingMode
from blenderforge.storage.db import DatabaseManager


def test_classify_tool_mutation():
    assert classify_tool_mutation("get_scene_info") is False
    assert classify_tool_mutation("read_mesh_vertices") is False
    assert classify_tool_mutation("create_cube") is True
    assert classify_tool_mutation("delete_hierarchy") is True
    assert classify_tool_mutation("apply_modifier") is True


@pytest.mark.asyncio
async def test_mock_adapter_read_only_in_inspect_mode():
    cfg = ServerConfig(id="test-mock", name="Test Mock", transport=TransportType.MOCK)
    adapter = MockMCPAdapter(cfg)
    await adapter.connect()

    tools = await adapter.list_tools()
    assert len(tools) >= 3

    # get_scene_info is read-only -> should succeed in INSPECT mode
    res = await adapter.call_tool("get_scene_info", {}, operating_mode=OperatingMode.INSPECT, tools_cache=tools)
    assert res.success is True
    assert res.data["scene"] == "Scene"

    await adapter.disconnect()


@pytest.mark.asyncio
async def test_mock_adapter_mutation_blocked_in_inspect_mode():
    cfg = ServerConfig(id="test-mock", name="Test Mock", transport=TransportType.MOCK)
    adapter = MockMCPAdapter(cfg)
    await adapter.connect()

    tools = await adapter.list_tools()

    # create_primitive_mesh is mutation -> should be blocked in INSPECT mode
    res = await adapter.call_tool(
        "create_primitive_mesh",
        {"primitive_type": "cube"},
        operating_mode=OperatingMode.INSPECT,
        tools_cache=tools
    )
    assert res.success is False
    assert "PermissionDenied" in res.error

    # In EXPERIMENT mode, it should be permitted
    res_exp = await adapter.call_tool(
        "create_primitive_mesh",
        {"primitive_type": "cube"},
        operating_mode=OperatingMode.EXPERIMENT,
        tools_cache=tools
    )
    assert res_exp.success is True
    assert res_exp.data["status"] == "created"

    await adapter.disconnect()


@pytest.mark.asyncio
async def test_mock_adapter_schema_validation():
    cfg = ServerConfig(id="test-mock", name="Test Mock", transport=TransportType.MOCK)
    adapter = MockMCPAdapter(cfg)
    await adapter.connect()

    tools = await adapter.list_tools()

    # Pass invalid argument (missing required 'primitive_type')
    res = await adapter.call_tool(
        "create_primitive_mesh",
        {"size": 2.0},  # missing required primitive_type
        operating_mode=OperatingMode.EXPERIMENT,
        tools_cache=tools
    )
    assert res.success is False
    assert "SchemaValidationError" in res.error

    await adapter.disconnect()


@pytest.mark.asyncio
async def test_adapter_registry_overlap_detection(tmp_path):
    db = DatabaseManager(tmp_path / "test.db")
    reg = AdapterRegistry(db)

    # Server 1
    reg.register_server(ServerConfig(id="srv1", name="Server 1", transport=TransportType.MOCK))

    # Server 2 with overlapping tool
    cfg2 = ServerConfig(id="srv2", name="Server 2", transport=TransportType.MOCK)
    adapter2 = MockMCPAdapter(cfg2, mock_tools=[
        {
            "name": "create_primitive_mesh",
            "description": "Create mesh in server 2",
            "input_schema": {"type": "object", "properties": {"primitive_type": {"type": "string"}}},
            "is_mutation": True
        }
    ])
    reg._adapters["srv2"] = adapter2

    await reg.discover_all()
    overlaps = reg.detect_overlapping_capabilities()

    assert len(overlaps) >= 1
    assert any("create_primitive_mesh" in o["tool_a"] or "create_primitive_mesh" in o["tool_b"] for o in overlaps)
