import nuke

def import_usd_stage():
    """
    Creates a GeoImport node to load a USD stage into Nuke's new 3D system.
    """
    filepath = nuke.getFilename("Select USD File", "*.usd *.usda *.usdc *.usdz")
    if not filepath:
        return
        
    geo = nuke.nodes.GeoImport(file=filepath)
    geo['label'].setValue("USD Stage")
    
    # Auto-frame the DAG
    nuke.zoom(1.0, [geo.xpos(), geo.ypos()])


def extract_usd_camera(source_node):
    """
    Extracts a Camera from a GeoImport or legacy ReadGeo node containing USD data.
    """
    if not source_node:
        nuke.message("Please select a GeoImport or ReadGeo node containing USD.")
        return
        
    node_class = source_node.Class()
    
    if node_class == "GeoImport":
        # Nuke 14+ USD System
        cam = nuke.nodes.Camera3()
        cam.setInput(0, source_node)
        cam['label'].setValue("Extracted USD Camera")
        cam.setXYpos(source_node.xpos() + 150, source_node.ypos())
        
        # We can't automatically select the prim path without knowing the USD structure,
        # but we can set up the node for the user.
        nuke.message("Camera3 node created and linked.\\nPlease select the specific Camera Prim Path in the Camera3 node properties.")
        
    elif node_class == "ReadGeo2" or node_class == "ReadGeo":
        # Legacy
        filepath = source_node['file'].value()
        if not filepath.lower().endswith(('.usd', '.usda', '.usdc', '.usdz')):
            nuke.message("Selected node does not appear to reference a USD file.")
            return
            
        cam = nuke.nodes.Camera2(file=filepath, read_from_file=True)
        cam['label'].setValue("Legacy USD Camera")
        cam.setXYpos(source_node.xpos() + 150, source_node.ypos())
    else:
        nuke.message("Selected node is not a GeoImport or ReadGeo node.")


def extract_usd_lights(source_node):
    """
    Sets up a USD light extraction workflow.
    """
    if not source_node or source_node.Class() != "GeoImport":
        nuke.message("Please select a GeoImport node containing USD lights.")
        return
        
    # In Nuke's new 3D system, you can use a GeoBindMaterial or just pass the USD lights 
    # directly into the scene. For specific extraction, artists often use a GeoScene node.
    scene = nuke.nodes.GeoScene()
    scene.setInput(0, source_node)
    scene.setXYpos(source_node.xpos(), source_node.ypos() + 100)
    
    nuke.message("GeoScene node connected.\\nUse the Scene graph to isolate Light prims.")


def configure_hydra_viewer():
    """
    Configures the current viewer to use the Hydra Storm renderer if applicable.
    """
    viewer = nuke.activeViewer()
    if not viewer:
        nuke.message("No active viewer found.")
        return
        
    viewer_node = viewer.node()
    
    # Nuke 14+ viewer has a 3D renderer dropdown
    if 'renderer' in viewer_node.knobs():
        # Values usually include: 'Nuke', 'Hydra'
        try:
            viewer_node['renderer'].setValue('Hydra')
            nuke.message("Viewer configured to use Hydra renderer.")
        except Exception as e:
            nuke.message(f"Could not set Hydra renderer: {e}")
    else:
        nuke.message("Your Nuke version/viewer does not support direct Hydra renderer toggling via this knob.")


def create_usd_lookdev_rig(source_node):
    """
    Builds a basic 3-point USD lighting rig + HDRI Environment for unlit stages.
    """
    if not source_node:
        nuke.message("Please select a GeoImport or USD node to attach the LookDev rig to.")
        return
        
    base_x = source_node.xpos()
    base_y = source_node.ypos()
    
    # Create the environment light
    env_light = nuke.nodes.EnvironmentLight(inputs=[])
    env_light['label'].setValue("Ambient / HDRI")
    env_light.setXYpos(base_x - 150, base_y + 100)
    
    # Create a Direct Light (Key light)
    key_light = nuke.nodes.DirectLight(inputs=[])
    key_light['label'].setValue("Key Light")
    key_light['intensity'].setValue(2.0)
    key_light.setXYpos(base_x + 150, base_y + 100)
    
    # Create a GeoScene to merge lights
    light_scene = nuke.nodes.GeoScene(inputs=[env_light, key_light])
    light_scene['label'].setValue("LookDev Lights")
    light_scene.setXYpos(base_x, base_y + 150)
    
    # Merge the lights with the user's USD geometry
    master_scene = nuke.nodes.GeoScene(inputs=[source_node, light_scene])
    master_scene.setXYpos(base_x, base_y + 200)
    
    # Backdrop
    bd = nuke.nodes.BackdropNode()
    bd['label'].setValue("USD LookDev Rig")
    bd['note_font_size'].setValue(18)
    bd['xpos'].setValue(base_x - 170)
    bd['ypos'].setValue(base_y + 50)
    bd['bdwidth'].setValue(450)
    bd['bdheight'].setValue(220)
    
    for n in nuke.selectedNodes():
        n.setSelected(False)
    master_scene.setSelected(True)
    
    nuke.message("LookDev Rig created! Connect an HDRI map to the EnvironmentLight if desired.")
