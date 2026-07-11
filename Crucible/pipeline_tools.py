import nuke
import os
import re

def check_color_spaces():
    """Scans script for potential OCIO/ACES color space violations."""
    issues = []
    
    # Try to detect if the script is even using OCIO
    color_mgt = nuke.root()['colorManagement'].value()
    if color_mgt == 'Nuke':
        issues.append("⚠️ <b>Warning:</b> Script is using legacy Nuke color management, not OCIO/ACES!")
        
    for node in nuke.allNodes():
        if node.Class() in ['Read', 'Write']:
            colorspace = node['colorspace'].value()
            file_path = node['file'].evaluate()
            
            # Common ACES violations
            if file_path.lower().endswith(('.jpg', '.png', '.jpeg')):
                if 'sRGB' not in colorspace and 'Utility - sRGB' not in colorspace:
                    issues.append(f"❌ <b>[{node.name()}]</b> JPG/PNG is not using an sRGB input space. Current: {colorspace}")
            elif file_path.lower().endswith('.exr'):
                if 'ACEScg' not in colorspace and 'linear' not in colorspace.lower():
                    issues.append(f"⚠️ <b>[{node.name()}]</b> EXR is not assigned to ACEScg or Linear. Current: {colorspace}")
                    
    if not issues:
        nuke.message("<b>✅ Color Space Check PASSED</b><br>No obvious OCIO violations found.")
    else:
        nuke.message("<b>🎨 Color Management Report</b><br><br>" + "<br>".join(issues))


def _get_version_info(file_path):
    """Helper to extract version number and directory from a path."""
    match = re.search(r'(_v\d+)', file_path, re.IGNORECASE)
    if not match:
        return None, None, None
    version_str = match.group(1)
    return file_path, version_str, file_path.replace(version_str, "{V_TOKEN}")


def change_version(node, direction='up'):
    """Changes the version of the selected Read/Write node, or the Nuke script if no node is selected."""
    is_script = False
    
    if not node:
        # Version up the Nuke script itself
        file_path = nuke.root().name()
        if not file_path or file_path == 'Root':
            nuke.message("Please save the Nuke script first.")
            return
        is_script = True
    else:
        if 'file' not in node.knobs():
            nuke.message("Selected node does not have a 'file' knob.")
            return
        file_path = node['file'].value()
        
    _, current_v, token_path = _get_version_info(file_path)
    
    if not current_v:
        if is_script:
            nuke.message(f"No standard versioning (e.g. _v001) found in the script name:\n{file_path}")
        else:
            nuke.message(f"No standard versioning (e.g. _v001) found in the node's file path:\n{file_path}")
        return
        
    # Extract integer
    v_num = int(current_v.lower().replace('_v', ''))
    
    if direction == 'up':
        new_v_num = v_num + 1
    elif direction == 'down':
        new_v_num = max(1, v_num - 1)
    elif direction == 'latest':
        # Scan directory for highest version
        if is_script:
            dir_path = os.path.dirname(file_path)
        else:
            dir_path = os.path.dirname(node['file'].evaluate())
            
        if not os.path.exists(dir_path):
            # Try ascending directory tree to find parent version folder
            parent_dir = os.path.dirname(dir_path)
            if not os.path.exists(parent_dir):
                nuke.message("Directory does not exist on disk.")
                return
            dir_path = parent_dir
            
        highest = v_num
        for item in os.listdir(dir_path):
            match = re.search(r'_v(\d+)', item, re.IGNORECASE)
            if match:
                found_v = int(match.group(1))
                if found_v > highest:
                    highest = found_v
        new_v_num = highest
        
    if new_v_num == v_num:
        nuke.message(f"Already at version {v_num}.")
        return
        
    # Format back to _v###
    padding = len(current_v) - 2 # usually 3 for v001
    new_v_str = f"_v{new_v_num:0{padding}d}"
    
    new_file_path = token_path.replace("{V_TOKEN}", new_v_str)
    
    if is_script:
        # Save the new script version
        nuke.scriptSaveAs(new_file_path)
        print(f"Crucible: Script saved as {new_v_str}")
    else:
        # Update the node
        node['file'].setValue(new_file_path)
        if 'reload' in node.knobs():
            node['reload'].execute()
        print(f"Crucible: Node '{node.name()}' version changed to {new_v_str}")


def build_slap_comp():
    """Builds a complete Auto-Comp with LightWrap and Match Stack."""
    nodes = nuke.selectedNodes()
    cg_node = None
    plate_node = None
    
    # QoL Pipeline Improvement: If a single node is selected (like a Merge), try to grab its inputs
    if len(nodes) == 1 and nodes[0].Class() in ['Merge2', 'Merge']:
        sel_node = nodes[0]
        # In Nuke, Merge B input is 0 (Plate), A input is 1 (CG)
        if sel_node.inputs() >= 2 and sel_node.input(0) is not None and sel_node.input(1) is not None:
            plate_node = sel_node.input(0)
            cg_node = sel_node.input(1)
            nodes = [cg_node, plate_node]
            
    if len(nodes) != 2:
        nuke.message("Please select exactly TWO nodes (1 CG stream, 1 Plate stream)\nOR a single Merge node connecting them.")
        return
        
    # If not assigned by the Merge bypass, use heuristic to guess CG vs Plate
    if not cg_node or not plate_node:
        for n in nodes:
            name = n.name().lower()
            file_path = n['file'].value().lower() if 'file' in n.knobs() else ""
            
            is_cg = any(x in name for x in ['cg', 'render', 'beauty'])
            is_plate = any(x in name for x in ['plate', 'bg', 'bgnd'])
            
            if is_cg and not cg_node:
                cg_node = n
            elif is_plate and not plate_node:
                plate_node = n
            elif file_path.endswith('.exr') and not cg_node and not plate_node:
                cg_node = n
            else:
                if not plate_node:
                    plate_node = n
                else:
                    cg_node = n
                    
        # Fallback to arbitrary assignment if still unresolved
        if not cg_node or not plate_node:
            cg_node, plate_node = nodes[0], nodes[1]
        
    base_x = cg_node.xpos()
    base_y = max(cg_node.ypos(), plate_node.ypos()) + 150
    
    # Format match safely
    try:
        plate_format = plate_node.format().name()
    except Exception:
        # Fallback if node has no format method or is in error state
        plate_format = "HD_1080"
        
    reformat = nuke.nodes.Reformat(inputs=[cg_node], format=plate_format)
    reformat.setXYpos(base_x, base_y)
    
    # Import integration tools dynamically to avoid circular import issues if they exist
    import crucible.integration_tools as itools
    
    # Premult CG
    premult = nuke.nodes.Premult(inputs=[reformat])
    
    # Add Smart LightWrap
    smart_wrap = itools.create_light_wrap(premult)
    smart_wrap.setInput(1, plate_node)  # Connect BG input to plate
    
    # Merge Over Plate
    # In Nuke's Python API, inputs=[B, A] maps input 0 to Plate and input 1 to CG.
    merge_over = nuke.nodes.Merge2(inputs=[plate_node, smart_wrap], operation='over', label="Slap Comp")
    
    # Add Optical Stack (Removed ZDefocus per user request)
    grain = nuke.nodes.F_ReGrain(inputs=[merge_over], label="Plate Grain Match")
    
    # Setup Write node in an OUT folder next to the Nuke script
    script_path = nuke.root().name()
    if script_path != 'Root':
        script_dir = os.path.dirname(script_path)
        script_name = os.path.splitext(os.path.basename(script_path))[0]
        
        # Ensure script_name contains a version string for the version up/down tools
        import re
        if not re.search(r'(_v\d+)', script_name, re.IGNORECASE):
            script_name = f"{script_name}_v001"
            
        out_dir = os.path.join(script_dir, "OUT")
        
        # Create a version-specific subfolder to keep renders organized
        # e.g., OUT/shot_v001/shot_v001_slapcomp_%04d.exr
        render_path = os.path.join(out_dir, script_name, f"{script_name}_slapcomp_%04d.exr").replace('\\', '/')
    else:
        # Fallback if script is not saved
        import tempfile
        out_dir = os.path.join(tempfile.gettempdir(), "Crucible_OUT")
        render_path = os.path.join(out_dir, "slapcomp_v001", "slapcomp_v001_%04d.exr").replace('\\', '/')
        
    write_node = nuke.nodes.Write(inputs=[grain], label="SlapComp Output")
    write_node['file'].setValue(render_path)
    write_node['file_type'].setValue("exr")
    write_node['datatype'].setValue("16 bit half")
    write_node['compression'].setValue("Zip (1 scanline)")
    
    # Ensure Nuke automatically creates the directories when rendering new versions
    try:
        write_node['create_directories'].setValue(True)
    except:
        # Fallback for older Nuke versions
        write_node['beforeRender'].setValue("import os; d = os.path.dirname(nuke.thisNode()['file'].evaluate()); os.makedirs(d) if not os.path.exists(d) else None")
    
    # Align nodes
    premult.setXYpos(base_x, base_y + 50)
    smart_wrap.setXYpos(base_x, base_y + 100)
    merge_over.setXYpos(base_x, base_y + 150)
    grain.setXYpos(base_x, base_y + 250)
    write_node.setXYpos(base_x, base_y + 350)
    
    nuke.message("Slap Comp generated successfully with Versioning Support!")


def _get_vec3(knob):
    """Helper to extract exactly 3 float values from a Nuke knob."""
    val = knob.value()
    if isinstance(val, (int, float)):
        return [float(val), float(val), float(val)]
    return [float(val[0]), float(val[1]), float(val[2])]


def export_cdl_from_node():
    """Exports a standard .cdl file from the selected OCIOCDLTransform or Grade node."""
    nodes = nuke.selectedNodes()
    if not nodes:
        nuke.message("Please select an OCIOCDLTransform or Grade node.")
        return
        
    node = nodes[0]
    
    slope = [1.0, 1.0, 1.0]
    offset = [0.0, 0.0, 0.0]
    power = [1.0, 1.0, 1.0]
    saturation = 1.0
    
    if node.Class() == "OCIOCDLTransform":
        slope = _get_vec3(node['slope'])
        offset = _get_vec3(node['offset'])
        power = _get_vec3(node['power'])
        sat_val = node['saturation'].value()
        saturation = float(sat_val) if isinstance(sat_val, (int, float)) else float(sat_val[0])
    elif node.Class() == "Grade":
        # Grade node mapping: Multiply -> Slope, Add -> Offset, Gamma -> 1/Power
        if node['multiply'].hasExpression() or node['multiply'].isAnimated():
            print("Crucible Warning: Grade node multiply is animated, exporting current frame only.")
            
        slope = _get_vec3(node['multiply'])
        offset = _get_vec3(node['add'])
        gamma = _get_vec3(node['gamma'])
        power = [1.0/max(g, 0.0001) for g in gamma]
    else:
        nuke.message("Please select an OCIOCDLTransform or Grade node.")
        return
        
    root_name = nuke.root().name()
    default_dir = os.path.dirname(root_name) if root_name != 'Root' else ''
    default_path = os.path.join(default_dir, "{}.cdl".format(node.name()))
    
    export_path = nuke.getFilename("Export CDL", "*.cdl", default=default_path)
    if not export_path:
        return
        
    if not export_path.endswith('.cdl'):
        export_path += '.cdl'
        
    xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<ColorDecisionList xmlns="urn:ASC:CDL:v1.01">
  <ColorDecision>
    <ColorCorrection>
      <SOPNode>
        <Slope>{s[0]:.6f} {s[1]:.6f} {s[2]:.6f}</Slope>
        <Offset>{o[0]:.6f} {o[1]:.6f} {o[2]:.6f}</Offset>
        <Power>{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}</Power>
      </SOPNode>
      <SatNode>
        <Saturation>{sat:.6f}</Saturation>
      </SatNode>
    </ColorCorrection>
  </ColorDecision>
</ColorDecisionList>
'''.format(s=slope, o=offset, p=power, sat=saturation)

    try:
        with open(export_path, 'w') as f:
            f.write(xml_content)
        nuke.message("Successfully exported CDL to:\n{}".format(export_path))
    except Exception as e:
        nuke.message("Failed to export CDL:\n{}".format(e))


def launch_scopes():
    """Builds a custom GPU-accelerated RGB Waveform Scope using BlinkScript."""
    nodes = nuke.selectedNodes()
    if not nodes:
        nuke.message("Please select a node to attach the Waveform Scope.")
        return
        
    src_node = nodes[0]
    
    blink_code = """kernel WaveformScope : ImageComputationKernel<ePixelWise> {
  Image<eRead, eAccessRandom, eEdgeClamped> src;
  Image<eWrite> dst;

  param:
    float intensity_scale;
    float gain;
    float threshold;

  local:
    int srcYMin;
    int srcYMax;
    float outYMax;

  void define() {
    defineParam(intensity_scale, "Signal Range", 1.0f);
    defineParam(gain, "Scope Brightness", 0.05f);
    defineParam(threshold, "Scope Sharpness", 1.0f);
  }

  void init() {
    srcYMin = src.bounds.yMin;
    srcYMax = src.bounds.yMax;
    outYMax = (float)(dst.bounds.yMax - dst.bounds.yMin);
  }

  void process(int2 pos) {
    float r = 0.0f;
    float g = 0.0f;
    float b = 0.0f;

    float target_v = (float)(pos.y - dst.bounds.yMin) / outYMax;
    target_v *= intensity_scale;

    float tol = (threshold * intensity_scale) / outYMax;

    for (int y = srcYMin; y < srcYMax; y++) {
      SampleType(src) col = src(pos.x, y);
      if (fabs(col.x - target_v) <= tol) r += gain;
      if (fabs(col.y - target_v) <= tol) g += gain;
      if (fabs(col.z - target_v) <= tol) b += gain;
    }

    dst() = float4(r, g, b, 1.0f);
  }
}"""

    # Create Group wrapper to keep things clean
    group = nuke.nodes.Group(name="Crucible_Waveform")
    group.setInput(0, src_node)
    
    with group:
        inp = nuke.nodes.Input()
        
        # Add a Reformat so the waveform scope fits cleanly on screen
        fmt = nuke.nodes.Reformat(inputs=[inp])
        fmt['type'].setValue("to box")
        fmt['box_width'].setValue(1920)
        fmt['box_height'].setValue(1080)
        fmt['box_fixed'].setValue(True)
        
        blink = nuke.nodes.BlinkScript(inputs=[fmt])
        blink['kernelSource'].setValue(blink_code)
        blink.knob('recompile').execute()
        
        # Expose controls to the Group node
        group.addKnob(nuke.Tab_Knob("Waveform Settings"))
        
        # Add actual Float_Knobs to the Group, and expression link them down to the Blink node
        # This is much safer than Link_Knobs across compile states.
        k_scale = nuke.Double_Knob("intensity_scale", "Signal Range")
        k_scale.setValue(1.0)
        group.addKnob(k_scale)
        
        k_gain = nuke.Double_Knob("gain", "Scope Brightness")
        k_gain.setValue(0.05)
        group.addKnob(k_gain)
        
        k_thresh = nuke.Double_Knob("threshold", "Scope Sharpness")
        k_thresh.setValue(1.0)
        group.addKnob(k_thresh)
        
        # We wrap in a try-except just in case the Blink compile lags behind the script execution
        try:
            blink['intensity_scale'].setExpression("parent.intensity_scale")
            blink['gain'].setExpression("parent.gain")
            blink['threshold'].setExpression("parent.threshold")
        except Exception as e:
            nuke.message(f"Crucible Notice: Please manually link the Group parameters to the inner BlinkScript node. ({e})")
        
        out = nuke.nodes.Output(inputs=[blink])
        
    group.setXYpos(src_node.xpos() + 150, src_node.ypos())
    group['tile_color'].setValue(int('0x8e44adff', 16))
    nuke.message("Successfully built a real-time GPU Waveform Scope node!")
