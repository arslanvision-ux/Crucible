"""
Crucible Live Bridge — Houdini Bidirectional Server  v2.0
=========================================================
Paste the entire contents of this file into a Houdini Shelf Tool script.

Architecture
------------
                ┌──────────────────────────────────────────┐
                │            HOUDINI                       │
                │  Server thread  ← Nuke  (port 7890)      │
                │   ↳ receives: light_state, request_camera,│
                │               request_scene, ping         │
                │                                          │
                │  Sender  ──────→ Nuke  (port 7893)       │
                │   ↳ pushes:  camera_frame, camera_sequence│
                │              scene_info, pong             │
                └──────────────────────────────────────────┘

When Nuke sends ``request_camera`` Houdini immediately pushes back the
active camera's current frame data (or a full sequence if frame_range
was provided).  Camera, light, and scene updates flow in real-time with
NO manual file export steps.

To STOP the server click the same shelf button again.
"""

import hou
import json
import math
import queue
import socket
import threading

# ── Module-level singletons ──────────────────────────────────────────────────
# To prevent multiple clicks of the shelf tool from creating ghost threads
# and ghost queues, we must store the state in hou.session.

if not hasattr(hou.session, "crucible_bridge_queue"):
    hou.session.crucible_bridge_queue = queue.Queue()
if not hasattr(hou.session, "crucible_bridge_running"):
    hou.session.crucible_bridge_running = False
if not hasattr(hou.session, "crucible_bridge_socket"):
    hou.session.crucible_bridge_socket = None
if not hasattr(hou.session, "crucible_bridge_last_hash"):
    hou.session.crucible_bridge_last_hash = None
if not hasattr(hou.session, "crucible_bridge_last_push"):
    hou.session.crucible_bridge_last_push = 0.0
if not hasattr(hou.session, "crucible_is_updating"):
    hou.session.crucible_is_updating = False
if not hasattr(hou.session, "crucible_original_states"):
    hou.session.crucible_original_states = {}

_LISTEN_PORT    = 7890              # Houdini listens here (Nuke connects to this)
_NUKE_HOST      = "127.0.0.1"       # Where to find Nuke's listener
_NUKE_PORT      = 7893              # Nuke's NukeLiveListener port


# ── Wire helpers ─────────────────────────────────────────────────────────────

def _recv_exactly(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed mid-message")
        buf += chunk
    return buf


def _send_to_nuke(data: dict):
    """Send a typed message to Nuke's listener.  Non-blocking fire-and-forget."""
    def _do_send():
        msg_type = data.get('type', '?')
        try:
            payload = json.dumps(data).encode("utf-8")
            print(f"[Crucible Bridge] → Connecting to Nuke at {_NUKE_HOST}:{_NUKE_PORT} (type={msg_type})")
            with socket.create_connection((_NUKE_HOST, _NUKE_PORT), timeout=5.0) as s:
                s.sendall(len(payload).to_bytes(4, "big") + payload)
            print(f"[Crucible Bridge] → Sent '{msg_type}' to Nuke successfully ({len(payload)} bytes)")
        except ConnectionRefusedError:
            print(
                f"[Crucible Bridge] FAILED '{msg_type}': Connection REFUSED at {_NUKE_HOST}:{_NUKE_PORT}.\n"
                f"  → Nuke's listener is NOT running. Enable it in Crucible Pass Manager → Live Pull → Listener: ON"
            )
        except TimeoutError:
            print(
                f"[Crucible Bridge] FAILED '{msg_type}': Connection TIMED OUT to {_NUKE_HOST}:{_NUKE_PORT}.\n"
                f"  → A firewall may be blocking TCP port {_NUKE_PORT}. Try disabling Windows Firewall temporarily."
            )
        except OSError as e:
            print(
                f"[Crucible Bridge] FAILED '{msg_type}': {e}\n"
                f"  → Check _NUKE_HOST='{_NUKE_HOST}' and _NUKE_PORT={_NUKE_PORT} are correct."
            )
    threading.Thread(target=_do_send, daemon=True, name="CrucibleSendToNuke").start()



# ── Camera Helpers ───────────────────────────────────────────────────────────

def _get_render_camera():
    """Find the first camera node in /stage or /obj."""
    # Try Solaris /stage first
    stage = hou.node("/stage")
    if stage:
        for child in stage.children():
            if child.type().name() == "camera":
                return child
    # Fallback to /obj
    obj = hou.node("/obj")
    if obj:
        for child in obj.children():
            if child.type().name() == "cam":
                return child
    return None


def _eval_safe(node, parm_name, default, time=None):
    try:
        p = node.parm(parm_name)
        if p is None:
            return default
        val = p.evalAtTime(time) if time is not None else p.eval()
        if val is None or val == "":
            return default
        return float(val)
    except Exception:
        return default

def _eval_tuple_safe(node, parm_name, default, time=None):
    try:
        pt = node.parmTuple(parm_name)
        if not pt:
            return default
        val = pt.evalAtTime(time) if time is not None else pt.eval()
        return tuple(float(v) for v in val)
    except Exception:
        return default

def _camera_at_frame(cam_node, frame: int) -> dict:
    """Return a camera_frame dict for *cam_node* at *frame*."""
    
    # Evaluate precisely at the requested frame's time to bypass Houdini UI caching
    t_val = hou.frameToTime(frame)
    
    if hasattr(cam_node, "worldTransformAtTime"):
        wm = cam_node.worldTransformAtTime(t_val)
        t  = hou.Vector3(wm.extractTranslates())
        r  = wm.extractRotates()      # degrees
        s  = wm.extractScales()
    else:
        # Solaris / Fallback
        t  = _eval_tuple_safe(cam_node, "t", (0.0, 0.0, 0.0), time=t_val)
        r  = _eval_tuple_safe(cam_node, "r", (0.0, 0.0, 0.0), time=t_val)
        s  = _eval_tuple_safe(cam_node, "s", (1.0, 1.0, 1.0), time=t_val)
        
    focal     = _eval_safe(cam_node, "focal", 35.0, time=t_val)
    aperture  = _eval_safe(cam_node, "aperture", 41.4213, time=t_val)
    near      = _eval_safe(cam_node, "near", 0.1, time=t_val)
    far       = _eval_safe(cam_node, "far", 10000.0, time=t_val)
    focus_d   = _eval_safe(cam_node, "focus", 100.0, time=t_val)
    fstop     = _eval_safe(cam_node, "fstop", 5.6, time=t_val)
    res_x     = int(_eval_safe(cam_node, "resx", 1920, time=t_val))
    res_y     = int(_eval_safe(cam_node, "resy", 1080, time=t_val))
    aspect    = max(res_x, 1) / max(res_y, 1)
    vaperture = aperture / max(aspect, 0.0001)

    return {
        "frame":           frame,
        "translate":       [t[0], t[1], t[2]],
        "rotate":          [r[0], r[1], r[2]],
        "scale":           [s[0], s[1], s[2]],
        "focal_length_mm": focal,
        "haperture_mm":    aperture,
        "vaperture_mm":    vaperture,
        "near_clip":       near,
        "far_clip":        far,
        "focus_distance":  focus_d,
        "fstop":           fstop,
        "lens_distortion": {"k1": 0.0, "k2": 0.0, "k3": 0.0,
                             "p1": 0.0, "p2": 0.0},
    }


def _handle_request_camera(msg: dict):
    """Respond to a request_camera message by pushing camera data to Nuke."""
    cam = _get_render_camera()
    if cam is None:
        _send_to_nuke({
            "type":    "error",
            "message": "No camera found in /obj."
        })
        return

    prev_frame = hou.frame()

    frame_start = msg.get("frame_start")
    frame_end   = msg.get("frame_end")

    if frame_start is not None and frame_end is not None:
        # Full sequence
        frames = []
        for f in range(int(frame_start), int(frame_end) + 1):
            frames.append(_camera_at_frame(cam, f))
        hou.setFrame(prev_frame)
        _send_to_nuke({
            "type":    "camera_sequence",
            "name":    cam.name(),
            "source_dcc": "houdini",
            "shot": {
                "frame_start": int(frame_start),
                "frame_end":   int(frame_end),
                "fps":         hou.fps(),
            },
            "frames": frames,
        })
    else:
        # Single current frame
        current = int(hou.frame())
        frame_data = _camera_at_frame(cam, current)
        hou.setFrame(prev_frame)
        _send_to_nuke({
            "type":       "camera_frame",
            "name":       cam.name(),
            "source_dcc": "houdini",
            **frame_data,
        })


def _handle_request_scene(msg: dict):
    """Respond to request_scene by pushing a scene_info snapshot to Nuke."""
    fps         = hou.fps()
    frame_range = hou.playbar.playbackRange()

    # Collect lights
    lights = []
    for node in hou.node("/").allSubChildren():
        nt = node.type().name().lower()
        if not any(kw in nt for kw in ("light", "env", "sun")):
            continue

        # Calculate relative multiplier vs original state
        orig_states = hou.session.crucible_original_states
        
        # Exposure -> Multiplier
        intensity = 1.0
        for pname in ("exposure", "ar_exposure", "xn__inputsexposure_v3a"):
            p = node.parm(pname)
            if p:
                current_exp = p.eval()
                path = p.path()
                orig_exp = orig_states.get(path, current_exp)
                intensity = 2.0 ** (current_exp - orig_exp)
                break

        color = [1.0, 1.0, 1.0]
        for cname in ("color", "inputs:color", "light_color", "ar_color", "xn__inputscolor_v3a"):
            pt = node.parmTuple(cname)
            if pt and len(pt) >= 3:
                try:
                    current_col = list(pt.eval()[:3])
                    path = f"{pt.node().path()}/{pt.name()}"
                    orig_col = orig_states.get(path, current_col)
                    color = [
                        current_col[0] / orig_col[0] if orig_col[0] > 0 else 1.0,
                        current_col[1] / orig_col[1] if orig_col[1] > 0 else 1.0,
                        current_col[2] / orig_col[2] if orig_col[2] > 0 else 1.0
                    ]
                except Exception:
                    pass
                break

        lights.append({
            "name":      node.name(),
            "type":      node.type().name(),
            "intensity": intensity,
            "color":     color,
        })

    _send_to_nuke({
        "type":       "scene_info",
        "source_dcc": "houdini",
        "shot": {
            "frame_start": int(frame_range[0]),
            "frame_end":   int(frame_range[1]),
            "fps":         fps,
        },
        "lights": lights,
        "passes": [],  # Could be expanded to pull from Karma ROP
    })


import hdefereval
from PySide2 import QtWidgets, QtCore, QtGui

# ── Globals & UI ──────────────────────────────────────────────────────────────
def log_message(msg):
    print(f"[Crucible] {msg}")
    if getattr(hou.session, 'crucible_ui_instance', None):
        hdefereval.executeDeferred(lambda: hou.session.crucible_ui_instance.append_log(msg))

def _apply_light_state(data: dict):
    """
    Parse the `lighting_multipliers` dict and apply exposure/color changes.
    """
    hou.session.crucible_is_updating = True

    multipliers = data.get("lighting_multipliers", data)
    meta = data.get("metadata", {})
    frame = meta.get("frame")
    
    if frame is not None:
        try:
            hou.setFrame(frame)
        except Exception:
            pass

    updated     = 0
    log         = []

    with hou.undos.group("Crucible LiveBridge"):
        for node in hou.node("/").allSubChildren():
            node_type = node.type().name().lower()
            if "light" not in node_type and "env" not in node_type:
                continue

            name = node.name().lower()
            matched_key = None
            for k in multipliers:
                clean_k = k.lower()
                for pfx in ("c_", "rgba_", "lightgroup_"):
                    if clean_k.startswith(pfx):
                        clean_k = clean_k[len(pfx):]
                        break
                if name == clean_k:
                    matched_key = k
                    break

            if matched_key is None:
                pp = node.parm("primpattern")
                if pp:
                    leaf = pp.eval().lower().split("/")[-1]
                    for k in multipliers:
                        clean_k = k.lower()
                        for pfx in ("c_", "rgba_", "lightgroup_"):
                            if clean_k.startswith(pfx):
                                clean_k = clean_k[len(pfx):]
                                break
                        if leaf == clean_k:
                            matched_key = k
                            break

            if matched_key is None:
                continue

            entry = multipliers[matched_key]
            mult  = entry.get("multiplier", 1.0) if isinstance(entry, dict) else float(entry)
            color = entry.get("color", [1.0, 1.0, 1.0]) if isinstance(entry, dict) else [1.0, 1.0, 1.0]
            is_animated = entry.get("is_animated", False) if isinstance(entry, dict) else False

            abs_mult   = abs(mult)
            color_sign = -1.0 if mult < 0 else 1.0

            # Exposure
            target_exp = None
            for en in ("exposure", "ar_exposure", "xn__inputsexposure_v3a",
                       "inputs:exposure", "xn__inputsexposure_control"):
                if node.parm(en) is not None:
                    target_exp = node.parm(en)
                    break
            if target_exp is None:
                for p in node.parms():
                    pn = p.name().lower()
                    if "exposure" in pn and "enable" not in pn and "control" not in pn:
                        target_exp = p
                        break

            if target_exp:
                try:
                    # Enable USD control parameter FIRST so the parameter is unlocked
                    exp_name = target_exp.name()
                    for ctrl_name in (exp_name + "_control", "enable_" + exp_name, "enable" + exp_name):
                        ctrl = node.parm(ctrl_name)
                        if ctrl:
                            try:
                                if isinstance(ctrl.eval(), str): ctrl.set("set")
                                else: ctrl.set(1)
                            except: pass

                    path = target_exp.path()
                    if path not in hou.session.crucible_original_states:
                        hou.session.crucible_original_states[path] = target_exp.eval()
                        
                    # If it was corrupted in cache, actively fix it
                    if hou.session.crucible_original_states[path] <= -99.0:
                        hou.session.crucible_original_states[path] = 0.0
                    
                    orig_exp = hou.session.crucible_original_states[path]
                    new_exp = orig_exp + math.log2(abs_mult) if abs_mult > 0 else -100.0
                    
                    # Set value first to trigger viewport cook and any auto-keying
                    target_exp.set(new_exp)
                    
                    if frame is not None and is_animated:
                        kf = hou.Keyframe()
                        kf.setFrame(frame)
                        kf.setValue(new_exp)
                        kf.setExpression("linear()", hou.exprLanguage.Hscript)
                        target_exp.setKeyframe(kf)
                        
                    if frame is not None and is_animated:
                        log.append(f"[{name}] exposure ({target_exp.name()}) → {new_exp:.2f} @ fr:{frame}")
                    else:
                        log.append(f"[{name}] exposure ({target_exp.name()}) → {new_exp:.2f}")
                    updated += 1
                except Exception:
                    pass

            # Color
            target_col = None
            for cn in ("lightcolor", "light_color", "color", "inputs:color", "ar_color", "xn__inputscolor_v3a"):
                pt = node.parmTuple(cn)
                if pt is not None and len(pt) >= 3:
                    target_col = pt
                    break
            if target_col is None:
                for pt in node.parmTuples():
                    tn = pt.name().lower()
                    if ("color" in tn and "shadow" not in tn and "guide" not in tn
                            and len(pt) >= 3 and "enable" not in tn
                            and "temperature" not in tn and "control" not in tn):
                        target_col = pt
                        break

            if target_col:
                try:
                    # Enable USD control parameter FIRST so the parameter is unlocked
                    col_name = target_col.name()
                    for ctrl_name in (col_name + "_control", "enable_" + col_name, "enable" + col_name):
                        ctrl = node.parm(ctrl_name)
                        if ctrl:
                            try:
                                if isinstance(ctrl.eval(), str): ctrl.set("set")
                                else: ctrl.set(1)
                            except: pass

                    path = f"{target_col.node().path()}/{target_col.name()}"
                    if path not in hou.session.crucible_original_states:
                        hou.session.crucible_original_states[path] = target_col.eval()[:3]
                        
                    orig_col = hou.session.crucible_original_states[path]
                    nc = (orig_col[0] * color[0] * color_sign,
                          orig_col[1] * color[1] * color_sign,
                          orig_col[2] * color[2] * color_sign)
                          
                    # Set value first to trigger viewport cook and any auto-keying
                    target_col.set(nc)
                    
                    if frame is not None and is_animated:
                        for i, v in enumerate(nc):
                            kf = hou.Keyframe()
                            kf.setFrame(frame)
                            kf.setValue(v)
                            kf.setExpression("linear()", hou.exprLanguage.Hscript)
                            target_col[i].setKeyframe(kf)
                            
                    if frame is not None and is_animated:
                        log.append(f"[{name}] color ({target_col.name()}) → {nc} @ fr:{frame}")
                    else:
                        log.append(f"[{name}] color ({target_col.name()}) → {nc}")
                except Exception as e:
                    log.append(f"[{name}] ERROR on color: {e}")
                    pass

    if log:
        if frame is not None:
            log_message(f"Keyed {updated} lights at frame {frame}:")
        else:
            log_message(f"Updated {updated} lights:")
        for msg in log:
            log_message(f"  {msg}")
        
    hou.session.crucible_is_updating = False
    import time
    hou.session.crucible_bridge_last_push = time.time() + 0.5


def _clear_keyframes(data: dict):
    light_name = data.get("light", "").lower()
    if not light_name:
        return
        
    updated = 0
    with hou.undos.group("Crucible Clear Keyframes"):
        for node in hou.node("/").allSubChildren():
            nt = node.type().name().lower()
            if not any(kw in nt for kw in ("light", "env", "sun")):
                continue
                
            name = node.name().lower()
            if name != light_name and not name.endswith(light_name):
                continue
                
            # Clear Exposure
            target_exp = None
            for en in ("inputs:exposure", "exposure", "ar_exposure", "xn__inputsexposure_v3a", "xn__inputsexposure_control"):
                if node.parm(en) is not None:
                    target_exp = node.parm(en)
                    break
            if target_exp is None:
                for p in node.parms():
                    pn = p.name().lower()
                    if "exposure" in pn and "enable" not in pn and "control" not in pn:
                        target_exp = p
                        break
                        
            if target_exp:
                try:
                    # Unlock first
                    exp_name = target_exp.name()
                    for ctrl_name in (exp_name + "_control", "enable_" + exp_name, "enable" + exp_name):
                        ctrl = node.parm(ctrl_name)
                        if ctrl:
                            try:
                                if isinstance(ctrl.eval(), str): ctrl.set("set")
                                else: ctrl.set(1)
                            except: pass

                    target_exp.deleteAllKeyframes()
                    path = target_exp.path()
                    if path in hou.session.crucible_original_states:
                        target_exp.set(hou.session.crucible_original_states[path])
                except: pass
                
            # Clear Color
            target_col = None
            for cn in ("lightcolor", "light_color", "color", "inputs:color", "ar_color", "xn__inputscolor_v3a"):
                pt = node.parmTuple(cn)
                if pt is not None and len(pt) >= 3:
                    target_col = pt
                    break
            if target_col is None:
                for pt in node.parmTuples():
                    tn = pt.name().lower()
                    if ("color" in tn and "shadow" not in tn and "guide" not in tn
                            and len(pt) >= 3 and "enable" not in tn
                            and "temperature" not in tn and "control" not in tn):
                        target_col = pt
                        break
                        
            if target_col:
                try:
                    # Unlock first
                    col_name = target_col.name()
                    for ctrl_name in (col_name + "_control", "enable_" + col_name, "enable" + col_name):
                        ctrl = node.parm(ctrl_name)
                        if ctrl:
                            try:
                                if isinstance(ctrl.eval(), str): ctrl.set("set")
                                else: ctrl.set(1)
                            except: pass

                    for p in target_col:
                        p.deleteAllKeyframes()
                    path = f"{target_col.node().path()}/{target_col.name()}"
                    if path in hou.session.crucible_original_states:
                        target_col.set(hou.session.crucible_original_states[path])
                except: pass
                
            updated += 1
            
    if updated > 0:
        print(f"[Crucible] Cleared keyframes and restored original state for '{light_name}'")


# ── Message Dispatcher ────────────────────────────────────────────────────────

def _dispatch(data: dict):
    """Route an incoming message to the correct handler."""
    msg_type = data.get("type", "light_state")  # default for v1 compat

    if msg_type == "light_state":
        _apply_light_state(data)
    elif msg_type == "clear_keyframes":
        _clear_keyframes(data)
    elif msg_type == "request_camera":
        _handle_request_camera(data)
    elif msg_type == "request_scene":
        _handle_request_scene(data)
    elif msg_type == "ping":
        _send_to_nuke({"type": "pong", "source_dcc": "houdini"})
    else:
        print(f"[Crucible LiveBridge] Unknown message type: '{msg_type}'")


# ── Event Loop Callback ───────────────────────────────────────────────────────

def _event_loop_callback():
    """Called by Houdini on its main thread every UI tick — drain the queue."""
    q = hou.session.crucible_bridge_queue
    while not q.empty():
        try:
            data = q.get_nowait()
            _dispatch(data)
        except Exception as e:
            print(f"[Crucible LiveBridge] dispatch error: {e}")
            
    if hou.session.crucible_is_updating:
        return
        
    import time
    now = time.time()
    if now - hou.session.crucible_bridge_last_push < 0.2:
        return
        
    current_hash = ""
    for node in hou.node("/").allSubChildren():
        nt = node.type().name().lower()
        if not any(kw in nt for kw in ("light", "env", "sun")):
            continue
        try:
            intensity = 1.0
            for pname in ("exposure", "ar_exposure", "xn__inputsexposure_v3a"):
                p = node.parm(pname)
                if p:
                    current_exp = p.eval()
                    path = p.path()
                    orig_exp = hou.session.crucible_original_states.get(path, current_exp)
                    intensity = 2.0 ** (current_exp - orig_exp)
                    break
            color = [1.0, 1.0, 1.0]
            for cname in ("color", "light_color", "ar_color", "xn__inputscolor_v3a"):
                pt = node.parmTuple(cname)
                if pt and len(pt) >= 3:
                    current_col = pt.eval()[:3]
                    path = pt.path()
                    orig_col = hou.session.crucible_original_states.get(path, current_col)
                    color = [
                        current_col[0] / orig_col[0] if orig_col[0] > 0 else 1.0,
                        current_col[1] / orig_col[1] if orig_col[1] > 0 else 1.0,
                        current_col[2] / orig_col[2] if orig_col[2] > 0 else 1.0
                    ]
                    break
            current_hash += f"{node.name()}:{intensity:.3f}:{color[0]:.3f},{color[1]:.3f},{color[2]:.3f};"
        except:
            pass
            
    if current_hash != hou.session.crucible_bridge_last_hash:
        if hou.session.crucible_bridge_last_hash is not None:
            hou.session.crucible_bridge_last_push = now
            _handle_request_scene({})
        hou.session.crucible_bridge_last_hash = current_hash


# ── TCP Server Loop ───────────────────────────────────────────────────────────

def _server_loop(srv_sock):
    """Background thread: accept → recv framed JSON → enqueue."""
    srv_sock.settimeout(1.0)
    while hou.session.crucible_bridge_running:
        try:
            conn, addr = srv_sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            with conn:
                length_bytes = _recv_exactly(conn, 4)
                length       = int.from_bytes(length_bytes, "big")
                payload      = _recv_exactly(conn, length)
                data         = json.loads(payload.decode("utf-8"))
                hou.session.crucible_bridge_queue.put(data)
        except Exception as e:
            print(f"[Crucible LiveBridge] recv error: {e}")


# ── Toggle ────────────────────────────────────────────────────────────────────

def toggle_server(silent=False):
    if hou.session.crucible_bridge_running:
        # ── STOP ──
        hou.session.crucible_bridge_running = False
        # Restore original states
        for path, val in hou.session.crucible_original_states.items():
            try:
                p = hou.parm(path)
                if p: p.set(val)
                else:
                    pt = hou.parmTuple(path)
                    if pt: pt.set(val)
            except Exception:
                pass
        hou.session.crucible_original_states.clear()

        if hou.session.crucible_bridge_socket:
            try:
                hou.session.crucible_bridge_socket.close()
            except Exception:
                pass
            hou.session.crucible_bridge_socket = None
        try:
            hou.ui.removeEventLoopCallback(_event_loop_callback)
        except Exception:
            pass
        if not silent:
            hou.ui.displayMessage(
                "Crucible LiveBridge STOPPED.",
                title="Crucible Live Bridge v2"
            )
        log_message("LiveBridge STOPPED.")
        return

    # ── START ──
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        import os
        if os.name != 'nt':
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", _LISTEN_PORT))
        srv.listen(5)
        hou.session.crucible_bridge_socket = srv
    except OSError as e:
        if not silent:
            hou.ui.displayMessage(
                f"Failed to start server on port {_LISTEN_PORT}:\n{e}\n\n"
                f"Restart Houdini to clear ghost threads if the port is stuck.",
                title="Crucible Live Bridge v2 Error"
            )
        return

    hou.session.crucible_bridge_running = True
    t = threading.Thread(
        target=_server_loop, args=(srv,), daemon=True, name="CrucibleLiveBridge"
    )
    t.start()
    
    try:
        hou.ui.removeEventLoopCallback(_event_loop_callback)
    except Exception:
        pass
    hou.ui.addEventLoopCallback(_event_loop_callback)

    if not silent:
        hou.ui.displayMessage(
            f"Crucible LiveBridge v2 RUNNING\n\n"
            f"  Listening on port  : {_LISTEN_PORT}\n"
            f"Click this button again to stop.",
            title="Crucible Live Bridge v2"
        )
    log_message("LiveBridge RUNNING.")

class CrucibleLiveBridgeWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(CrucibleLiveBridgeWindow, self).__init__(parent)
        self.setWindowTitle("Crucible LiveBridge (Houdini)")
        self.resize(400, 340)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(5)
        
        lbl = QtWidgets.QLabel("Crucible LiveBridge")
        f = lbl.font()
        f.setBold(True)
        lbl.setFont(f)
        layout.addWidget(lbl)
        
        layout.addWidget(QtWidgets.QLabel("Connects Houdini to Nuke's Pass Manager and Light Mixer"))
        
        self.toggle_btn = QtWidgets.QPushButton()
        self.toggle_btn.setMinimumHeight(40)
        self.toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self.toggle_btn)
        
        layout.addWidget(QtWidgets.QLabel("Server Logs:"))
        
        self.log_field = QtWidgets.QTextEdit()
        self.log_field.setReadOnly(True)
        self.log_field.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        font = self.log_field.font()
        font.setFamily("Consolas")
        if hasattr(font, 'setPointSize'):
            font.setPointSize(9)
        self.log_field.setFont(font)
        layout.addWidget(self.log_field)
        
        self._update_state()
        hou.session.crucible_ui_instance = self
        
    def _update_state(self):
        is_running = getattr(hou.session, "crucible_bridge_running", False)
        if is_running:
            self.toggle_btn.setText("Stop Server (ON)")
            self.toggle_btn.setStyleSheet("background-color: #4a8c4a; color: white;")
        else:
            self.toggle_btn.setText("Start Server (OFF)")
            self.toggle_btn.setStyleSheet("background-color: #8c4a4a; color: white;")
            
    def _on_toggle(self):
        toggle_server(silent=True)
        self._update_state()
        
    def append_log(self, msg):
        self.log_field.append(msg)
        
    def closeEvent(self, event):
        hou.session.crucible_ui_instance = None
        super(CrucibleLiveBridgeWindow, self).closeEvent(event)

def show_ui():
    if getattr(hou.session, 'crucible_ui_instance', None):
        hou.session.crucible_ui_instance.close()
        
    parent = hou.qt.mainWindow()
    win = CrucibleLiveBridgeWindow(parent)
    win.show()

# ── Entry point ───────────────────────────────────────────────────────────────
show_ui()
