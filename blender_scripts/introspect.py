"""Blender runtime introspection script executed in Blender background mode.

Discovers API operators, RNA types, modifiers, node types, and capabilities
WITHOUT calling operators or mutating scene data.
"""

import hashlib
import json
import os
import sys

try:
    import bpy
    import addon_utils
except ImportError:
    print("ERROR: This script must be executed from within Blender.", file=sys.stderr)
    sys.exit(1)


def sanitize_val(v):
    """Sanitize runtime value into JSON-safe type."""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, (set, tuple)):
        return [sanitize_val(x) for x in v]
    if isinstance(v, dict):
        return {k: sanitize_val(val) for k, val in v.items()}
    if isinstance(v, list):
        return [sanitize_val(x) for x in v]
    return v


def get_operator_properties(op_func):
    """Extract RNA properties of an operator safely without execution."""
    props = {}
    try:
        rna = op_func.get_rna_type()
        for prop in rna.properties:
            if prop.identifier in {"rna_type"}:
                continue
            prop_info = {
                "name": str(prop.name),
                "description": str(prop.description),
                "type": str(prop.type),
                "is_readonly": bool(prop.is_readonly),
            }
            if prop.type == "ENUM":
                prop_info["enum_items"] = [item.identifier for item in prop.enum_items]
            props[prop.identifier] = prop_info
    except Exception as e:
        props["_error"] = str(e)
    return props


def introspect_runtime():
    """Perform non-destructive runtime capability inventory."""
    inventory = {
        "blender": {
            "version": list(bpy.app.version),
            "version_string": sanitize_val(bpy.app.version_string),
            "build_date": sanitize_val(getattr(bpy.app, "build_date", "unknown")),
            "build_hash": sanitize_val(getattr(bpy.app, "build_hash", "unknown")),
            "build_branch": sanitize_val(getattr(bpy.app, "build_branch", "unknown")),
            "build_platform": sanitize_val(getattr(bpy.app, "build_platform", "unknown")),
            "python_version": sys.version.split()[0],
        },
        "operators": {},
        "modifiers": [],
        "constraints": [],
        "nodes": {
            "geometry_nodes": [],
            "shader_nodes": [],
            "compositor_nodes": [],
        },
        "render_engines": [],
        "importers": [],
        "exporters": [],
        "addons": [],
    }

    # 1. Operators: Inspect key operational modules
    target_modules = [
        "mesh", "curve", "surface", "object", "material", "node",
        "render", "export_scene", "import_scene", "geometry_nodes",
        "armature", "anim", "action", "transform"
    ]
    for mod_name in target_modules:
        if hasattr(bpy.ops, mod_name):
            mod = getattr(bpy.ops, mod_name)
            op_dict = {}
            for op_name in dir(mod):
                if op_name.startswith("_"):
                    continue
                op_func = getattr(mod, op_name)
                # Ensure it's a callable operator
                if callable(op_func):
                    op_dict[op_name] = {
                        "identifier": f"bpy.ops.{mod_name}.{op_name}",
                        "properties": get_operator_properties(op_func)
                    }
            inventory["operators"][mod_name] = op_dict

    # 2. Modifiers
    try:
        mod_type_prop = bpy.types.Modifier.bl_rna.properties.get("type")
        if mod_type_prop and hasattr(mod_type_prop, "enum_items"):
            inventory["modifiers"] = [
                {"identifier": item.identifier, "name": str(item.name), "description": str(item.description)}
                for item in mod_type_prop.enum_items
            ]
    except Exception as e:
        inventory["modifiers_error"] = str(e)

    # 3. Constraints
    try:
        cons_type_prop = bpy.types.Constraint.bl_rna.properties.get("type")
        if cons_type_prop and hasattr(cons_type_prop, "enum_items"):
            inventory["constraints"] = [
                {"identifier": item.identifier, "name": str(item.name), "description": str(item.description)}
                for item in cons_type_prop.enum_items
            ]
    except Exception as e:
        inventory["constraints_error"] = str(e)

    # 4. Node Types
    try:
        for attr in dir(bpy.types):
            if attr.startswith("GeometryNode"):
                inventory["nodes"]["geometry_nodes"].append(attr)
            elif attr.startswith("ShaderNode"):
                inventory["nodes"]["shader_nodes"].append(attr)
            elif attr.startswith("CompositorNode"):
                inventory["nodes"]["compositor_nodes"].append(attr)
    except Exception as e:
        inventory["nodes_error"] = str(e)

    # 5. Render engines
    try:
        engine_prop = bpy.types.RenderSettings.bl_rna.properties.get("engine")
        if engine_prop and hasattr(engine_prop, "enum_items"):
            inventory["render_engines"] = [
                {"identifier": item.identifier, "name": str(item.name)}
                for item in engine_prop.enum_items
            ]
    except Exception as e:
        inventory["render_engines_error"] = str(e)

    # 6. Exporters and Importers
    if hasattr(bpy.ops, "export_scene"):
        inventory["exporters"].extend(dir(bpy.ops.export_scene))
    if hasattr(bpy.ops, "export_mesh"):
        inventory["exporters"].extend(dir(bpy.ops.export_mesh))
    if hasattr(bpy.ops, "import_scene"):
        inventory["importers"].extend(dir(bpy.ops.import_scene))
    if hasattr(bpy.ops, "import_mesh"):
        inventory["importers"].extend(dir(bpy.ops.import_mesh))

    # 7. Addons
    try:
        for mod in addon_utils.modules():
            info = addon_utils.module_bl_info(mod)
            is_enabled, is_loaded = addon_utils.check(mod.__name__)
            inventory["addons"].append({
                "module": mod.__name__,
                "name": str(info.get("name", mod.__name__)),
                "version": [int(x) if isinstance(x, int) else str(x) for x in info.get("version", ())],
                "enabled": bool(is_enabled),
                "category": str(info.get("category", ""))
            })
    except Exception as e:
        inventory["addons_error"] = str(e)

    return inventory


def main():
    args = sys.argv
    output_path = None
    if "--output-json" in args:
        idx = args.index("--output-json")
        if idx + 1 < len(args):
            output_path = args[idx + 1]

    data = introspect_runtime()
    json_bytes = json.dumps(data, indent=2, sort_keys=True, default=str).encode("utf-8")
    data_hash = hashlib.sha256(json_bytes).hexdigest()
    data["sha256"] = data_hash

    if output_path:
        with open(output_path, "wb") as f:
            f.write(json.dumps(data, indent=2, sort_keys=True, default=str).encode("utf-8"))
        print(f"INTROSPECTION_COMPLETE:{output_path}:{data_hash}")
    else:
        print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    main()
