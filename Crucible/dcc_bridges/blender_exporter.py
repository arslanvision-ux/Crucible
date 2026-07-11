"""
Crucible — Blender Companion Exporter.

Runs INSIDE Blender (Scripting workspace or add-on).
Exports camera animation, all lights, render settings, and pass configuration
to the Crucible Universal JSON format for import into Nuke.

INSTALL
-------
1. Open Blender → Scripting workspace.
2. Open this file (or paste it into a new script).
3. Click "Run Script".
4. A file-save dialog will appear — choose an output path.
5. In Nuke, use Crucible → Pass Manager → Import DCC Scene.

Supported renderers: Cycles, EEVEE, EEVEE-Next.
"""

import bpy
import json
import math
import os
from bpy_extras.io_utils import ExportHelper
from bpy.types import Operator
from bpy.props import StringProperty


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mat4_to_trs(matrix):
    """Decompose a Blender 4×4 matrix to translate / rotate / scale."""
    import mathutils
    import math
    axis_conversion = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X')
    nuke_matrix = axis_conversion @ matrix
    loc, rot, scale = nuke_matrix.decompose()
    # Blender uses radians; Crucible stores degrees
    rot_euler = rot.to_euler("ZXY")
    return (
        list(loc),
        [math.degrees(rot_euler.x),
         math.degrees(rot_euler.y),
         math.degrees(rot_euler.z)],
        list(scale),
    )


def _blender_passes(scene):
    """Collect all enabled render passes for the active view layer."""
    vl = scene.view_layers.active
    if vl is None:
        return []

    passes = []
    pass_attrs = {
        "use_pass_diffuse_direct":    "diffuse_direct",
        "use_pass_diffuse_indirect":  "diffuse_indirect",
        "use_pass_diffuse_color":     "diffuse_albedo",
        "use_pass_glossy_direct":     "specular_direct",
        "use_pass_glossy_indirect":   "specular_indirect",
        "use_pass_glossy_color":      "specular_albedo",
        "use_pass_transmission_direct":  "transmission_direct",
        "use_pass_transmission_indirect":"transmission_indirect",
        "use_pass_emit":              "emission",
        "use_pass_shadow":            "shadow",
        "use_pass_ambient_occlusion": "ambient_occlusion",
        "use_pass_normal":            "normal",
        "use_pass_z":                 "depth",
        "use_pass_vector":            "motion",
        "use_pass_uv":                "uv",
        "use_pass_object_index":      "object_id",
        "use_pass_material_index":    "material_id",
        "use_pass_combined":          "beauty",
    }

    for attr, crucible_name in pass_attrs.items():
        if getattr(vl, attr, False):
            passes.append(crucible_name)

    return passes


def _collect_lights(scene, frame_start, frame_end):
    """Collect all light objects with per-frame animation."""
    lights = []
    fps = scene.render.fps

    for obj in scene.objects:
        if obj.type != "LIGHT":
            continue

        light_data = obj.data
        light_type = light_data.type.lower()  # "point", "sun", "spot", "area"

        frames_data = []
        prev_frame = scene.frame_current

        for f in range(frame_start, frame_end + 1):
            scene.frame_set(f)
            translate, rotate, scale = _mat4_to_trs(obj.matrix_world)

            # Energy — handle Cycles node tree or simple energy
            energy = light_data.energy
            color  = list(light_data.color)

            if (scene.render.engine == "CYCLES"
                    and light_data.use_nodes
                    and light_data.node_tree):
                for node in light_data.node_tree.nodes:
                    if node.type == "EMISSION":
                        energy = node.inputs["Strength"].default_value
                        raw_c  = node.inputs["Color"].default_value
                        color  = [raw_c[0], raw_c[1], raw_c[2]]
                        break

            frames_data.append({
                "frame":     f,
                "translate": translate,
                "rotate":    rotate,
                "energy":    energy,
                "color":     color,
            })

        scene.frame_set(prev_frame)

        # Light-specific params
        params = {
            "light_type": light_type,
            "radius":     getattr(light_data, "shadow_soft_size", 0.0),
        }
        if light_type == "spot":
            params["spot_size"]  = math.degrees(light_data.spot_size)
            params["spot_blend"] = light_data.spot_blend
        if light_type == "area":
            params["shape"]  = light_data.shape.lower()
            params["size"]   = light_data.size
            params["size_y"] = getattr(light_data, "size_y", light_data.size)

        lights.append({
            "name":   obj.name,
            "type":   light_type,
            "params": params,
            "frames": frames_data,
        })

    return lights


def _collect_camera(scene, cam_obj, frame_start, frame_end):
    """Collect camera animation for Crucible Universal Camera schema."""
    if cam_obj is None or cam_obj.type != "CAMERA":
        return None

    cam_data  = cam_obj.data
    frames    = []
    prev_frame = scene.frame_current

    for f in range(frame_start, frame_end + 1):
        scene.frame_set(f)
        translate, rotate, scale = _mat4_to_trs(cam_obj.matrix_world)

        # Focal length in mm
        focal_mm = cam_data.lens

        # Sensor (aperture) in mm
        if cam_data.sensor_fit in ("HORIZONTAL", "AUTO"):
            haperture = cam_data.sensor_width
            render    = scene.render
            aspect    = render.resolution_x / max(render.resolution_y, 1)
            vaperture = haperture / max(aspect, 0.0001)
        else:
            vaperture = cam_data.sensor_height
            render    = scene.render
            aspect    = render.resolution_x / max(render.resolution_y, 1)
            haperture = vaperture * aspect

        frames.append({
            "frame":           f,
            "translate":       translate,
            "rotate":          rotate,
            "scale":           scale,
            "focal_length_mm": focal_mm,
            "haperture_mm":    haperture,
            "vaperture_mm":    vaperture,
            "near_clip":       cam_data.clip_start,
            "far_clip":        cam_data.clip_end,
            "focus_distance":  cam_data.dof.focus_distance,
            "fstop":           cam_data.dof.aperture_fstop,
            "lens_distortion": {
                "k1": 0.0, "k2": 0.0, "k3": 0.0,
                "p1": 0.0, "p2": 0.0,
            },
        })

    scene.frame_set(prev_frame)
    return frames


# ---------------------------------------------------------------------------
# Main Export
# ---------------------------------------------------------------------------

def export_crucible_scene(filepath: str) -> dict:
    """Build and write the full Crucible scene JSON.

    Args:
        filepath: Destination path for the JSON file.

    Returns:
        The exported dict.
    """
    scene      = bpy.context.scene
    render     = scene.render
    frame_start = scene.frame_start
    frame_end   = scene.frame_end

    # Render engine string → crucible label
    engine_map = {
        "CYCLES":       "cycles",
        "BLENDER_EEVEE":      "eevee",
        "BLENDER_EEVEE_NEXT": "eevee",
    }
    engine = engine_map.get(render.engine, render.engine.lower())

    # Color space
    cs = "linear_srgb"
    try:
        cs = scene.sequencer_colorspace_settings.name
    except Exception:
        pass

    cam_obj = scene.camera
    cam_frames = _collect_camera(scene, cam_obj, frame_start, frame_end)

    payload = {
        "crucible_schema_version": "1.0",
        "source_dcc":              "blender",
        "source_renderer":         engine,
        "shot": {
            "frame_start":  int(frame_start),
            "frame_end":    int(frame_end),
            "fps":          render.fps / render.fps_base,
        },
        "render_settings": {
            "resolution_x":    render.resolution_x,
            "resolution_y":    render.resolution_y,
            "fps":             render.fps / render.fps_base,
            "color_space":     cs,
            "renderer":        engine,
            "samples":         getattr(scene.cycles, "samples", None),
            "denoise":         getattr(getattr(scene, "cycles", None), "use_denoising", False),
        },
        "camera": {
            "name":   cam_obj.name if cam_obj else "unknown",
            "frames": cam_frames or [],
        },
        "lights": _collect_lights(scene, frame_start, frame_end),
        "passes": _blender_passes(scene),
    }

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=4)

    return payload


# ---------------------------------------------------------------------------
# Blender Operator
# ---------------------------------------------------------------------------

class CRUCIBLE_OT_export_scene(Operator, ExportHelper):
    """Export Crucible Universal Scene JSON."""
    bl_idname      = "crucible.export_scene"
    bl_label       = "Export Crucible Scene"
    filename_ext   = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            data   = export_crucible_scene(self.filepath)
            n_lights = len(data.get("lights", []))
            n_passes = len(data.get("passes", []))
            self.report(
                {"INFO"},
                f"[Crucible] Exported: {n_lights} lights, {n_passes} passes → {self.filepath}"
            )
        except Exception as exc:
            self.report({"ERROR"}, f"[Crucible] Export failed: {exc}")
        return {"FINISHED"}


def register():
    bpy.utils.register_class(CRUCIBLE_OT_export_scene)


def unregister():
    bpy.utils.unregister_class(CRUCIBLE_OT_export_scene)


if __name__ == "__main__":
    register()
    bpy.ops.crucible.export_scene("INVOKE_DEFAULT")
