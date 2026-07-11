"""
Crucible — Houdini Companion Exporter.

Runs INSIDE Houdini (Python shell, shelf tool, or HDA callback).
Exports camera animation, all lights (including Karma/Solaris USD lights),
Karma AOV configuration, and render settings to Crucible Universal JSON.

INSTALL (Shelf Tool)
--------------------
1. In Houdini, create a new Shelf → New Tool.
2. Name it "Crucible Export Scene".
3. In the Script tab, paste this entire file.
4. Click Accept.  The tool button will appear on the shelf.
5. Click it to export.  In Nuke, use Crucible → Pass Manager → Import DCC Scene.

Supported: Mantra, Karma CPU, Karma XPU (USD lights via Solaris).
"""

import hou
import json
import math
import os


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xform_to_trs(xform_matrix):
    """Decompose a hou.Matrix4 to translate / rotate / scale (degrees)."""
    t = hou.Vector3(xform_matrix.extractTranslates())
    r = xform_matrix.extractRotates()     # degrees in Houdini
    s = xform_matrix.extractScales()
    return list(t), list(r), list(s)


def _karma_aovs(rop_node):
    """Extract Karma AOV names from a Karma/LOP ROP."""
    aovs = []
    try:
        # Karma stores AOVs via USD opinions — check aov parms directly
        num = rop_node.evalParm("vm_numaux") or 0
        for i in range(1, num + 1):
            vex_var = rop_node.evalParm(f"vm_variable_plane{i}") or ""
            channel = rop_node.evalParm(f"vm_channel_plane{i}") or vex_var
            if channel:
                aovs.append(channel.lower())
    except Exception:
        pass
    return aovs


def _mantra_aovs(rop_node):
    """Extract Mantra (ifd) extra image planes."""
    aovs = ["beauty"]
    try:
        num = rop_node.evalParm("vm_numaux") or 0
        for i in range(1, num + 1):
            vex_var = rop_node.evalParm(f"vm_variable_plane{i}") or ""
            channel = rop_node.evalParm(f"vm_channel_plane{i}") or vex_var
            if channel:
                aovs.append(channel.lower())
    except Exception:
        pass
    return aovs


def _collect_rop() -> tuple:
    """Find the best active ROP and detect its renderer."""
    # Priority: karma_usd → ifd → karmarenderer
    for rop_type in ("karma", "karma_usd", "ifd", "ris", "geometry"):
        rops = hou.nodeType(hou.sopNodeTypeCategory(), rop_type)
        if rops is None:
            all_rops = [n for n in hou.node("/out").children()
                        if rop_type in n.type().name().lower()]
        else:
            all_rops = []

        # Broader search
        out = hou.node("/out")
        if out:
            all_rops = [n for n in out.children()
                        if rop_type in n.type().name().lower()]
        if all_rops:
            return all_rops[0], rop_type

    # Fallback: return first child of /out
    out = hou.node("/out")
    if out and out.children():
        n = out.children()[0]
        return n, n.type().name().lower()

    return None, "unknown"


def _collect_lights(frame_start: int, frame_end: int) -> list:
    """Walk entire node tree and collect light data per frame."""
    lights_data = []
    root = hou.node("/")
    if root is None:
        return lights_data

    all_nodes = root.allSubChildren()
    light_type_keywords = ("light", "env", "sun", "distant", "spot", "dome")

    prev_frame = hou.frame()

    for node in all_nodes:
        nt = node.type().name().lower()
        if not any(kw in nt for kw in light_type_keywords):
            continue

        frames_data = []
        for f in range(frame_start, frame_end + 1):
            hou.setFrame(f)

            # World position
            try:
                wm = node.worldTransform()
                translate, rotate, scale = _xform_to_trs(wm)
            except Exception:
                translate = rotate = scale = [0.0, 0.0, 0.0]

            # Intensity
            intensity = 1.0
            for exp_name in ("exposure", "ar_exposure",
                             "xn__inputsexposure_v3a", "inputs:exposure"):
                p = node.parm(exp_name)
                if p is not None:
                    intensity = p.eval()
                    break
            else:
                # Try to find any 'intensity' or 'power' parm
                for p in node.parms():
                    pn = p.name().lower()
                    if pn in ("intensity", "light_intensity", "power", "strength"):
                        intensity = p.eval()
                        break

            # Color
            color = [1.0, 1.0, 1.0]
            for col_name in ("color", "light_color", "ar_color",
                             "xn__inputscolor_v3a", "inputs:color"):
                pt = node.parmTuple(col_name)
                if pt is not None and len(pt) >= 3:
                    try:
                        color = list(pt.eval()[:3])
                    except Exception:
                        pass
                    break

            frames_data.append({
                "frame":     f,
                "translate": translate,
                "rotate":    rotate,
                "energy":    intensity,
                "color":     color,
            })

        lights_data.append({
            "name":   node.name(),
            "type":   node.type().name(),
            "params": {
                "light_type":    node.type().name().lower(),
                "primpattern":   (node.parm("primpattern").eval()
                                  if node.parm("primpattern") else None),
            },
            "frames": frames_data,
        })

    hou.setFrame(prev_frame)
    return lights_data


def _collect_camera(frame_start: int, frame_end: int) -> dict:
    """Find the render camera and collect per-frame data."""
    # Look in /obj for camera nodes
    obj = hou.node("/obj")
    cam_node = None
    if obj:
        for child in obj.children():
            if child.type().name() == "cam":
                cam_node = child
                break

    if cam_node is None:
        return {"name": "unknown", "frames": []}

    frames_data = []
    prev_frame  = hou.frame()

    for f in range(frame_start, frame_end + 1):
        hou.setFrame(f)

        wm = cam_node.worldTransform()
        translate, rotate, scale = _xform_to_trs(wm)

        focal    = cam_node.evalParm("focal")    or 35.0
        aperture = cam_node.evalParm("aperture") or 41.4213
        near     = cam_node.evalParm("near")     or 0.1
        far      = cam_node.evalParm("far")      or 10000.0

        # Houdini aperture is horizontal in mm
        # Compute vertical from resolution
        res_x = cam_node.evalParm("resx") or 1920
        res_y = cam_node.evalParm("resy") or 1080
        aspect = max(res_x, 1) / max(res_y, 1)
        vaperture = aperture / aspect

        frames_data.append({
            "frame":           f,
            "translate":       translate,
            "rotate":          rotate,
            "scale":           scale,
            "focal_length_mm": focal,
            "haperture_mm":    aperture,
            "vaperture_mm":    vaperture,
            "near_clip":       near,
            "far_clip":        far,
            "focus_distance":  cam_node.evalParm("focus") or 100.0,
            "fstop":           cam_node.evalParm("fstop") or 5.6,
            "lens_distortion": {"k1": 0.0, "k2": 0.0, "k3": 0.0,
                                "p1": 0.0, "p2": 0.0},
        })

    hou.setFrame(prev_frame)
    return {"name": cam_node.name(), "frames": frames_data}


# ---------------------------------------------------------------------------
# Main Export
# ---------------------------------------------------------------------------

def export_crucible_scene(filepath: str = None) -> dict:
    """Build and write the Crucible scene JSON from Houdini.

    Args:
        filepath: Output JSON path.  If None, prompts via Houdini dialog.

    Returns:
        The exported dict.
    """
    if filepath is None:
        filepath = hou.ui.selectFile(
            title="Save Crucible Scene Export",
            pattern="*.json",
            chooser_mode=hou.fileChooserMode.Write,
        )
        if not filepath:
            hou.ui.displayMessage("[Crucible] Export cancelled.")
            return {}
        filepath = hou.expandString(filepath)

    fps         = hou.fps()
    frame_start = int(hou.playbackRange()[0])
    frame_end   = int(hou.playbackRange()[1])

    rop_node, renderer_type = _collect_rop()

    renderer = "karma"
    if "ifd" in renderer_type:
        renderer = "mantra"
    elif "ris" in renderer_type:
        renderer = "renderman"

    aovs = []
    if rop_node:
        if renderer == "karma":
            aovs = _karma_aovs(rop_node)
        elif renderer == "mantra":
            aovs = _mantra_aovs(rop_node)

    # Resolution
    res_x, res_y = 1920, 1080
    if rop_node:
        try:
            res_x = rop_node.evalParm("vm_image_filesx") or 1920
            res_y = rop_node.evalParm("vm_image_filesy") or 1080
        except Exception:
            pass

    camera = _collect_camera(frame_start, frame_end)
    lights = _collect_lights(frame_start, frame_end)

    payload = {
        "crucible_schema_version": "1.0",
        "source_dcc":              "houdini",
        "source_renderer":         renderer,
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
            "renderer":     renderer,
        },
        "camera": camera,
        "lights": lights,
        "passes": aovs,
    }

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=4)

    n_lights = len(lights)
    n_passes = len(aovs)
    hou.ui.displayMessage(
        f"[Crucible] Scene exported!\n\n"
        f"Lights: {n_lights}   AOVs: {n_passes}\n"
        f"Camera: {camera.get('name', 'none')}\n\n"
        f"Saved:\n{filepath}",
        title="Crucible Export",
    )
    return payload


# Run immediately when used as a Houdini Shelf Tool script
export_crucible_scene()
