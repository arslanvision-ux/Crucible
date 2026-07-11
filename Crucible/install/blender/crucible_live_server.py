"""
Crucible Live Bridge — Blender Bidirectional Server  v2.0
=========================================================
Paste the entire contents of this file into the Blender Scripting
workspace and click Run Script, or install it as an add-on.

Architecture
------------
  Blender listens on port  7892  (receives requests from Nuke)
  Blender sends back to    7893  (Nuke's NukeLiveListener port)

Supported message types
-----------------------
  Incoming (from Nuke):
    light_state        Update emission strength/color on matching lights
    request_camera     Push back camera_frame or camera_sequence
    request_scene      Push back scene_info snapshot
    ping               Reply with pong

  Outgoing (to Nuke):
    camera_frame       Single-frame camera data
    camera_sequence    Animated camera over a frame range
    scene_info         All lights + render settings
    pong               Heartbeat reply

USAGE
-----
1. Blender -> Scripting workspace -> New text block.
2. Paste this file and click Run Script.
3. In Nuke's Crucible panel -> Pass Manager -> Live Pull:
   Select "Blender", Out Port = 7892, click a Pull button.
4. Run the script again to stop the server.
"""

import bpy
import json
import math
import queue
import socket
import threading

# Configuration
_LISTEN_PORT    = 7892
_NUKE_HOST      = "127.0.0.1"
_NUKE_PORT      = 7893


def _recv_exactly(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed mid-read")
        buf += chunk
    return buf


def _send_to_nuke(data: dict):
    """Fire-and-forget send from Blender to Nuke."""
    try:
        import json
        with open('e:/PROJECTS/Crucible/crucible/blender_debug.json', 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass
    def _do():
        try:
            payload = json.dumps(data).encode("utf-8")
            with socket.create_connection((_NUKE_HOST, _NUKE_PORT), timeout=3.0) as s:
                s.sendall(len(payload).to_bytes(4, "big") + payload)
            print(f"[Crucible Blender] -> Nuke: {data.get('type','?')}")
        except OSError as e:
            print(f"[Crucible Blender] Cannot reach Nuke:{_NUKE_PORT}: {e}")
    threading.Thread(target=_do, daemon=True, name="CrucibleBlenderSend").start()


def log_message(msg):
    """Log to console and UI."""
    print(f"[Crucible Blender] {msg}")
    try:
        logs = bpy.context.window_manager.crucible_logs
        lines = logs.split("\n") if logs else []
        if len(lines) > 20:
            lines = lines[-20:]
        lines.append(msg)
        bpy.context.window_manager.crucible_logs = "\n".join(lines)
        
        # Redraw UI
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    except Exception:
        pass


def _mat4_to_trs(matrix):
    import mathutils
    import math
    axis_conversion = mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X')
    nuke_matrix = axis_conversion @ matrix
    loc, rot, scale = nuke_matrix.decompose()
    euler = rot.to_euler("ZXY")
    return (
        [loc.x, loc.y, loc.z],
        [math.degrees(euler.x), math.degrees(euler.y), math.degrees(euler.z)],
        [scale.x, scale.y, scale.z],
    )


def _camera_record(scene, cam_obj, frame):
    scene.frame_set(frame)
    cam_data = cam_obj.data
    translate, rotate, scale = _mat4_to_trs(cam_obj.matrix_world)
    focal = cam_data.lens
    if cam_data.sensor_fit in ("HORIZONTAL", "AUTO"):
        haperture = cam_data.sensor_width
        aspect    = scene.render.resolution_x / max(scene.render.resolution_y, 1)
        vaperture = haperture / max(aspect, 0.0001)
    else:
        vaperture = cam_data.sensor_height
        aspect    = scene.render.resolution_x / max(scene.render.resolution_y, 1)
        haperture = vaperture * aspect
    return {
        "frame": frame, "translate": translate, "rotate": rotate, "scale": scale,
        "focal_length_mm": focal, "haperture_mm": haperture, "vaperture_mm": vaperture,
        "near_clip": cam_data.clip_start, "far_clip": cam_data.clip_end,
        "focus_distance": cam_data.dof.focus_distance,
        "fstop": cam_data.dof.aperture_fstop,
        "lens_distortion": {"k1": 0.0, "k2": 0.0, "k3": 0.0, "p1": 0.0, "p2": 0.0},
    }


def _light_energy_color(scene, obj):
    ld = obj.data
    energy, color = 1.0, [1.0, 1.0, 1.0]
    
    if getattr(ld, "node_tree", None):
        # Look for the Crucible injection nodes first
        for node in ld.node_tree.nodes:
            if node.name == "Crucible_Mult_Strength":
                energy = node.inputs[1].default_value
            elif node.name == "Crucible_Tint_Color":
                rc = node.inputs[7].default_value
                color = [rc[0], rc[1], rc[2]]
    
    return energy, color


def _collect_lights_snapshot(scene):
    lights = []
    for obj in scene.objects:
        if obj.type != "LIGHT":
            continue
        energy, color = _light_energy_color(scene, obj)
        lg = getattr(obj, "lightgroup", "")
        if not lg:
            lg = getattr(obj.data, "lightgroup", "")
            
        lights.append({"name": lg if lg else obj.name, "type": obj.data.type.lower(),
                       "intensity": energy, "color": color})
                       
    print(f"[Crucible Debug] Found {len(bpy.data.worlds)} worlds in bpy.data.worlds")
    for w in bpy.data.worlds:
        lg = getattr(w, "lightgroup", "")
        energy, color = 1.0, [1.0, 1.0, 1.0]
        if getattr(w, "node_tree", None):
            for node in w.node_tree.nodes:
                if node.name == "Crucible_Mult_Strength":
                    energy = node.inputs[1].default_value
                elif node.name == "Crucible_Tint_Color":
                    rc = node.inputs[7].default_value
                    color = [rc[0], rc[1], rc[2]]
        print(f"[Crucible Debug] Appending world: {lg if lg else w.name} (Energy: {energy})")
        lights.append({"name": lg if lg else w.name, "type": "world",
                       "intensity": energy, "color": color})
                       
    print(f"[Crucible Debug] Total lights returning: {[l['name'] for l in lights]}")
    return lights


def _handle_request_camera(msg: dict):
    scene   = bpy.context.scene
    cam_obj = scene.camera
    if cam_obj is None or cam_obj.type != "CAMERA":
        _send_to_nuke({"type": "error", "message": "No active camera in Blender."})
        return
    prev = scene.frame_current
    fs   = msg.get("frame_start")
    fe   = msg.get("frame_end")
    if fs is not None and fe is not None:
        frames = [_camera_record(scene, cam_obj, f) for f in range(int(fs), int(fe) + 1)]
        scene.frame_set(prev)
        _send_to_nuke({
            "type": "camera_sequence", "name": cam_obj.name, "source_dcc": "blender",
            "shot": {"frame_start": int(fs), "frame_end": int(fe), "fps": scene.render.fps},
            "frames": frames,
        })
    else:
        rec = _camera_record(scene, cam_obj, scene.frame_current)
        scene.frame_set(prev)
        _send_to_nuke({"type": "camera_frame", "name": cam_obj.name,
                       "source_dcc": "blender", **rec})


def _handle_request_scene(msg: dict):
    scene  = bpy.context.scene
    render = scene.render
    engine = {"CYCLES": "cycles", "BLENDER_EEVEE": "eevee",
              "BLENDER_EEVEE_NEXT": "eevee"}.get(render.engine, render.engine.lower())
    _send_to_nuke({
        "type": "scene_info", "source_dcc": "blender",
        "shot": {"frame_start": int(scene.frame_start), "frame_end": int(scene.frame_end),
                 "fps": render.fps / render.fps_base},
        "render_settings": {"resolution_x": render.resolution_x,
                            "resolution_y": render.resolution_y,
                            "fps": render.fps / render.fps_base, "color_space": "ACEScg",
                            "renderer": engine},
        "lights": _collect_lights_snapshot(scene), "passes": [],
    })


def _inject_multiplier(tree, target_node, input_name, mult_val, is_color=False, frame=None):
    inp = target_node.inputs[input_name]
    
    if is_color:
        mult_val = (mult_val[0], mult_val[1], mult_val[2], 1.0)
        node_type = "ShaderNodeMix"
        node_name = f"Crucible_Tint_{input_name}"
        in_a = 6
        in_b = 7
        out_idx = 2
    else:
        mult_val = abs(mult_val)
        node_type = "ShaderNodeMath"
        node_name = f"Crucible_Mult_{input_name}"
        in_a = 0
        in_b = 1
        out_idx = 0

    if inp.is_linked:
        link = inp.links[0]
        prev_node = link.from_node
        if prev_node.name == node_name:
            prev_node.inputs[in_b].default_value = mult_val
            return
        
        mix = tree.nodes.new(node_type)
        mix.name = node_name
        if is_color:
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs[0].default_value = 1.0
        else:
            mix.operation = 'MULTIPLY'
            
        tree.links.new(link.from_socket, mix.inputs[in_a])
        tree.links.new(mix.outputs[out_idx], inp)
        mix.inputs[in_b].default_value = mult_val
    else:
        orig_val = inp.default_value
        
        mix = tree.nodes.new(node_type)
        mix.name = node_name
        if is_color:
            mix.data_type = 'RGBA'
            mix.blend_type = 'MULTIPLY'
            mix.inputs[0].default_value = 1.0
        else:
            mix.operation = 'MULTIPLY'
            
        if is_color:
            mix.inputs[in_a].default_value = (orig_val[0], orig_val[1], orig_val[2], orig_val[3])
        else:
            mix.inputs[in_a].default_value = orig_val
            
        mix.inputs[in_b].default_value = mult_val
        tree.links.new(mix.outputs[out_idx], inp)
        
    if frame is not None:
        mix.inputs[in_b].keyframe_insert(data_path="default_value", frame=frame)


def _apply_light_state(data: dict):
    bpy.app.driver_namespace["CRUCIBLE_IS_UPDATING"] = True
    multipliers = data.get("lighting_multipliers", data)
    meta = data.get("metadata", {})
    frame = meta.get("frame")
    scene = bpy.context.scene
    
    if frame is not None:
        try:
            scene.frame_set(frame)
        except Exception:
            pass
            
    updated = 0
    for obj in scene.objects:
        if obj.type != "LIGHT":
            continue
        name = obj.name.lower()
        lg   = ""
        try: lg = getattr(obj, "lightgroup", "").lower()
        except: pass
        if not lg:
            try: lg = getattr(obj.data, "lightgroup", "").lower()
            except: pass

        matched_key = None
        for k in multipliers:
            clean = k.lower()
            for pfx in ("c_", "rgba_", "lightgroup_", "combined_"):
                if clean.startswith(pfx):
                    clean = clean[len(pfx):]
                    break
            
            # Match either the object name or its designated lightgroup!
            if name == clean or (lg and lg == clean):
                matched_key = k
                break
                
        if matched_key is None:
            continue
        entry = multipliers[matched_key]
        mult  = entry.get("multiplier", 1.0) if isinstance(entry, dict) else float(entry)
        color = entry.get("color", [1.0, 1.0, 1.0]) if isinstance(entry, dict) else [1.0, 1.0, 1.0]
        try:
            ld = obj.data
            if not getattr(ld, "use_nodes", False):
                try: ld.use_nodes = True
                except: pass
                
                if getattr(ld, "node_tree", None):
                    for node in ld.node_tree.nodes:
                        if node.type == "EMISSION":
                            _inject_multiplier(ld.node_tree, node, "Strength", mult, is_color=False, frame=frame)
                            _inject_multiplier(ld.node_tree, node, "Color", color, is_color=True, frame=frame)
                            break
                if frame is not None:
                    log_message(f"Keyed {obj.name} at frame {frame}")
                else:
                    log_message(f"Updated {obj.name}")
                updated += 1
            except Exception as e:
                log_message(f"{obj.name}: {e}")

    # Process World (Dome) Lights
    for w in bpy.data.worlds:
        name = w.name.lower()
        lg   = ""
        try: lg = getattr(w, "lightgroup", "").lower()
        except: pass
        
        matched_key = None
        for k in multipliers:
            clean = k.lower()
            for pfx in ("c_", "rgba_", "lightgroup_", "combined_"):
                if clean.startswith(pfx):
                    clean = clean[len(pfx):]
                    break
            if name == clean or (lg and lg == clean):
                matched_key = k
                break
                
        if matched_key is None:
            continue
            
        entry = multipliers[matched_key]
        mult  = entry.get("multiplier", 1.0) if isinstance(entry, dict) else float(entry)
        color = entry.get("color", [1.0, 1.0, 1.0]) if isinstance(entry, dict) else [1.0, 1.0, 1.0]
        
        try:
            if getattr(w, "node_tree", None):
                for node in w.node_tree.nodes:
                    if node.type == "BACKGROUND":
                        _inject_multiplier(w.node_tree, node, "Strength", mult, is_color=False, frame=frame)
                        _inject_multiplier(w.node_tree, node, "Color", color, is_color=True, frame=frame)
                        break
                w.node_tree.update_tag()
                w.update_tag()
            if frame is not None:
                log_message(f"Keyed {w.name} at frame {frame}")
            else:
                log_message(f"Updated {w.name}")
            updated += 1
        except Exception as e:
            log_message(f"{w.name}: {e}")
    log_message(f"Applied to {updated} lights.")
    
    def _reset_updating_flag():
        bpy.app.driver_namespace["CRUCIBLE_IS_UPDATING"] = False
        return None
    bpy.app.timers.register(_reset_updating_flag, first_interval=0.2)

import time
@bpy.app.handlers.persistent
def crucible_depsgraph_update(scene, depsgraph):
    if not bpy.app.driver_namespace.get("CRUCIBLE_RUNNING", False):
        return
    last = bpy.app.driver_namespace.get("CRUCIBLE_LAST_PUSH", 0.0)
    now = time.time()
    if now - last < 0.2:
        return
    if bpy.app.driver_namespace.get("CRUCIBLE_IS_UPDATING", False):
        return
    changed = False
    for update in depsgraph.updates:
        uid = update.id
        t_name = type(uid).__name__.lower()
        if isinstance(uid, bpy.types.Object) and getattr(uid, 'type', '') == 'LIGHT':
            changed = True
            break
        elif 'light' in t_name or 'world' in t_name or 'nodetree' in t_name:
            changed = True
            break
    if not changed:
        return
    bpy.app.driver_namespace["CRUCIBLE_LAST_PUSH"] = now
    print("[Crucible Blender] Light changed, pushing to Nuke...")
    _handle_request_scene({})


def _dispatch(data: dict):
    t = data.get("type", "light_state")
    print(f"[Crucible Blender] Dispatching packet: {t}")
    if t == "light_state":
        _apply_light_state(data)
    elif t == "request_camera":
        _handle_request_camera(data)
    elif t == "request_scene":
        _handle_request_scene(data)
    elif t == "ping":
        _send_to_nuke({"type": "pong", "source_dcc": "blender"})
    else:
        print(f"[Crucible Blender] Unknown type: '{t}'")


def process_queue():
    q = bpy.app.driver_namespace.get("CRUCIBLE_QUEUE")
    if q:
        while not q.empty():
            try:
                _dispatch(q.get_nowait())
            except Exception as e:
                print(f"[Crucible Blender] dispatch error: {e}")
    
    if bpy.app.driver_namespace.get("CRUCIBLE_RUNNING", False):
        return 0.1  # run again in 0.1 seconds
    return None  # stop timer


def _server_loop(srv_sock):
    srv_sock.settimeout(1.0)
    while bpy.app.driver_namespace.get("CRUCIBLE_RUNNING", False):
        try:
            conn, _ = srv_sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            with conn:
                length = int.from_bytes(_recv_exactly(conn, 4), "big")
                data   = json.loads(_recv_exactly(conn, length).decode("utf-8"))
                print(f"[Crucible Blender] Received packet: {data.get('type')}")
                q = bpy.app.driver_namespace.get("CRUCIBLE_QUEUE")
                if q:
                    q.put(data)
        except Exception as e:
            print(f"[Crucible Blender] recv error: {e}")


def toggle_server():
    is_running = bpy.app.driver_namespace.get("CRUCIBLE_RUNNING", False)
    
    if is_running:
        bpy.app.driver_namespace["CRUCIBLE_RUNNING"] = False
        old_sock = bpy.app.driver_namespace.get("CRUCIBLE_SOCKET")
        if old_sock:
            try: old_sock.close()
            except: pass
        bpy.app.driver_namespace["CRUCIBLE_SOCKET"] = None
        print("[Crucible Blender] LiveBridge STOPPED.")
        return

    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", _LISTEN_PORT))
        srv.listen(5)
    except OSError as e:
        print(f"[Crucible Blender] Cannot bind port {_LISTEN_PORT}: {e}")
        return

    bpy.app.driver_namespace["CRUCIBLE_RUNNING"] = True
    bpy.app.driver_namespace["CRUCIBLE_SOCKET"] = srv
    bpy.app.driver_namespace["CRUCIBLE_IS_UPDATING"] = False
    bpy.app.driver_namespace["CRUCIBLE_LAST_PUSH"] = 0.0
    if "CRUCIBLE_QUEUE" not in bpy.app.driver_namespace:
        bpy.app.driver_namespace["CRUCIBLE_QUEUE"] = queue.Queue()
    
    # Auto-configure Color Management to avoid AgX mismatch with Nuke
    try:
        scene = bpy.context.scene
        try:
            scene.view_settings.view_transform = "ACES 1.0 SDR-video"
            print("[Crucible Blender] View Transform set to ACES 1.0 SDR-video")
        except TypeError:
            try:
                scene.view_settings.view_transform = "Standard"
                print("[Crucible Blender] View Transform set to Standard (sRGB)")
            except TypeError: pass
        try:
            scene.sequencer_colorspace_settings.name = "ACEScg"
            print("[Crucible Blender] Working Space set to ACEScg")
        except TypeError: pass
    except Exception as e:
        print(f"[Crucible Blender] Color Management error: {e}")

    t = threading.Thread(
        target=_server_loop, args=(srv,), daemon=True, name="CrucibleBlenderBridge")
    t.start()
    bpy.app.driver_namespace["CRUCIBLE_THREAD"] = t

    if bpy.app.timers.is_registered(process_queue):
        bpy.app.timers.unregister(process_queue)
    bpy.app.timers.register(process_queue)
    
    handlers = bpy.app.handlers.depsgraph_update_post
    to_remove = [h for h in handlers if h.__name__ == "crucible_depsgraph_update"]
    for h in to_remove:
        handlers.remove(h)
    handlers.append(crucible_depsgraph_update)

    print(
        f"[Crucible Blender] LiveBridge RUNNING\n"
        f"  Listen: {_LISTEN_PORT} <- Nuke\n"
        f"  Send:   {_NUKE_HOST}:{_NUKE_PORT} -> Nuke"
    )

class CRUCIBLE_OT_toggle_server(bpy.types.Operator):
    bl_idname = "crucible.toggle_server"
    bl_label = "Toggle Server"
    
    def execute(self, context):
        toggle_server()
        return {'FINISHED'}

class CRUCIBLE_PT_live_bridge(bpy.types.Panel):
    bl_label = "Crucible LiveBridge"
    bl_idname = "CRUCIBLE_PT_live_bridge"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Crucible'
    
    def draw(self, context):
        layout = self.layout
        is_running = bpy.app.driver_namespace.get("CRUCIBLE_RUNNING", False)
        
        row = layout.row()
        row.scale_y = 1.5
        if is_running:
            row.operator("crucible.toggle_server", text="Stop Server (ON)", icon='PAUSE')
        else:
            row.operator("crucible.toggle_server", text="Start Server (OFF)", icon='PLAY')
            
        layout.separator()
        layout.label(text="Server Logs:")
        
        box = layout.box()
        logs = context.window_manager.crucible_logs
        if logs:
            for line in logs.split("\n"):
                box.label(text=line)
        else:
            box.label(text="No logs yet...")

def register():
    try: bpy.utils.register_class(CRUCIBLE_OT_toggle_server)
    except: pass
    try: bpy.utils.register_class(CRUCIBLE_PT_live_bridge)
    except: pass
    bpy.types.WindowManager.crucible_logs = bpy.props.StringProperty(default="")
    
def unregister():
    bpy.utils.unregister_class(CRUCIBLE_PT_live_bridge)
    bpy.utils.unregister_class(CRUCIBLE_OT_toggle_server)
    del bpy.types.WindowManager.crucible_logs

if __name__ == "__main__":
    register()
    # Auto-start on run
    if not bpy.app.driver_namespace.get("CRUCIBLE_RUNNING", False):
        toggle_server()
