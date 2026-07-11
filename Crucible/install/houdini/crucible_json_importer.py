import hou
import json

def import_crucible_lightmix():
    json_path = hou.ui.selectFile(title="Select Crucible LightMix JSON", pattern="*.json")
    if not json_path:
        return
        
    with open(hou.expandString(json_path), 'r') as f:
        data = json.load(f)
        
    multipliers = data.get("lighting_multipliers", {})
    engine = data.get("metadata", {}).get("target_engine", "Karma")
    
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
                else:
                    mult = data_dict
                    color = [1.0, 1.0, 1.0]

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
                        old_val = target_exp.eval()
                        import math
                        if mult > 0:
                            new_val = old_val + math.log2(mult)
                        else:
                            new_val = old_val - 100.0
                            
                        target_exp.set(new_val)
                        
                        ctrl_parm = node.parm(target_exp.name().replace("r5a", "control").replace("exposure", "exposure_control"))
                        if ctrl_parm: ctrl_parm.set(1)
                        
                        log_messages.append(f"[{name}] {target_exp.name()}: {old_val:.2f} -> {new_val:.2f}")
                        updated = True
                    except: pass

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
                        target_col.set((color[0], color[1], color[2]))
                        
                        ctrl_parm = node.parm(target_col.name().replace("r5a", "control").replace("color", "color_control"))
                        if ctrl_parm: ctrl_parm.set(1)
                        
                        log_messages.append(f"[{name}] Color Updated")
                        updated = True
                    except: pass
                
                if updated:
                    updated_count += 1
                    
    if updated_count > 0:
        hou.ui.displayMessage("Successfully updated! Overrode " + str(updated_count) + " lights.\n\nDetails:\n" + "\n".join(log_messages))
    else:
        hou.ui.displayMessage("Failed to find any matching parameters to update.")

import_crucible_lightmix()
