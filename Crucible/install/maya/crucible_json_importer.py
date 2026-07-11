import maya.cmds as cmds
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
