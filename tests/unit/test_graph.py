"""Tests for Capability Graph relationships and queries."""

from pathlib import Path
from blenderforge.discovery.graph import (
    CapabilityEdge,
    CapabilityGraph,
    CapabilityNode,
    NodeType,
    RelationType,
)
from blenderforge.storage.db import DatabaseManager


def test_capability_graph_nodes_and_edges(tmp_path: Path):
    db = DatabaseManager(tmp_path / "test.db")
    graph = CapabilityGraph(db)

    # Add node 1: Primitive Cube operator
    node1 = CapabilityNode(
        id="bpy.ops.mesh.primitive_cube_add",
        node_type=NodeType.API_OPERATOR,
        name="primitive_cube_add",
        identifier="bpy.ops.mesh.primitive_cube_add",
        description="Add a cube mesh",
    )
    graph.add_node(node1)

    # Add node 2: Geometry Nodes Cube
    node2 = CapabilityNode(
        id="geometry_nodes.mesh_cube",
        node_type=NodeType.NODE_TYPE,
        name="Mesh Cube Node",
        identifier="GeometryNodeMeshCube",
        description="Procedural cube generator in Geometry Nodes",
    )
    graph.add_node(node2)

    # Add alternative_to edge
    edge = CapabilityEdge(
        source_id=node2.id,
        target_id=node1.id,
        relation_type=RelationType.ALTERNATIVE_TO,
        payload={"reason": "Procedural alternative to destructive mesh operator"}
    )
    edge_id = graph.add_edge(edge)
    assert edge_id > 0

    # Test retrieval
    retrieved = graph.get_node(node1.id)
    assert retrieved is not None
    assert retrieved.name == "primitive_cube_add"

    # Test alternative discovery
    alts = graph.find_alternatives(node2.id)
    assert len(alts) == 1
    assert alts[0].id == node1.id
