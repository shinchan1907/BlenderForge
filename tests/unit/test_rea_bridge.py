"""Tests for REA bridge and static reverse-engineering analysis."""

from pathlib import Path
from blenderforge.discovery.rea_bridge import REABridge


def test_rea_availability_and_version():
    bridge = REABridge()
    # On this local Windows environment, npx and rea-agents are installed
    assert bridge.is_available() is True
    version = bridge.get_version()
    assert version is not None
    assert "6." in version


def test_rea_doctor_and_capabilities():
    bridge = REABridge()
    caps = bridge.list_capabilities()
    assert caps.get("available") is True
    assert caps.get("cli_commands_count", 0) > 100
    assert caps.get("mcp_tools_count", 0) > 150


def test_rea_analyze_local_target(tmp_path: Path):
    sample_file = tmp_path / "addon_sample.py"
    sample_file.write_text(
        "import bpy\n"
        "class MESH_OT_custom_bevel(bpy.types.Operator):\n"
        "    bl_idname = 'mesh.custom_bevel'\n"
        "    def execute(self, context):\n"
        "        bpy.ops.mesh.primitive_cube_add()\n"
        "        return {'FINISHED'}\n",
        encoding="utf-8"
    )

    bridge = REABridge()
    finding = bridge.analyze_source_target(sample_file, "Custom Bevel Operator Workflow")

    assert finding.id.startswith("finding_addon_sample")
    assert "mesh.custom_bevel" in finding.evidence_excerpt or "bpy.ops" in finding.evidence_excerpt
    assert finding.confidence >= 0.8
