import os
import json
import nuke
import stat

def export_lightmix_json(file_path, export_data, software, engine):
    """Exports the LightMix multipliers along with target 3D software metadata."""
    payload = {
        "metadata": {
            "source": "Crucible VFX Toolkit",
            "target_software": software,
            "target_engine": engine
        },
        "lighting_multipliers": export_data
    }
    
    try:
        with open(file_path, 'w') as f:
            json.dump(payload, f, indent=4)
        nuke.message("3D Lighting Data exported successfully!\n\nTarget: {} ({})".format(software, engine))
    except Exception as e:
        nuke.message("Failed to export 3D data:\n{}".format(e))


def generate_bridge_scripts():
    """Generates the Python scripts for Houdini, Maya, and Blender and saves them to disk."""
    # We will save them in a 'bridges' folder next to the script, or in the Crucible install dir.
    crucible_dir = os.path.dirname(os.path.abspath(__file__))
    bridge_dir = os.path.join(crucible_dir, "3D_Bridges")
    
    if not os.path.exists(bridge_dir):
        os.makedirs(bridge_dir)
        
    # --- HOUDINI SCRIPT ---
    houdini_script = """import hou
import json

def import_crucible_lightmix():
    json_path = hou.ui.selectFile(title="Select Crucible LightMix JSON", pattern="*.json")
    if not json_path:
        return
        
    with open(hou.expandString(json_path), 'r') as f:
        data = json.load(f)
        
    apply_mode = hou.ui.displayMessage(
        "How would you like to apply the Crucible LightMix grades?",
        buttons=('Multiply / Add to Existing (Match Nuke)', 'Overwrite Existing', 'Cancel'),
        default_choice=0,
        close_choice=2,
        title="Crucible LightMix",
        help="IMPORTANT: To perfectly match what you see in Nuke, choose 'Multiply / Add'.\nNuke grades are multipliers on top of your existing renders. Overwriting will destroy your base light values!"
    )
    if apply_mode == 2: return
    is_additive = (apply_mode == 0)
    
    multipliers = data.get("lighting_multipliers", {})
    
    updated_count = 0
    log_messages = []
    
    with hou.undos.group("Crucible LightMix"):
        for node in hou.node('/').allSubChildren():
            node_type = node.type().name().lower()
            if 'light' not in node_type and 'env' not in node_type and 'sun' not in node_type:
                continue
                
            name = node.name().lower()
            
            matching_keys = []
            # 1. Match Node Name (stripping standard AOV prefixes from the JSON keys)
            for k in multipliers.keys():
                clean_k = k.lower()
                if clean_k.startswith("c_"): clean_k = clean_k[2:]
                elif clean_k.startswith("rgba_"): clean_k = clean_k[5:]
                
                if name == clean_k:
                    matching_keys.append(k)
            
            # 2. If no match on Node Name, check Solaris Primpattern (e.g. '/lights/sun_houses')
            if not matching_keys:
                primpattern = node.parm("primpattern")
                if primpattern:
                    pp_val = primpattern.eval().lower()
                    leaf_name = pp_val.split("/")[-1] # Gets 'sun_houses' from '/lights/sun_houses'
                    
                    for k in multipliers.keys():
                        clean_k = k.lower()
                        if clean_k.startswith("c_"): clean_k = clean_k[2:]
                        elif clean_k.startswith("rgba_"): clean_k = clean_k[5:]
                        
                        if leaf_name == clean_k:
                            matching_keys.append(k)
            
            if matching_keys:
                data_dict = multipliers[matching_keys[0]]
                if isinstance(data_dict, dict):
                    mult = data_dict.get("multiplier", 1.0)
                    color = data_dict.get("color", [1.0, 1.0, 1.0])
                    animated = data_dict.get("animated", False)
                    frames = data_dict.get("frames", [])
                    multipliers_arr = data_dict.get("multipliers", [])
                    colors_arr = data_dict.get("colors", [])
                else:
                    mult = data_dict
                    color = [1.0, 1.0, 1.0]
                    animated = False

                updated = False
                
                # 1. Update Exposure
                target_exp = None
                # Prioritize exact names to avoid hitting wrong parameters (like 'shadow_exposure' if it existed)
                for en in ['exposure', 'ar_exposure', 'xn__inputsexposure_v3a', 'inputs:exposure', 'xn__inputsexposure_control']:
                    if node.parm(en) is not None:
                        target_exp = node.parm(en)
                        break
                
                if not target_exp:
                    for parm in node.parms():
                        p_name = parm.name().lower()
                        if 'exposure' in p_name and 'enable' not in p_name and 'control' not in p_name:
                            target_exp = parm
                            break
                            
                if target_exp:
                    try:
                        import math
                        
                        if animated and frames:
                            for f, m in zip(frames, multipliers_arr):
                                a_m = abs(m)
                                nv = math.log2(a_m) if a_m > 0 else -100.0
                                target_exp.setKeyframe(hou.Keyframe(nv, float(f)))
                            new_val_log = f"animated ({len(frames)} keys)"
                        else:
                            abs_mult = abs(mult)
                            if abs_mult > 0:
                                new_val = math.log2(abs_mult)
                            else:
                                new_val = -100.0
                            target_exp.set(new_val)
                            new_val_log = f"{new_val:.2f}"
                        
                        ctrl_parm = None
                        base_name = target_exp.name()
                        for cand in (
                            base_name.replace("r5a", "control").replace("exposure", "exposure_control"),
                            base_name + "_control",
                            "edit_" + base_name + "_control",
                            base_name.replace("_v3a", "").replace("exposure", "exposure_control"),
                        ):
                            ctrl_parm = node.parm(cand)
                            if ctrl_parm: break
                            
                        if not ctrl_parm:
                            for p in node.parms():
                                pn = p.name().lower()
                                if "exposure" in pn and "control" in pn:
                                    ctrl_parm = p
                                    break
                                    
                        if ctrl_parm:
                            try:
                                labels = ctrl_parm.menuLabels()
                                items = ctrl_parm.menuItems()
                                if is_additive:
                                    idx = 2
                                    for i, lbl in enumerate(labels):
                                        if "Add" in lbl: idx = i; break
                                else:
                                    idx = 0
                                    for i, lbl in enumerate(labels):
                                        if "Set" in lbl and "Exists" not in lbl: idx = i; break
                                if idx < len(items):
                                    ctrl_parm.set(items[idx])
                            except Exception: pass
                        
                        log_messages.append(f"[{name}] {target_exp.name()} -> {new_val_log} ({'add' if is_additive else 'set'})")
                        updated = True
                    except Exception as e:
                        print(f"[Crucible] Error on {name}: {e}")
                        pass

                # 2. Update Color
                target_col = None
                for cn in ['color', 'light_color', 'ar_color', 'xn__inputscolor_v3a', 'inputs:color', 'xn__inputscolor_control']:
                    if node.parmTuple(cn) is not None and len(node.parmTuple(cn)) >= 3:
                        target_col = node.parmTuple(cn)
                        break
                        
                if not target_col:
                    for parm_tuple in node.parmTuples():
                        t_name = parm_tuple.name().lower()
                        if 'color' in t_name and 'shadow' not in t_name and 'guide' not in t_name and len(parm_tuple) >= 3 and 'enable' not in t_name and 'temperature' not in t_name and 'control' not in t_name:
                            target_col = parm_tuple
                            break
                            
                if target_col:
                    try:
                        if animated and frames:
                            for f, m, c in zip(frames, multipliers_arr, colors_arr):
                                cs = -1.0 if m < 0 else 1.0
                                nc = (c[0]*cs, c[1]*cs, c[2]*cs)
                                # setKeyframe requires a Keyframe object or tuple? For parmTuple, it might be tricky.
                                # Instead, set the frame, then set the value.
                                # BUT parmTuple doesn't have setKeyframe. We must setKeyframe on the individual parms.
                                for i, comp in enumerate(nc):
                                    if i < len(target_col):
                                        target_col[i].setKeyframe(hou.Keyframe(comp, float(f)))
                        else:
                            color_sign = -1.0 if mult < 0 else 1.0
                            new_c = (color[0] * color_sign, color[1] * color_sign, color[2] * color_sign)
                            target_col.set(new_c)
                        
                        ctrl_parm = None
                        base_name = target_col.name()
                        for cand in (
                            base_name.replace("r5a", "control").replace("color", "color_control"),
                            base_name + "_control",
                            "edit_" + base_name + "_control",
                            base_name.replace("_v3a", "").replace("color", "color_control"),
                        ):
                            ctrl_parm = node.parm(cand)
                            if ctrl_parm: break
                            
                        if not ctrl_parm:
                            for p in node.parms():
                                pn = p.name().lower()
                                if "color" in pn and "control" in pn and "temperature" not in pn:
                                    ctrl_parm = p
                                    break
                                    
                        if ctrl_parm:
                            try:
                                labels = ctrl_parm.menuLabels()
                                items = ctrl_parm.menuItems()
                                if is_additive:
                                    idx = 3
                                    for i, lbl in enumerate(labels):
                                        if "Multiply" in lbl: idx = i; break
                                else:
                                    idx = 0
                                    for i, lbl in enumerate(labels):
                                        if "Set" in lbl and "Exists" not in lbl: idx = i; break
                                if idx < len(items):
                                    ctrl_parm.set(items[idx])
                            except Exception: pass
                        
                        log_messages.append(f"[{name}] Color Updated ({'mult' if is_additive else 'set'})")
                        updated = True
                    except Exception as e:
                        print(f"[Crucible] Error on {name}: {e}")
                        pass
                
                if updated:
                    updated_count += 1
                    
    if updated_count > 0:
        hou.ui.displayMessage("Successfully updated! Overrode " + str(updated_count) + " lights.\\n\\nDetails:\\n" + "\\n".join(log_messages))
    else:
        hou.ui.displayMessage("Failed to find any matching parameters to update.")

import_crucible_lightmix()
"""

    # --- MAYA SCRIPT ---
    maya_script = """import maya.cmds as cmds
import json

def import_crucible_lightmix():
    json_path = cmds.fileDialog2(fileFilter="JSON Files (*.json)", dialogStyle=2, fileMode=1, caption="Select Crucible LightMix JSON")
    if not json_path:
        return
        
    with open(json_path[0], 'r') as f:
        data = json.load(f)
        
    multipliers = data.get("lighting_multipliers", {})
    engine = data.get("metadata", {}).get("target_engine", "Arnold")
    
    updated_count = 0
    for light_name, data_dict in multipliers.items():
        if isinstance(data_dict, dict):
            mult = data_dict.get("multiplier", 1.0)
            color = data_dict.get("color", [1.0, 1.0, 1.0])
        else:
            mult = data_dict
            color = [1.0, 1.0, 1.0]
            
        if cmds.objExists(light_name):
            # Determine attribute based on engine
            if engine == "Arnold":
                attr = f"{light_name}.aiExposure" if cmds.objExists(f"{light_name}.aiExposure") else f"{light_name}.intensity"
                color_attr = f"{light_name}.color"
            elif engine == "V-Ray":
                attr = f"{light_name}.intensityMult"
                color_attr = f"{light_name}.lightColor"
            elif engine == "Redshift":
                attr = f"{light_name}.multiplier"
                color_attr = f"{light_name}.color"
            else:
                attr = f"{light_name}.intensity"
                color_attr = f"{light_name}.color"
                
            if cmds.objExists(attr):
                current = cmds.getAttr(attr)
                cmds.setAttr(attr, current * mult)
                if cmds.objExists(color_attr):
                    cmds.setAttr(color_attr, color[0], color[1], color[2], type="double3")
                print(f"[Crucible] Updated {light_name} -> {attr} multiplied by {mult}")
                updated_count += 1
            else:
                print(f"[Crucible] Attribute not found for {light_name} ({engine})")
        else:
            print(f"[Crucible] Light {light_name} not found in scene.")
            
    cmds.confirmDialog(title='Crucible Bridge', message=f'Applied LightMix to {updated_count} lights.', button=['OK'])

import_crucible_lightmix()
"""

    # --- BLENDER SCRIPT ---
    blender_script = """import bpy
import json
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator

class CRUCIBLE_OT_import_lightmix(Operator, ImportHelper):
    bl_idname = "crucible.import_lightmix"
    bl_label = "Import Crucible LightMix"
    filename_ext = ".json"
    
    def execute(self, context):
        with open(self.filepath, 'r') as f:
            data = json.load(f)
            
        multipliers = data.get("lighting_multipliers", {})
        engine = data.get("metadata", {}).get("target_engine", "Cycles")
        
        updated = 0
        for light_name, data_dict in multipliers.items():
            if isinstance(data_dict, dict):
                mult = data_dict.get("multiplier", 1.0)
                color = data_dict.get("color", [1.0, 1.0, 1.0])
            else:
                mult = data_dict
                color = [1.0, 1.0, 1.0]
                
            if light_name in bpy.data.lights:
                light = bpy.data.lights[light_name]
                if engine == "Cycles" and hasattr(light, 'cycles'):
                    # Cycles nodes
                    if light.use_nodes and light.node_tree:
                        for node in light.node_tree.nodes:
                            if node.type == 'EMISSION':
                                current = node.inputs['Strength'].default_value
                                node.inputs['Strength'].default_value = current * mult
                                node.inputs['Color'].default_value = (color[0], color[1], color[2], 1.0)
                                updated += 1
                else:
                    # Standard Eevee/Blender energy
                    light.energy = light.energy * mult
                    light.color = (color[0], color[1], color[2])
                    updated += 1
                    
        self.report({'INFO'}, f"Crucible LightMix applied to {updated} lights.")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(CRUCIBLE_OT_import_lightmix)
def unregister():
    bpy.utils.unregister_class(CRUCIBLE_OT_import_lightmix)

if __name__ == "__main__":
    register()
    bpy.ops.crucible.import_lightmix('INVOKE_DEFAULT')
"""

    # Write files
    h_path = os.path.join(bridge_dir, "Houdini_Crucible_Importer.py")
    m_path = os.path.join(bridge_dir, "Maya_Crucible_Importer.py")
    b_path = os.path.join(bridge_dir, "Blender_Crucible_Importer.py")
    
    with open(h_path, 'w') as f: f.write(houdini_script)
    with open(m_path, 'w') as f: f.write(maya_script)
    with open(b_path, 'w') as f: f.write(blender_script)
    
    # Create installation instructions
    readme = """CRUCIBLE 3D BRIDGE INSTALLATION
=================================

HOUDINI:
1. Open Houdini.
2. Create a new Shelf Tool.
3. Name it "Crucible LightMix".
4. Copy and paste the contents of 'Houdini_Crucible_Importer.py' into the Script tab.
5. Click Accept. You can now click this button in Solaris to import your Nuke comps!

MAYA:
1. Open Maya.
2. Open the Script Editor (Python tab).
3. Copy and paste the contents of 'Maya_Crucible_Importer.py'.
4. Highlight the text and Middle-Mouse-Drag it to your custom shelf to create a button.

BLENDER:
1. Open Blender.
2. Go to the Scripting workspace.
3. Open 'Blender_Crucible_Importer.py' and click "Run Script".
4. It will immediately prompt you to select your JSON file and apply it.
"""
    with open(os.path.join(bridge_dir, "INSTALL_INSTRUCTIONS.txt"), 'w') as f:
        f.write(readme)
        
    nuke.message(f"Bridge Scripts Generated Successfully!\n\nSaved to:\n{bridge_dir}\n\nPlease check INSTALL_INSTRUCTIONS.txt")
    
    # Try to open the directory automatically
    try:
        import subprocess
        import sys
        if sys.platform == 'win32':
            os.startfile(bridge_dir)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', bridge_dir])
        else:
            subprocess.Popen(['xdg-open', bridge_dir])
    except:
        pass
