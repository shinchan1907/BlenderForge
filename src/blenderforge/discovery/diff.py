"""Version difference report generator between two Blender API inventories."""

from __future__ import annotations

from typing import Any, Dict, List, Set


def compare_inventories(inv_a: Dict[str, Any], inv_b: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate semantic differences between two Blender runtime inventories."""
    ver_a = inv_a.get("blender", {}).get("version_string", "Version A")
    ver_b = inv_b.get("blender", {}).get("version_string", "Version B")

    # 1. Modifiers comparison
    mods_a = {m["identifier"]: m for m in inv_a.get("modifiers", [])}
    mods_b = {m["identifier"]: m for m in inv_b.get("modifiers", [])}
    added_modifiers = [mods_b[k]["name"] for k in set(mods_b) - set(mods_a)]
    removed_modifiers = [mods_a[k]["name"] for k in set(mods_a) - set(mods_b)]

    # 2. Geometry Nodes comparison
    nodes_a = set(inv_a.get("nodes", {}).get("geometry_nodes", []))
    nodes_b = set(inv_b.get("nodes", {}).get("geometry_nodes", []))
    added_geo_nodes = sorted(list(nodes_b - nodes_a))
    removed_geo_nodes = sorted(list(nodes_a - nodes_b))

    # 3. Operators comparison
    ops_a: Set[str] = set()
    for cat, ops in inv_a.get("operators", {}).items():
        for op in ops.keys():
            ops_a.add(f"bpy.ops.{cat}.{op}")

    ops_b: Set[str] = set()
    for cat, ops in inv_b.get("operators", {}).items():
        for op in ops.keys():
            ops_b.add(f"bpy.ops.{cat}.{op}")

    added_operators = sorted(list(ops_b - ops_a))
    removed_operators = sorted(list(ops_a - ops_b))

    # 4. Render engines comparison
    eng_a = {e["identifier"] for e in inv_a.get("render_engines", [])}
    eng_b = {e["identifier"] for e in inv_b.get("render_engines", [])}
    added_engines = sorted(list(eng_b - eng_a))
    removed_engines = sorted(list(eng_a - eng_b))

    return {
        "version_a": ver_a,
        "version_b": ver_b,
        "hash_a": inv_a.get("sha256", "none"),
        "hash_b": inv_b.get("sha256", "none"),
        "operators": {
            "added_count": len(added_operators),
            "removed_count": len(removed_operators),
            "added": added_operators[:50],  # Bounded for reporting
            "removed": removed_operators[:50],
        },
        "modifiers": {
            "added": added_modifiers,
            "removed": removed_modifiers,
        },
        "geometry_nodes": {
            "added_count": len(added_geo_nodes),
            "removed_count": len(removed_geo_nodes),
            "added": added_geo_nodes[:50],
            "removed": removed_geo_nodes[:50],
        },
        "render_engines": {
            "added": added_engines,
            "removed": removed_engines,
        }
    }


def format_diff_markdown(diff: Dict[str, Any]) -> str:
    """Format inventory difference as Markdown."""
    lines = [
        f"# Blender Version Difference Report",
        f"**Baseline (A):** {diff['version_a']} (`{diff['hash_a'][:12]}`)",
        f"**Comparison (B):** {diff['version_b']} (`{diff['hash_b'][:12]}`)\n",
        "## Summary of Changes",
        f"- **Operators:** +{diff['operators']['added_count']} added, -{diff['operators']['removed_count']} removed",
        f"- **Modifiers:** +{len(diff['modifiers']['added'])} added, -{len(diff['modifiers']['removed'])} removed",
        f"- **Geometry Nodes:** +{diff['geometry_nodes']['added_count']} added, -{diff['geometry_nodes']['removed_count']} removed\n",
    ]

    if diff["modifiers"]["added"]:
        lines.append(f"### Added Modifiers\n- " + "\n- ".join(diff["modifiers"]["added"]))
    if diff["modifiers"]["removed"]:
        lines.append(f"### Removed Modifiers\n- " + "\n- ".join(diff["modifiers"]["removed"]))

    if diff["geometry_nodes"]["added"]:
        lines.append(f"\n### Newly Available Geometry Nodes\n- " + "\n- ".join(diff["geometry_nodes"]["added"][:20]))

    if diff["operators"]["added"]:
        lines.append(f"\n### Newly Available Operators\n- " + "\n- ".join(diff["operators"]["added"][:20]))

    return "\n".join(lines)
