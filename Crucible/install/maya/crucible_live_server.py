"""
Crucible Live Bridge — Maya Server
====================================
Paste the entire contents of this file into a Maya Script Editor (Python tab)
and execute it, OR create a shelf button from it.

When executed:
  1. A background thread starts listening on TCP port 7891.
  2. Incoming Nuke light-state packets are queued.
  3. maya.utils.executeDeferred() dispatches the update safely on Maya's main
     thread — no UI freezing, no scene corruption.

Run the script again to STOP the server (it toggles).

Supported render engines (auto-detected from the JSON 'target_engine' field):
  Arnold    — aiExposure, color
  V-Ray     — intensityMult, lightColor
  Redshift  — multiplier, color
  Standard  — intensity, color
"""

import json
import math
import queue
import socket
import threading
import maya.cmds as cmds
import maya.utils as mu

# ── Module-level singletons ──────────────────────────────────────────────────
_SRV_THREAD  = None
_SRV_SOCK    = None
_PACKET_Q    = queue.Queue()
_RUNNING     = False
_PORT        = 7891
_NUKE_HOST = "127.0.0.1"
_NUKE_PORT = 7893

def _send_to_nuke(data):
    def _do():
        try:
            import json, socket
            payload = json.dumps(data).encode("utf-8")
            with socket.create_connection((_NUKE_HOST, _NUKE_PORT), timeout=3.0) as s:
                s.sendall(len(payload).to_bytes(4, "big") + payload)
            log_message("-> Nuke: {data.get('type','?')}")
        except OSError as e:
            log_message("Cannot reach Nuke:{_NUKE_PORT}: {e}")
    threading.Thread(target=_do, daemon=True, name="CrucibleMayaSend").start()

def _handle_request_scene(msg):
    lights = []
    light_shapes = cmds.ls(lights=True) or []
    extra_types = [
        "aiAreaLight", "aiSkyDomeLight", "aiPhotometricLight",
        "VRayLightSphereShape", "VRayLightRectShape", "VRayLightIESShape",
        "RedshiftPhysicalLight", "RedshiftIESLight", "RedshiftDomeLight"
    ]
    for ext_type in extra_types:
        try:
            found = cmds.ls(type=ext_type)
            if found:
                light_shapes.extend(found)
        except Exception:
            pass
            
    light_shapes = list(set(light_shapes))
    
    for shape in light_shapes:
        transforms = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        transform_name = cmds.ls(transforms[0], shortNames=True)[0] if transforms else shape
        
        intensity = 1.0
        color = [1.0, 1.0, 1.0]
        nt = cmds.nodeType(shape)
        
        try:
            if nt.startswith("ai"):
                if cmds.objExists(f"{shape}.aiExposure"):
                    exp = cmds.getAttr(f"{shape}.aiExposure")
                    orig_exp = _ORIGINAL_STATES.get(f"{shape}.aiExposure", exp)
                    intensity = 2.0 ** (exp - orig_exp) if exp != orig_exp else 1.0
                if cmds.objExists(f"{shape}.color"):
                    col = cmds.getAttr(f"{shape}.color")[0]
                    orig_col = _ORIGINAL_STATES.get(f"{shape}.color", col)
                    color = [
                        col[0] / orig_col[0] if orig_col[0] > 0 else 1.0,
                        col[1] / orig_col[1] if orig_col[1] > 0 else 1.0,
                        col[2] / orig_col[2] if orig_col[2] > 0 else 1.0,
                    ]
            elif nt.startswith("Redshift"):
                exp_attr = f"{shape}.exposure0" if cmds.objExists(f"{shape}.exposure0") else f"{shape}.exposure"
                if cmds.objExists(exp_attr):
                    exp = cmds.getAttr(exp_attr)
                    orig_exp = _ORIGINAL_STATES.get(exp_attr, exp)
                    intensity = 2.0 ** (exp - orig_exp) if exp != orig_exp else 1.0
                if cmds.objExists(f"{shape}.color"):
                    col = cmds.getAttr(f"{shape}.color")[0]
                    orig_col = _ORIGINAL_STATES.get(f"{shape}.color", col)
                    color = [
                        col[0] / orig_col[0] if orig_col[0] > 0 else 1.0,
                        col[1] / orig_col[1] if orig_col[1] > 0 else 1.0,
                        col[2] / orig_col[2] if orig_col[2] > 0 else 1.0,
                    ]
            elif nt.startswith("VRay"):
                if cmds.objExists(f"{shape}.intensityMult"):
                    int_mult = cmds.getAttr(f"{shape}.intensityMult")
                    orig_int = _ORIGINAL_STATES.get(f"{shape}.intensityMult", int_mult)
                    intensity = int_mult / orig_int if orig_int > 0 else 1.0
                if cmds.objExists(f"{shape}.lightColor"):
                    col = cmds.getAttr(f"{shape}.lightColor")[0]
                    orig_col = _ORIGINAL_STATES.get(f"{shape}.lightColor", col)
                    color = [
                        col[0] / orig_col[0] if orig_col[0] > 0 else 1.0,
                        col[1] / orig_col[1] if orig_col[1] > 0 else 1.0,
                        col[2] / orig_col[2] if orig_col[2] > 0 else 1.0,
                    ]
            else:
                if cmds.objExists(f"{shape}.intensity"):
                    int_val = cmds.getAttr(f"{shape}.intensity")
                    orig_int = _ORIGINAL_STATES.get(f"{shape}.intensity", int_val)
                    intensity = int_val / orig_int if orig_int > 0 else 1.0
                if cmds.objExists(f"{shape}.color"):
                    col = cmds.getAttr(f"{shape}.color")[0]
                    orig_col = _ORIGINAL_STATES.get(f"{shape}.color", col)
                    color = [
                        col[0] / orig_col[0] if orig_col[0] > 0 else 1.0,
                        col[1] / orig_col[1] if orig_col[1] > 0 else 1.0,
                        col[2] / orig_col[2] if orig_col[2] > 0 else 1.0,
                    ]
        except Exception:
            pass

        lights.append({
            "name": transform_name,
            "type": nt,
            "intensity": intensity,
            "color": color
        })
        
    start_time = cmds.playbackOptions(q=True, minTime=True)
    end_time = cmds.playbackOptions(q=True, maxTime=True)
    fps_map = {"film": 24, "pal": 25, "ntsc": 30}
    fps = fps_map.get(cmds.currentUnit(q=True, time=True), 24)

    _send_to_nuke({
        "type": "scene_info",
        "source_dcc": "maya",
        "shot": {
            "frame_start": int(start_time),
            "frame_end": int(end_time),
            "fps": float(fps)
        },
        "lights": lights,
        "passes": []
    })

def _handle_request_camera(msg):
    cams = [c for c in cmds.ls(type='camera') if not cmds.camera(c, q=True, startupCamera=True)]
    if not cams:
        _send_to_nuke({"type": "error", "message": "No render camera found."})
        return
    cam_shape = cams[0]
    cam_trans = cmds.listRelatives(cam_shape, parent=True)[0]
    
    def _get_cam_data(frame):
        cmds.currentTime(frame, edit=True)
        tx = cmds.getAttr(f"{cam_trans}.tx")
        ty = cmds.getAttr(f"{cam_trans}.ty")
        tz = cmds.getAttr(f"{cam_trans}.tz")
        rx = cmds.getAttr(f"{cam_trans}.rx")
        ry = cmds.getAttr(f"{cam_trans}.ry")
        rz = cmds.getAttr(f"{cam_trans}.rz")
        sx = cmds.getAttr(f"{cam_trans}.sx")
        sy = cmds.getAttr(f"{cam_trans}.sy")
        sz = cmds.getAttr(f"{cam_trans}.sz")
        focal = cmds.camera(cam_shape, q=True, focalLength=True)
        h_aperture = cmds.camera(cam_shape, q=True, horizontalFilmAperture=True) * 25.4
        v_aperture = cmds.camera(cam_shape, q=True, verticalFilmAperture=True) * 25.4
        near = cmds.camera(cam_shape, q=True, nearClipPlane=True)
        far = cmds.camera(cam_shape, q=True, farClipPlane=True)
        fd = cmds.camera(cam_shape, q=True, focusDistance=True)
        fstop = cmds.camera(cam_shape, q=True, fStop=True)
        return {
            "frame": frame,
            "translate": [tx, ty, tz],
            "rotate": [rx, ry, rz],
            "scale": [sx, sy, sz],
            "focal_length_mm": focal,
            "haperture_mm": h_aperture,
            "vaperture_mm": v_aperture,
            "near_clip": near,
            "far_clip": far,
            "focus_distance": fd,
            "fstop": fstop,
            "lens_distortion": {"k1": 0.0, "k2": 0.0, "k3": 0.0, "p1": 0.0, "p2": 0.0},
        }

    frame_start = msg.get("frame_start")
    frame_end   = msg.get("frame_end")
    orig_time = cmds.currentTime(q=True)
    
    fps_map = {"film": 24, "pal": 25, "ntsc": 30}
    fps = fps_map.get(cmds.currentUnit(q=True, time=True), 24)

    if frame_start is not None and frame_end is not None:
        frames = []
        for f in range(int(frame_start), int(frame_end) + 1):
            frames.append(_get_cam_data(f))
        cmds.currentTime(orig_time, edit=True)
        _send_to_nuke({
            "type": "camera_sequence",
            "name": cam_trans,
            "source_dcc": "maya",
            "shot": {
                "frame_start": int(frame_start),
                "frame_end": int(frame_end),
                "fps": float(fps)
            },
            "frames": frames
        })
    else:
        frame_data = _get_cam_data(orig_time)
        cmds.currentTime(orig_time, edit=True)
        _send_to_nuke({
            "type": "camera_frame",
            "name": cam_trans,
            "source_dcc": "maya",
            **frame_data
        })

_ORIGINAL_STATES = {}



# ── TCP Server (background thread) ───────────────────────────────────────────

def _recv_exactly(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed mid-message")
        buf += chunk
    return buf


def _server_loop(srv_sock):
    global _RUNNING
    srv_sock.settimeout(1.0)
    while _RUNNING:
        try:
            conn, _ = srv_sock.accept()
        except socket.timeout:
            continue
        try:
            with conn:
                length = int.from_bytes(_recv_exactly(conn, 4), "big")
                data   = json.loads(_recv_exactly(conn, length).decode("utf-8"))
                _PACKET_Q.put(data)
                # Dispatch to main thread immediately via executeDeferred
                mu.executeDeferred(_drain_queue)
        except ConnectionError:
            # Silently ignore Nuke's connectivity-check pings which open and close immediately
            pass
        except Exception as e:
            log_message("recv error: {e}")


# ── Main-Thread Update ────────────────────────────────────────────────────────

def _drain_queue():
    """Called on Maya's main thread via executeDeferred."""
    while not _PACKET_Q.empty():
        try:
            data = _PACKET_Q.get_nowait()
            msg_type = data.get("type", "light_state")
            
            if msg_type == "ping":
                _send_to_nuke({"type": "pong", "source_dcc": "maya"})
            elif msg_type == "request_scene":
                _handle_request_scene(data)
            elif msg_type == "request_camera":
                _handle_request_camera(data)
            elif msg_type == "light_state":
                _apply_light_state(data)
            else:
                _apply_light_state(data)
        except Exception as e:
            log_message("apply error: {e}")


def _apply_light_state(data: dict):
    """Apply incoming Nuke light state to Maya lights."""
    multipliers = data.get("lighting_multipliers", data)
    meta        = data.get("metadata", {})
    engine      = meta.get("target_engine", "Arnold")
    frame       = meta.get("frame")
    updated     = 0

    if frame is not None:
        try:
            cmds.currentTime(frame, edit=True)
        except Exception:
            pass

    # Collect standard Maya lights
    light_shapes = cmds.ls(lights=True) or []
    
    # Safely query 3rd party lights one by one so an unloaded plugin doesn't break the rest
    extra_types = [
        "aiAreaLight", "aiSkyDomeLight", "aiPhotometricLight",
        "VRayLightSphereShape", "VRayLightRectShape", "VRayLightIESShape",
        "RedshiftPhysicalLight", "RedshiftIESLight", "RedshiftDomeLight"
    ]
    for ext_type in extra_types:
        try:
            found = cmds.ls(type=ext_type)
            if found:
                light_shapes.extend(found)
        except Exception:
            pass
            
    # Remove duplicates
    light_shapes = list(set(light_shapes))

    for shape in light_shapes:
        transforms = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        transform_name = cmds.ls(transforms[0], shortNames=True)[0] if transforms else shape
        
        names_to_try = [shape.lower(), transform_name.lower()]
        if shape.lower().endswith("shape"):
            names_to_try.append(shape.lower()[:-5])

        matched_key = None
        for k in multipliers:
            clean_k = k.lower()
            for pfx in ("c_", "rgba_", "lightgroup_"):
                if clean_k.startswith(pfx):
                    clean_k = clean_k[len(pfx):]
                    break
            
            for n in names_to_try:
                if n == clean_k or n.startswith(clean_k) or n.endswith(clean_k):
                    matched_key = k
                    break
            if matched_key:
                break

        if matched_key is None:
            continue

        entry = multipliers[matched_key]
        if isinstance(entry, dict):
            mult  = entry.get("multiplier", 1.0)
            color = entry.get("color", [1.0, 1.0, 1.0])
        else:
            mult  = float(entry)
            color = [1.0, 1.0, 1.0]

        abs_mult = abs(mult)
        color_sign = -1.0 if mult < 0 else 1.0

        # ── Engine-specific attribute mapping ────────────────────────────
        if engine == "Arnold":
            exp_attr   = f"{shape}.aiExposure"
            col_attr   = f"{shape}.color"
            if cmds.objExists(exp_attr):
                if exp_attr not in _ORIGINAL_STATES:
                    _ORIGINAL_STATES[exp_attr] = cmds.getAttr(exp_attr)
                
                orig_exp = _ORIGINAL_STATES[exp_attr]
                new_exp = orig_exp + math.log2(abs_mult) if abs_mult > 0 else -100.0
                if frame is not None:
                    cmds.setKeyframe(exp_attr, value=new_exp, time=frame)
                else:
                    try: cmds.setAttr(exp_attr, new_exp)
                    except: pass
                
            if cmds.objExists(col_attr):
                if col_attr not in _ORIGINAL_STATES:
                    _ORIGINAL_STATES[col_attr] = cmds.getAttr(col_attr)[0]
                
                orig_col = _ORIGINAL_STATES[col_attr]
                c_r = orig_col[0] * color[0] * color_sign
                c_g = orig_col[1] * color[1] * color_sign
                c_b = orig_col[2] * color[2] * color_sign
                if frame is not None:
                    cmds.setKeyframe(f"{col_attr}R", value=c_r, time=frame)
                    cmds.setKeyframe(f"{col_attr}G", value=c_g, time=frame)
                    cmds.setKeyframe(f"{col_attr}B", value=c_b, time=frame)
                else:
                    try: cmds.setAttr(col_attr, c_r, c_g, c_b, type="double3")
                    except: pass

        elif engine == "V-Ray":
            int_attr = f"{shape}.intensityMult"
            col_attr = f"{shape}.lightColor"
            if cmds.objExists(int_attr):
                if int_attr not in _ORIGINAL_STATES:
                    _ORIGINAL_STATES[int_attr] = cmds.getAttr(int_attr)
                new_val = _ORIGINAL_STATES[int_attr] * abs_mult
                if frame is not None:
                    cmds.setKeyframe(int_attr, value=new_val, time=frame)
                else:
                    try: cmds.setAttr(int_attr, new_val)
                    except: pass
                
            if cmds.objExists(col_attr):
                if col_attr not in _ORIGINAL_STATES:
                    _ORIGINAL_STATES[col_attr] = cmds.getAttr(col_attr)[0]
                
                orig_col = _ORIGINAL_STATES[col_attr]
                c_r = orig_col[0] * color[0] * color_sign
                c_g = orig_col[1] * color[1] * color_sign
                c_b = orig_col[2] * color[2] * color_sign
                if frame is not None:
                    cmds.setKeyframe(f"{col_attr}R", value=c_r, time=frame)
                    cmds.setKeyframe(f"{col_attr}G", value=c_g, time=frame)
                    cmds.setKeyframe(f"{col_attr}B", value=c_b, time=frame)
                else:
                    try: cmds.setAttr(col_attr, c_r, c_g, c_b, type="double3")
                    except: pass

        elif engine == "Redshift":
            # Dome lights sometimes use exposure0 instead of exposure in Maya
            exp_attr = f"{shape}.exposure0" if cmds.objExists(f"{shape}.exposure0") else f"{shape}.exposure"
            col_attr = f"{shape}.color"
            if cmds.objExists(exp_attr):
                if exp_attr not in _ORIGINAL_STATES:
                    _ORIGINAL_STATES[exp_attr] = cmds.getAttr(exp_attr)
                
                orig_exp = _ORIGINAL_STATES[exp_attr]
                new_exp = orig_exp + math.log2(abs_mult) if abs_mult > 0 else -100.0
                if frame is not None:
                    cmds.setKeyframe(exp_attr, value=new_exp, time=frame)
                else:
                    try: cmds.setAttr(exp_attr, new_exp)
                    except: pass
                
            if cmds.objExists(col_attr):
                if col_attr not in _ORIGINAL_STATES:
                    _ORIGINAL_STATES[col_attr] = cmds.getAttr(col_attr)[0]
                orig_col = _ORIGINAL_STATES[col_attr]
                c_r = orig_col[0] * color[0] * color_sign
                c_g = orig_col[1] * color[1] * color_sign
                c_b = orig_col[2] * color[2] * color_sign
                if frame is not None:
                    cmds.setKeyframe(f"{col_attr}R", value=c_r, time=frame)
                    cmds.setKeyframe(f"{col_attr}G", value=c_g, time=frame)
                    cmds.setKeyframe(f"{col_attr}B", value=c_b, time=frame)
                else:
                    try: cmds.setAttr(col_attr, c_r, c_g, c_b, type="double3")
                    except: pass

        else:
            # Standard Maya lights
            int_attr = f"{shape}.intensity"
            col_attr = f"{shape}.color"
            if cmds.objExists(int_attr):
                if int_attr not in _ORIGINAL_STATES:
                    _ORIGINAL_STATES[int_attr] = cmds.getAttr(int_attr)
                new_val = _ORIGINAL_STATES[int_attr] * abs_mult
                if frame is not None:
                    cmds.setKeyframe(int_attr, value=new_val, time=frame)
                else:
                    try: cmds.setAttr(int_attr, new_val)
                    except: pass
                
            if cmds.objExists(col_attr):
                if col_attr not in _ORIGINAL_STATES:
                    _ORIGINAL_STATES[col_attr] = cmds.getAttr(col_attr)[0]
                orig_col = _ORIGINAL_STATES[col_attr]
                c_r = orig_col[0] * color[0] * color_sign
                c_g = orig_col[1] * color[1] * color_sign
                c_b = orig_col[2] * color[2] * color_sign
                if frame is not None:
                    cmds.setKeyframe(f"{col_attr}R", value=c_r, time=frame)
                    cmds.setKeyframe(f"{col_attr}G", value=c_g, time=frame)
                    cmds.setKeyframe(f"{col_attr}B", value=c_b, time=frame)
                else:
                    try: cmds.setAttr(col_attr, c_r, c_g, c_b, type="double3")
                    except: pass

        if frame is not None:
            log_message(f"Keyed {shape} at frame {frame}")
        else:
            log_message(f"Updated {shape}")
        updated += 1

    log_message(f"Applied to {updated} lights ({engine})")


# ── Toggle ────────────────────────────────────────────────────────────────────


# ── UI & Logging ──────────────────────────────────────────────────────────────

_LOG_FIELD = None
_UI_WINDOW = "CrucibleLiveBridgeWindow"

def log_message(msg):
    """Print to script editor and also push to UI if it exists."""
    print(f"[Crucible] {msg}")
    if _LOG_FIELD and cmds.window(_UI_WINDOW, exists=True):
        mu.executeDeferred(lambda: _append_log(msg))

def _append_log(msg):
    if _LOG_FIELD and cmds.scrollField(_LOG_FIELD, exists=True):
        current = cmds.scrollField(_LOG_FIELD, q=True, text=True)
        lines = current.split('\n') if current else []
        if len(lines) > 50:
            lines = lines[-50:]
        lines.append(msg)
        new_text = '\n'.join(lines)
        cmds.scrollField(_LOG_FIELD, e=True, text=new_text)
        cmds.scrollField(_LOG_FIELD, e=True, insertionPosition=len(new_text))

def _update_ui_state():
    if cmds.window(_UI_WINDOW, exists=True):
        if _RUNNING:
            cmds.button("crucibleToggleBtn", e=True, label="Stop Server (ON)", backgroundColor=(0.3, 0.8, 0.3))
        else:
            cmds.button("crucibleToggleBtn", e=True, label="Start Server (OFF)", backgroundColor=(0.8, 0.3, 0.3))

def toggle_denoise(*args):
    toggled = False
    rs_options = cmds.ls(type="RedshiftOptions")
    if rs_options:
        rs_node = rs_options[0]
        for attr in ['denoisingEnabled', 'denoiseEnabled', 'denoiseEnable', 'denoiserEnabled', 'denoiserEnable', 'denoiseOptiX', 'denoiseOptix']:
            if cmds.objExists(f'{rs_node}.{attr}'):
                curr = cmds.getAttr(f'{rs_node}.{attr}')
                cmds.setAttr(f'{rs_node}.{attr}', not curr)
                log_message(f"Redshift '{attr}' set to {not curr}")
                toggled = True
                break

    imagers = cmds.ls(type=['aiImagerDenoiserOptix', 'aiImagerDenoiserOidn', 'aiImagerDenoiserNoice']) or []
    for img in imagers:
        for attr in ['enable', 'enabled']:
            if cmds.objExists(f"{img}.{attr}"):
                curr = cmds.getAttr(f"{img}.{attr}")
                cmds.setAttr(f"{img}.{attr}", not curr)
                log_message(f"Arnold Denoiser '{img}' set to {not curr}")
                toggled = True
                break
            
    if not toggled:
        log_message("Could not find an active Denoiser (Redshift/Arnold) to toggle.")

def show_ui():
    global _LOG_FIELD
    if cmds.window(_UI_WINDOW, exists=True):
        cmds.deleteUI(_UI_WINDOW, window=True)
        
    cmds.window(_UI_WINDOW, title="Crucible LiveBridge (Maya)", widthHeight=(400, 340), sizeable=True)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=5, columnAttach=('both', 5))
    
    cmds.separator(height=10, style='none')
    cmds.text(label="Crucible LiveBridge", font="boldLabelFont")
    cmds.text(label="Connects Maya to Nuke's Pass Manager and Light Mixer")
    cmds.separator(height=15)
    
    bg_color = (0.3, 0.8, 0.3) if _RUNNING else (0.8, 0.3, 0.3)
    lbl = "Stop Server (ON)" if _RUNNING else "Start Server (OFF)"
    cmds.button("crucibleToggleBtn", label=lbl, height=40, backgroundColor=bg_color, command=toggle_server)
    
    cmds.button("crucibleDenoiseBtn", label="Toggle Viewport Denoise", height=30, backgroundColor=(0.2, 0.4, 0.6), command=toggle_denoise)
    
    cmds.separator(height=15)
    cmds.text(label="Server Logs:", align="left")
    
    _LOG_FIELD = cmds.scrollField(editable=False, wordWrap=True, height=200, font="smallFixedWidthFont")
    
    cmds.showWindow(_UI_WINDOW)
    log_message("UI Initialized.")

def toggle_server(*args):
    global _SRV_THREAD, _SRV_SOCK, _RUNNING, _ORIGINAL_STATES

    if _RUNNING:
        _RUNNING = False
        
        # Restore original states so the scene isn't permanently modified
        for attr, val in _ORIGINAL_STATES.items():
            try:
                if cmds.objExists(attr):
                    if isinstance(val, (list, tuple)) and len(val) >= 3:
                        cmds.setAttr(attr, val[0], val[1], val[2], type="double3")
                    else:
                        cmds.setAttr(attr, val)
            except Exception:
                pass
                
        _ORIGINAL_STATES.clear()
        
        if _SRV_SOCK:
            try:
                _SRV_SOCK.close()
            except Exception:
                pass
            _SRV_SOCK = None
            
        cmds.inViewMessage(
            amg="<hl>Crucible Maya LiveBridge</hl> STOPPED.",
            pos="topCenter", fade=True
        )
        log_message("Server STOPPED. Original states restored.")
        _update_ui_state()
        return

    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", _PORT))
        srv.listen(5)
        _SRV_SOCK = srv
    except OSError as e:
        log_message(f"Failed to start server on port {_PORT}: {e}")
        return

    _ORIGINAL_STATES.clear()
    _RUNNING = True
    _SRV_THREAD = threading.Thread(
        target=_server_loop, args=(srv,), daemon=True, name="CrucibleMayaLiveBridge"
    )
    _SRV_THREAD.start()

    cmds.inViewMessage(
        amg=f"<hl>Crucible Maya LiveBridge</hl> RUNNING on port <hl>{_PORT}</hl>.<br>"
            f"Enable Live Link in Nuke's Crucible panel.",
        pos="topCenter", fade=True
    )
    log_message(f"Server RUNNING on port {_PORT}. Click Stop Server to disable.")
    _update_ui_state()
    


show_ui()
