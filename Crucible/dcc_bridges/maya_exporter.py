"""
Crucible — Maya Companion Exporter.

Runs INSIDE Maya (Script Editor, Python tab or shelf button).
Exports camera animation, all lights, render settings, and AOV/render
layer configuration to the Crucible Universal JSON format.

INSTALL
-------
1. Open Maya → Script Editor → Python tab.
2. Paste the contents of this file.
3. Run it, or drag-select-all and Middle-Mouse-Drag to your shelf.
4. In Nuke, use Crucible → Pass Manager → Import DCC Scene.

Supported renderers: Arnold (aiStandard lights), V-Ray, Redshift, Maya stdSurf.
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om
import json
import math
import os


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_world_matrix(node, frame):
    """Get world-space translation and rotation for a Maya node at a frame."""
    cmds.currentTime(frame, update=True)
    mat = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    # mat is a flat 16-element list in row-major order
    m = om.MMatrix(mat)
    t = om.MTransformationMatrix(m)
    tx, ty, tz = t.translation(om.MSpace.kWorld)
    euler = t.rotation(asQuaternion=False)
    rx = math.degrees(euler.x)
    ry = math.degrees(euler.y)
    rz = math.degrees(euler.z)
    sx, sy, sz = t.scale(om.MSpace.kObject)
    return (
        [tx, ty, tz],
        [rx, ry, rz],
        [sx, sy, sz],
    )


def _get_attr_safe(node, attr, default=None):
    """Query a Maya attribute safely."""
    full = f"{node}.{attr}"
    try:
        if cmds.objExists(full):
            return cmds.getAttr(full)
    except Exception:
        pass
    return default


def _light_intensity_attr(node, engine):
    """Return the best intensity attribute name for a given renderer."""
    if engine == "Arnold":
        for a in ("aiExposure", "intensity"):
            if cmds.objExists(f"{node}.{a}"):
                return a
    elif engine == "V-Ray":
        for a in ("intensityMult", "intensity"):
            if cmds.objExists(f"{node}.{a}"):
                return a
    elif engine == "Redshift":
        for a in ("multiplier", "intensity"):
            if cmds.objExists(f"{node}.{a}"):
                return a
    return "intensity"


def _light_color_attr(node, engine):
    """Return the best color attribute name for a given renderer."""
    if engine == "V-Ray":
        for a in ("lightColor", "color"):
            if cmds.objExists(f"{node}.{a}"):
                return a
    return "color"


def _maya_engine() -> str:
    """Detect current renderer name."""
    rend = cmds.getAttr("defaultRenderGlobals.currentRenderer") or "arnold"
    mapping = {
        "arnold":  "Arnold",
        "vray":    "V-Ray",
        "redshift":"Redshift",
        "renderman":"RenderMan",
    }
    return mapping.get(rend.lower(), rend.title())


def _collect_maya_aovs(engine: str):
    """Collect enabled AOV names for the current renderer."""
    aovs = []
    if engine == "Arnold":
        aov_nodes = cmds.ls(type="aiAOV") or []
        for n in aov_nodes:
            if _get_attr_safe(n, "enabled", True):
                name = _get_attr_safe(n, "name", "")
                if name:
                    aovs.append(name)
    elif engine == "V-Ray":
        vray_aov_nodes = cmds.ls(type="VRayRenderElement") or []
        for n in vray_aov_nodes:
            en = _get_attr_safe(n, "enabled", True)
            if en:
                aovs.append(n)
    elif engine == "Redshift":
        rs_nodes = cmds.ls(type="RedshiftOptions") or []
        # Redshift AOVs are queried through a different mechanism
        aovs = ["beauty"]  # Minimal fallback

    return aovs


def _collect_render_layers():
    """List all render layers and whether they are active."""
    layers = cmds.ls(type="renderLayer") or []
    result = []
    for lyr in layers:
        is_active = cmds.getAttr(f"{lyr}.renderable")
        result.append({"name": lyr, "active": bool(is_active)})
    return result


def _collect_lights(engine, frame_start, frame_end):
    """Collect all lights with per-frame animation data."""
    light_types = [
        "pointLight", "spotLight", "directionalLight", "areaLight",
        "aiAreaLight", "aiSkyDomeLight", "aiPhotometricLight",
        "VRayLight", "VRayLightDome", "VRaySun",
        "RedshiftDomeLight", "RedshiftPhysicalLight",
        "RedshiftPortalLight",
    ]

    lights_data = []
    all_lights = []
    for lt in light_types:
        all_lights.extend(cmds.ls(type=lt) or [])

    prev_frame = cmds.currentTime(query=True)

    for light in all_lights:
        # Get transform node
        transforms = cmds.listRelatives(light, parent=True, fullPath=True) or []
        if not transforms:
            continue
        transform = transforms[0]

        int_attr   = _light_intensity_attr(light, engine)
        color_attr = _light_color_attr(light, engine)

        frames_data = []
        for f in range(frame_start, frame_end + 1):
            cmds.currentTime(f, update=True)
            translate, rotate, scale = _get_world_matrix(transform, f)
            intensity = _get_attr_safe(light, int_attr, 1.0)
            raw_color = _get_attr_safe(light, color_attr, None)
            if isinstance(raw_color, list) and len(raw_color) > 0:
                color = list(raw_color[0]) if isinstance(raw_color[0], (list, tuple)) else raw_color
            else:
                color = [1.0, 1.0, 1.0]

            frames_data.append({
                "frame":     f,
                "translate": translate,
                "rotate":    rotate,
                "energy":    intensity,
                "color":     color[:3] if len(color) >= 3 else color,
            })

        lights_data.append({
            "name":   cmds.ls(transform, shortNames=True)[0],
            "type":   cmds.nodeType(light),
            "params": {
                "light_type": cmds.nodeType(light).lower(),
                "exposure":   _get_attr_safe(light, "aiExposure", 0.0),
                "cone_angle": _get_attr_safe(light, "coneAngle", None),
            },
            "frames": frames_data,
        })

    cmds.currentTime(prev_frame, update=True)
    return lights_data


def _collect_camera(cam_transform, frame_start, frame_end):
    """Collect camera animation data."""
    cam_shapes = cmds.listRelatives(cam_transform, shapes=True, type="camera") or []
    if not cam_shapes:
        return None

    cam_shape   = cam_shapes[0]
    frames_data = []
    prev_frame  = cmds.currentTime(query=True)

    for f in range(frame_start, frame_end + 1):
        cmds.currentTime(f, update=True)
        translate, rotate, scale = _get_world_matrix(cam_transform, f)

        focal    = _get_attr_safe(cam_shape, "focalLength",   35.0)
        hapt     = _get_attr_safe(cam_shape, "horizontalFilmAperture", 0.935)
        vapt     = _get_attr_safe(cam_shape, "verticalFilmAperture",   0.526)
        near_c   = _get_attr_safe(cam_shape, "nearClipPlane",  0.1)
        far_c    = _get_attr_safe(cam_shape, "farClipPlane",   10000.0)
        focus_d  = _get_attr_safe(cam_shape, "focusDistance",  100.0)
        fstop    = _get_attr_safe(cam_shape, "fStop",          8.0)

        # Convert Maya film aperture (inches) → mm
        hapt_mm = (hapt or 0.935) * 25.4
        vapt_mm = (vapt or 0.526) * 25.4

        frames_data.append({
            "frame":           f,
            "translate":       translate,
            "rotate":          rotate,
            "scale":           scale,
            "focal_length_mm": focal,
            "haperture_mm":    hapt_mm,
            "vaperture_mm":    vapt_mm,
            "near_clip":       near_c,
            "far_clip":        far_c,
            "focus_distance":  focus_d,
            "fstop":           fstop,
            "lens_distortion": {"k1": 0.0, "k2": 0.0, "k3": 0.0,
                                "p1": 0.0, "p2": 0.0},
        })

    cmds.currentTime(prev_frame, update=True)
    return frames_data


# ---------------------------------------------------------------------------
# Main Export
# ---------------------------------------------------------------------------

def export_crucible_scene(filepath: str = None) -> dict:
    """Build and write the full Crucible scene JSON from Maya.

    Args:
        filepath: Output path.  If None, opens a Maya file-save dialog.

    Returns:
        The exported dict.
    """
    if filepath is None:
        result = cmds.fileDialog2(
            fileFilter="JSON Files (*.json)",
            dialogStyle=2,
            fileMode=0,
            caption="Save Crucible Scene Export",
        )
        if not result:
            cmds.warning("[Crucible] Export cancelled.")
            return {}
        filepath = result[0]

    engine = _maya_engine()

    frame_start = int(cmds.playbackOptions(query=True, minTime=True))
    frame_end   = int(cmds.playbackOptions(query=True, maxTime=True))
    fps_str     = cmds.currentUnit(query=True, time=True)  # e.g. "film" = 24
    fps_map     = {
        "game": 15.0, "film": 24.0, "pal": 25.0, "ntsc": 30.0,
        "show": 48.0, "palf": 50.0, "ntscf": 60.0,
    }
    fps = fps_map.get(fps_str, 24.0)

    res_x = int(cmds.getAttr("defaultResolution.width"))
    res_y = int(cmds.getAttr("defaultResolution.height"))

    # Camera — use first renderable camera
    all_cams = cmds.ls(cameras=True) or []
    render_cam = None
    for c in all_cams:
        parents = cmds.listRelatives(c, parent=True) or []
        if parents and cmds.getAttr(f"{c}.renderable"):
            render_cam = parents[0]
            break

    cam_frames = _collect_camera(render_cam, frame_start, frame_end) if render_cam else []

    payload = {
        "crucible_schema_version": "1.0",
        "source_dcc":              "maya",
        "source_renderer":         engine,
        "shot": {
            "frame_start": frame_start,
            "frame_end":   frame_end,
            "fps":         fps,
        },
        "render_settings": {
            "resolution_x": res_x,
            "resolution_y": res_y,
            "fps":          fps,
            "color_space":  "ACEScg",
            "renderer":     engine,
        },
        "camera": {
            "name":   render_cam or "unknown",
            "frames": cam_frames,
        },
        "lights":         _collect_lights(engine, frame_start, frame_end),
        "passes":         _collect_maya_aovs(engine),
        "render_layers":  _collect_render_layers(),
    }

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=4)

    n_lights = len(payload["lights"])
    n_passes = len(payload["passes"])
    cmds.confirmDialog(
        title="Crucible Export",
        message=(
            f"Scene exported successfully!\n\n"
            f"Lights: {n_lights}   Passes: {n_passes}\n"
            f"Camera: {render_cam or 'none'}\n\n"
            f"Saved to:\n{filepath}"
        ),
        button=["OK"],
    )
    return payload


# Run immediately when pasted into Maya Script Editor
export_crucible_scene()
