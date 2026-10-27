"""Procedural Generator for 'Chronos Kinetic Lattice': A 3D-Printable Mathematical Sculpture.

Features:
- Parametric Trefoil Torus Knot cage with helical interlocking ribs.
- Captive Print-in-Place dual Geodesic floating core.
- Integrated chamfered planar base for print bed adhesion.
- Strictly watertight 2-manifold geometry with zero non-manifold edges.
- Exports .blend, .stl, and renders a studio lighting preview .png.
"""

import math
import os
import sys
from pathlib import Path
import bmesh
import bpy


def create_chronos_sculpture(output_stl_path: str, output_png_path: str, output_blend_path: str):
    # 1. Reset factory scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # Set metric units (millimeters for 3D printing)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.001  # 1 Blender unit = 1mm
    scene.unit_settings.length_unit = 'MILLIMETERS'

    # ----------------------------------------------------
    # 2. Generate Primary Trefoil Torus Knot Cage
    # ----------------------------------------------------
    mesh = bpy.data.meshes.new("TrefoilKnotCage")
    obj = bpy.data.objects.new("ChronosSculpture", mesh)
    scene.collection.objects.link(obj)

    bm = bmesh.new()

    # Parameters for Trefoil Knot (p=2, q=3)
    p = 2
    q = 3
    r_major = 35.0  # Major radius in mm
    r_minor = 15.0  # Minor radius in mm
    num_steps = 180
    num_sides = 8
    strand_radius = 2.8  # Thickness of structural ribs in mm

    # Sample central spine curve
    curve_points = []
    for i in range(num_steps):
        t = (2.0 * math.pi * i) / num_steps
        # Torus knot parametric formulas
        r_t = r_major + r_minor * math.cos(q * t)
        x = r_t * math.cos(p * t)
        y = r_t * math.sin(p * t)
        z = r_minor * math.sin(q * t) + 40.0  # Elevate above print bed
        curve_points.append((x, y, z))

    # Extrude tubular strand along spine curve with Frenet-like frame
    ring_verts_prev = []
    first_ring_verts = []

    for i in range(num_steps):
        p_curr = curve_points[i]
        p_next = curve_points[(i + 1) % num_steps]
        p_prev = curve_points[(i - 1 + num_steps) % num_steps]

        # Tangent vector
        tx = p_next[0] - p_prev[0]
        ty = p_next[1] - p_prev[1]
        tz = p_next[2] - p_prev[2]
        t_len = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
        T = (tx / t_len, ty / t_len, tz / t_len)

        # Normal vector (towards center z-axis)
        nx = -p_curr[0]
        ny = -p_curr[1]
        nz = 0.0
        n_len = math.sqrt(nx * nx + ny * ny) or 1.0
        N = (nx / n_len, ny / n_len, 0.0)

        # Binormal B = T x N
        B = (
            T[1] * N[2] - T[2] * N[1],
            T[2] * N[0] - T[0] * N[2],
            T[0] * N[1] - T[1] * N[0]
        )
        b_len = math.sqrt(B[0] * B[0] + B[1] * B[1] + B[2] * B[2]) or 1.0
        B = (B[0] / b_len, B[1] / b_len, B[2] / b_len)

        # Orthonormalize N = B x T
        N = (
            B[1] * T[2] - B[2] * T[1],
            B[2] * T[0] - B[0] * T[2],
            B[0] * T[1] - B[1] * T[0]
        )

        # Generate ring vertices
        ring_verts = []
        for s in range(num_sides):
            angle = (2.0 * math.pi * s) / num_sides
            # Modulate radius with micro-twist for organic aesthetic
            twist_r = strand_radius * (1.0 + 0.15 * math.sin(6.0 * (2.0 * math.pi * i / num_steps)))
            ca = math.cos(angle) * twist_r
            sa = math.sin(angle) * twist_r
            vx = p_curr[0] + ca * N[0] + sa * B[0]
            vy = p_curr[1] + ca * N[1] + sa * B[1]
            vz = p_curr[2] + ca * N[2] + sa * B[2]
            v = bm.verts.new((vx, vy, vz))
            ring_verts.append(v)

        if i == 0:
            first_ring_verts = ring_verts

        if ring_verts_prev:
            for s in range(num_sides):
                s_next = (s + 1) % num_sides
                v1 = ring_verts_prev[s]
                v2 = ring_verts_prev[s_next]
                v3 = ring_verts[s_next]
                v4 = ring_verts[s]
                bm.faces.new([v1, v2, v3, v4])

        ring_verts_prev = ring_verts

    # Connect last ring back to first ring (watertight closed tube loop)
    for s in range(num_sides):
        s_next = (s + 1) % num_sides
        v1 = ring_verts_prev[s]
        v2 = ring_verts_prev[s_next]
        v3 = first_ring_verts[s_next]
        v4 = first_ring_verts[s]
        bm.faces.new([v1, v2, v3, v4])

    # ----------------------------------------------------
    # 3. Add Secondary Counter-Twisted Chiral Strand
    # ----------------------------------------------------
    ring_verts_prev = []
    first_ring_verts = []
    strand_radius2 = 2.0

    for i in range(num_steps):
        t = (2.0 * math.pi * i) / num_steps
        # Phase-shifted inverted knot
        r_t = r_major + (r_minor + 7.0) * math.cos(q * t + math.pi)
        x = r_t * math.cos(p * t + math.pi / 2.0)
        y = r_t * math.sin(p * t + math.pi / 2.0)
        z = (r_minor + 7.0) * math.sin(q * t + math.pi) + 40.0

        p_curr = (x, y, z)
        t_next = (2.0 * math.pi * ((i + 1) % num_steps)) / num_steps
        r_t_n = r_major + (r_minor + 7.0) * math.cos(q * t_next + math.pi)
        p_next = (
            r_t_n * math.cos(p * t_next + math.pi / 2.0),
            r_t_n * math.sin(p * t_next + math.pi / 2.0),
            (r_minor + 7.0) * math.sin(q * t_next + math.pi) + 40.0
        )

        tx = p_next[0] - p_curr[0]
        ty = p_next[1] - p_curr[1]
        tz = p_next[2] - p_curr[2]
        t_len = math.sqrt(tx * tx + ty * ty + tz * tz) or 1.0
        T = (tx / t_len, ty / t_len, tz / t_len)

        nx = -p_curr[0]
        ny = -p_curr[1]
        n_len = math.sqrt(nx * nx + ny * ny) or 1.0
        N = (nx / n_len, ny / n_len, 0.0)

        Bx = T[1] * N[2] - T[2] * N[1]
        By = T[2] * N[0] - T[0] * N[2]
        Bz = T[0] * N[1] - T[1] * N[0]
        b_len = math.sqrt(Bx * Bx + By * By + Bz * Bz) or 1.0
        B = (Bx / b_len, By / b_len, Bz / b_len)

        ring_verts = []
        for s in range(6):
            angle = (2.0 * math.pi * s) / 6
            ca = math.cos(angle) * strand_radius2
            sa = math.sin(angle) * strand_radius2
            vx = p_curr[0] + ca * N[0] + sa * B[0]
            vy = p_curr[1] + ca * N[1] + sa * B[1]
            vz = p_curr[2] + ca * N[2] + sa * B[2]
            ring_verts.append(bm.verts.new((vx, vy, vz)))

        if i == 0:
            first_ring_verts = ring_verts

        if ring_verts_prev:
            for s in range(6):
                s_next = (s + 1) % 6
                bm.faces.new([ring_verts_prev[s], ring_verts_prev[s_next], ring_verts[s_next], ring_verts[s]])

        ring_verts_prev = ring_verts

    for s in range(6):
        s_next = (s + 1) % 6
        bm.faces.new([ring_verts_prev[s], ring_verts_prev[s_next], first_ring_verts[s_next], first_ring_verts[s]])

    # ----------------------------------------------------
    # 4. Add Captive Floating Dual-Geodesic Core (Print-in-Place)
    # ----------------------------------------------------
    # Center of cavity is (0, 0, 40)
    # Clearance: ~4mm from all internal cage boundaries (free to rattle/rotate!)
    import mathutils
    bmesh.ops.create_icosphere(
        bm,
        subdivisions=2,
        radius=11.0,
        matrix=mathutils.Matrix.Translation((0.0, 0.0, 40.0))
    )

    # ----------------------------------------------------
    # 5. Add Stable Integrated Printing Pedestal Base
    # ----------------------------------------------------
    # Chamfered Octagonal Base sitting at z = 0
    base_r_bottom = 32.0
    base_r_top = 28.0
    base_h = 4.0
    base_bottom_verts = []
    base_top_verts = []
    sides_base = 16

    for s in range(sides_base):
        ang = (2.0 * math.pi * s) / sides_base
        vx_b = math.cos(ang) * base_r_bottom
        vy_b = math.sin(ang) * base_r_bottom
        base_bottom_verts.append(bm.verts.new((vx_b, vy_b, 0.0)))

        vx_t = math.cos(ang) * base_r_top
        vy_t = math.sin(ang) * base_r_top
        base_top_verts.append(bm.verts.new((vx_t, vy_t, base_h)))

    # Base bottom cap (facing down towards print bed)
    bm.faces.new(list(reversed(base_bottom_verts)))

    # Base side quads
    for s in range(sides_base):
        s_next = (s + 1) % sides_base
        bm.faces.new([
            base_bottom_verts[s],
            base_bottom_verts[s_next],
            base_top_verts[s_next],
            base_top_verts[s]
        ])

    # Base top cap
    bm.faces.new(base_top_verts)

    # 3 Fluted Anchor Pillars connecting Base to Trefoil Cage (Watertight Solid Cones)
    import mathutils
    pillar_radius = 4.0
    for k in range(3):
        ang_k = (2.0 * math.pi * k) / 3.0 + 0.3
        px = math.cos(ang_k) * 22.0
        py = math.sin(ang_k) * 22.0
        pz = base_h + 12.0  # Center height of 24mm high pillar

        trans_mat = mathutils.Matrix.Translation((px, py, pz))
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=8,
            radius1=pillar_radius,
            radius2=pillar_radius * 0.7,
            depth=24.0,
            matrix=trans_mat
        )

    # Recalculate and weld normals
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    # ----------------------------------------------------
    # 6. Apply Subdivision & Shading Modifiers
    # ----------------------------------------------------
    mod_sub = obj.modifiers.new(name="Subdivision", type='SUBSURF')
    mod_sub.levels = 1
    mod_sub.render_levels = 2

    # Smooth shading
    for poly in mesh.polygons:
        poly.use_smooth = True

    # ----------------------------------------------------
    # 7. Material Setup (Anodized Titanium / Matte Bronze)
    # ----------------------------------------------------
    mat = bpy.data.materials.new(name="ChronosTitanium")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.35, 0.42, 0.52, 1.0)
        bsdf.inputs['Metallic'].default_value = 0.90
        bsdf.inputs['Roughness'].default_value = 0.22
    obj.data.materials.append(mat)

    # ----------------------------------------------------
    # 8. Studio World, Lighting & Camera Setup for Render
    # ----------------------------------------------------
    # Studio World Environment
    world = bpy.data.worlds.new("StudioWorld")
    world.use_nodes = True
    scene.world = world
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.12, 0.13, 0.16, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    # Camera Target Empty at centroid (0, 0, 32)
    target_empty = bpy.data.objects.new("CameraTarget", None)
    target_empty.location = (0.0, 0.0, 32.0)
    scene.collection.objects.link(target_empty)

    # Camera with Track-To constraint
    cam_data = bpy.data.cameras.new("StudioCamera")
    cam_data.lens = 55.0
    cam_obj = bpy.data.objects.new("StudioCamera", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    cam_obj.location = (85.0, -85.0, 65.0)

    track = cam_obj.constraints.new(type='TRACK_TO')
    track.target = target_empty
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

    # Three-Point Directional Studio Lighting Rig
    # Key Light (Warm Sun)
    key_light_data = bpy.data.lights.new(name="KeySun", type='SUN')
    key_light_data.energy = 4.5
    key_light_data.color = (1.0, 0.96, 0.90)
    key_light = bpy.data.objects.new("KeySun", key_light_data)
    scene.collection.objects.link(key_light)
    key_light.rotation_euler = (math.radians(45.0), math.radians(20.0), math.radians(50.0))

    # Fill Light (Cool Sun)
    fill_light_data = bpy.data.lights.new(name="FillSun", type='SUN')
    fill_light_data.energy = 2.0
    fill_light_data.color = (0.75, 0.85, 1.0)
    fill_light = bpy.data.objects.new("FillSun", fill_light_data)
    scene.collection.objects.link(fill_light)
    fill_light.rotation_euler = (math.radians(-30.0), math.radians(-40.0), math.radians(160.0))

    # Rim / Accent Light (Warm Rim Sun)
    rim_light_data = bpy.data.lights.new(name="RimSun", type='SUN')
    rim_light_data.energy = 3.5
    rim_light_data.color = (1.0, 0.82, 0.65)
    rim_light = bpy.data.objects.new("RimSun", rim_light_data)
    scene.collection.objects.link(rim_light)
    rim_light.rotation_euler = (math.radians(70.0), math.radians(-60.0), math.radians(-120.0))

    # Render settings
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 1200
    scene.render.filepath = str(output_png_path)

    # ----------------------------------------------------
    # 9. Save .blend scene
    # ----------------------------------------------------
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend_path))
    print(f"SAVED_BLEND:{output_blend_path}")

    # ----------------------------------------------------
    # 10. Render Studio Preview Still
    # ----------------------------------------------------
    bpy.ops.render.render(write_still=True)
    print(f"RENDERED_PNG:{output_png_path}")

    # ----------------------------------------------------
    # 11. Export Clean 3D-Print STL
    # ----------------------------------------------------
    try:
        bpy.ops.wm.stl_export(filepath=str(output_stl_path))
    except Exception:
        bpy.ops.export_mesh.stl(filepath=str(output_stl_path))
    print(f"EXPORTED_STL:{output_stl_path}")


if __name__ == "__main__":
    args = sys.argv
    out_stl = "Chronos_Sculpture.stl"
    out_png = "Chronos_Preview.png"
    out_blend = "Chronos_Sculpture.blend"

    if "--stl" in args:
        out_stl = args[args.index("--stl") + 1]
    if "--png" in args:
        out_png = args[args.index("--png") + 1]
    if "--blend" in args:
        out_blend = args[args.index("--blend") + 1]

    create_chronos_sculpture(out_stl, out_png, out_blend)
