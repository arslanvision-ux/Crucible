"""
Crucible — Universal Camera Exchange.

Defines the Crucible Universal Camera JSON schema and provides utilities
to import camera data exported from any DCC into Nuke Camera nodes.

Schema (version 1.0)
--------------------
{
    "crucible_schema_version": "1.0",
    "source_dcc": "maya | houdini | blender",
    "source_renderer": "arnold | karma | cycles | ...",
    "shot": { "frame_start": 1001, "frame_end": 1100, "fps": 24.0 },
    "camera": {
        "name": "renderCam",
        "frames": [
            {
                "frame":          1001,
                "translate":      [tx, ty, tz],
                "rotate":         [rx, ry, rz],   // degrees XYZ
                "scale":          [sx, sy, sz],
                "focal_length_mm":   35.0,
                "haperture_mm":      23.76,
                "vaperture_mm":      13.365,
                "near_clip":         0.1,
                "far_clip":          100000.0,
                "focus_distance":    100.0,
                "fstop":             8.0,
                "lens_distortion": { "k1": 0.0, "k2": 0.0, "k3": 0.0,
                                     "p1": 0.0, "p2": 0.0 }
            }
        ]
    }
}
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Schema Version
# ---------------------------------------------------------------------------

CAMERA_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Nuke Camera Import
# ---------------------------------------------------------------------------

def import_camera_from_json(file_path: str) -> Optional[object]:
    """Import a Crucible Universal Camera JSON into Nuke.

    Creates a fully animated Camera2 node in the current Nuke script.

    Args:
        file_path: Path to the Crucible camera JSON file.

    Returns:
        The created Nuke Camera2 node, or None on failure.

    Raises:
        FileNotFoundError: If file_path does not exist.
        ValueError:        If the JSON is malformed or schema version mismatch.
    """
    import nuke  # noqa: PLC0415

    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"[Crucible] Camera JSON not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    schema_ver = data.get("crucible_schema_version", "unknown")
    if schema_ver not in (CAMERA_SCHEMA_VERSION, "unknown"):
        nuke.message(
            f"[Crucible] Camera JSON schema version '{schema_ver}' may be "
            f"incompatible with this version of Crucible (expects {CAMERA_SCHEMA_VERSION})."
        )

    cam_data  = data.get("camera", {})
    frames    = cam_data.get("frames", [])
    shot_data = data.get("shot", {})
    dcc_src   = data.get("source_dcc", "unknown")
    cam_name  = cam_data.get("name", "crucible_camera")

    if not frames:
        nuke.message("[Crucible] Camera JSON contains no frame data.")
        return None

    with nuke.Undo("Crucible: Import Camera"):
        cam = nuke.nodes.Camera2(name=f"crucible_{cam_name}")
        cam["label"].setValue(f"[Crucible] from {dcc_src.title()}")

        # Shot-level metadata
        fps = float(shot_data.get("fps", nuke.root()["fps"].value()))
        frame_start = shot_data.get("frame_start")
        frame_end   = shot_data.get("frame_end")
        if frame_start and frame_end:
            cam["label"].setValue(
                f"[Crucible] {dcc_src.title()}  |  "
                f"{frame_start}-{frame_end} @ {fps}fps"
            )

        # Enable animation on relevant knobs
        anim_knobs = [
            "translate", "rotate", "focal", "haperture", "vaperture",
            "near", "far", "focaldist", "fstop",
        ]
        for knob_name in anim_knobs:
            knob = cam.knob(knob_name)
            if knob:
                try:
                    knob.setAnimated()
                except Exception:
                    pass

        # Per-frame keyframes
        for frame_rec in frames:
            frame = float(frame_rec.get("frame", 0))

            tx, ty, tz = frame_rec.get("translate", [0, 0, 0])
            rx, ry, rz = frame_rec.get("rotate",    [0, 0, 0])

            _set_key(cam, "translate", frame, [tx, ty, tz])
            _set_key(cam, "rotate",    frame, [rx, ry, rz])

            focal = frame_rec.get("focal_length_mm")
            if focal is not None:
                _set_key(cam, "focal", frame, float(focal))

            haperture = frame_rec.get("haperture_mm")
            if haperture is not None:
                _set_key(cam, "haperture", frame, float(haperture))

            vaperture = frame_rec.get("vaperture_mm")
            if vaperture is not None:
                _set_key(cam, "vaperture", frame, float(vaperture))

            near = frame_rec.get("near_clip")
            if near is not None:
                _set_key(cam, "near", frame, float(near))

            far = frame_rec.get("far_clip")
            if far is not None:
                _set_key(cam, "far", frame, float(far))

            focus_dist = frame_rec.get("focus_distance")
            if focus_dist is not None:
                _set_key(cam, "focaldist", frame, float(focus_dist))

            fstop = frame_rec.get("fstop")
            if fstop is not None:
                _set_key(cam, "fstop", frame, float(fstop))

        # Lens distortion — stored on a user tab for reference
        if frames:
            first = frames[0]
            ld = first.get("lens_distortion", {})
            if any(v != 0.0 for v in ld.values()):
                _add_lens_distortion_knobs(cam, ld)

    nuke.message(
        f"[Crucible] Camera '{cam_name}' imported from {dcc_src.title()}.\n"
        f"{len(frames)} keyframes set."
    )
    return cam


# ---------------------------------------------------------------------------
# Scene / Light Import (Universal Light JSON)
# ---------------------------------------------------------------------------

def import_scene_from_json(file_path: str) -> dict:
    """Import Crucible Universal Scene JSON (lights, render settings, etc.).

    Does NOT create Nuke nodes directly — returns structured data so that
    the Light Mixer or other tools can consume it.

    Args:
        file_path: Path to Crucible scene JSON.

    Returns:
        dict with keys: 'lights', 'render_settings', 'source_dcc', 'shot'.

    Raises:
        FileNotFoundError: If file not found.
        ValueError:        If JSON is malformed.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"[Crucible] Scene JSON not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Diff Render Settings
# ---------------------------------------------------------------------------

def diff_render_settings(a_path: str, b_path: str) -> List[str]:
    """Compare render settings between two Crucible scene JSON files.

    Args:
        a_path: Path to scene JSON A.
        b_path: Path to scene JSON B.

    Returns:
        List of human-readable mismatch strings.  Empty list = identical.
    """
    a = import_scene_from_json(a_path)
    b = import_scene_from_json(b_path)

    mismatches: List[str] = []

    keys_to_check = [
        ("render_settings", "resolution_x"),
        ("render_settings", "resolution_y"),
        ("render_settings", "fps"),
        ("render_settings", "color_space"),
        ("render_settings", "renderer"),
        ("shot",            "frame_start"),
        ("shot",            "frame_end"),
    ]

    for section, key in keys_to_check:
        va = a.get(section, {}).get(key)
        vb = b.get(section, {}).get(key)
        if va != vb:
            mismatches.append(
                f"{section}.{key}: A={va!r}  ≠  B={vb!r}"
            )

    # DCC source difference
    if a.get("source_dcc") != b.get("source_dcc"):
        mismatches.append(
            f"source_dcc: A={a.get('source_dcc')!r}  ≠  B={b.get('source_dcc')!r}"
        )

    return mismatches


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_key(node, knob_name: str, frame: float, value: Any) -> None:
    """Set a keyframe on a Nuke knob (scalar or vector)."""
    try:
        knob = node[knob_name]
        if isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                knob.setValueAt(float(v), frame, i)
        else:
            knob.setValueAt(float(value), frame)
    except Exception as exc:
        print(f"[Crucible] Warning: could not set key on {knob_name}: {exc}")


def _add_lens_distortion_knobs(cam, ld: dict) -> None:
    """Add a 'Lens Distortion' user tab to the camera node with LD coefficients."""
    try:
        import nuke  # noqa: PLC0415
        tab = nuke.Tab_Knob("crucible_ld_tab", "Crucible Lens Distortion")
        cam.addKnob(tab)
        for name, val in ld.items():
            k = nuke.Double_Knob(f"ld_{name}", f"LD {name.upper()}")
            k.setValue(float(val))
            cam.addKnob(k)
    except Exception as exc:
        print(f"[Crucible] Warning: could not add LD knobs: {exc}")
