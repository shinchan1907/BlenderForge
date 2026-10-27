"""Unit tests for Blender API inventory comparison and diff generation."""

from blenderforge.discovery.diff import compare_inventories, format_diff_markdown


def test_compare_inventories_diff():
    inv_a = {
        "blender": {"version_string": "4.2.0"},
        "sha256": "hash_a",
        "modifiers": [{"identifier": "BEVEL", "name": "Bevel"}],
        "nodes": {"geometry_nodes": ["GeometryNodeMeshCube"]},
        "operators": {"mesh": {"primitive_cube_add": {}}},
        "render_engines": [{"identifier": "BLENDER_EEVEE", "name": "EEVEE"}],
    }

    inv_b = {
        "blender": {"version_string": "5.2.2 LTS"},
        "sha256": "hash_b",
        "modifiers": [
            {"identifier": "BEVEL", "name": "Bevel"},
            {"identifier": "NODES", "name": "Geometry Nodes"},
        ],
        "nodes": {
            "geometry_nodes": [
                "GeometryNodeMeshCube",
                "GeometryNodeExtrudeMesh",
            ]
        },
        "operators": {
            "mesh": {
                "primitive_cube_add": {},
                "primitive_cone_add": {},
            }
        },
        "render_engines": [
            {"identifier": "BLENDER_EEVEE", "name": "EEVEE"},
            {"identifier": "CYCLES", "name": "Cycles"},
        ],
    }

    diff = compare_inventories(inv_a, inv_b)

    assert diff["version_a"] == "4.2.0"
    assert diff["version_b"] == "5.2.2 LTS"
    assert "Geometry Nodes" in diff["modifiers"]["added"]
    assert "GeometryNodeExtrudeMesh" in diff["geometry_nodes"]["added"]
    assert "bpy.ops.mesh.primitive_cone_add" in diff["operators"]["added"]
    assert "CYCLES" in diff["render_engines"]["added"]

    md = format_diff_markdown(diff)
    assert "Blender Version Difference Report" in md
    assert "Newly Available Geometry Nodes" in md
