import bpy
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
