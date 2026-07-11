import nuke

def create_deep_matte(source_node):
    """Slices Deep data at a specific Z-depth to create a flat 2D matte."""
    if not source_node or 'Deep' not in source_node.Class():
        # Heuristic: sometimes DeepReads are just called DeepRead, but let's just warn
        pass
        
    base_x = source_node.xpos() if source_node else 0
    base_y = source_node.ypos() + 100 if source_node else 0
    
    expr = nuke.nodes.DeepExpression(inputs=[source_node] if source_node else None)
    expr['label'].setValue("Deep Z-Slice\nAdjust Z-Front / Z-Back")
    # A standard deep slice expression:
    # If the deep sample is between Z_front and Z_back, keep alpha, else 0
    expr.addKnob(nuke.Double_Knob("slice_z", "Slice Z"))
    expr['slice_z'].setValue(100.0)
    expr.addKnob(nuke.Double_Knob("slice_thickness", "Thickness"))
    expr['slice_thickness'].setValue(10.0)
    
    expr['chans0'].setValue('deep')
    expr['chans1'].setValue('none')
    
    # deep.front > (slice_z - thickness) && deep.back < (slice_z + thickness) ? rgba.alpha : 0
    expr['deep.front'].setExpression("deep.front > (slice_z - slice_thickness) && deep.front < (slice_z + slice_thickness) ? deep.front : 0")
    expr['rgba.alpha'].setExpression("deep.front > 0 ? rgba.alpha : 0")
    
    deep_to_image = nuke.nodes.DeepToImage(inputs=[expr])
    deep_to_image.setXYpos(base_x, base_y + 50)
    
    return deep_to_image


def create_deep_holdout(source_node):
    """
    Builds a production-grade Deep Volume Slicer (Holdout) rig.
    Splits a deep volume into Foreground and Background 2D streams at a specific Z-depth,
    allowing 2D elements to be perfectly sandwiched inside the volume.
    """
    if not source_node:
        nuke.message("Please select a Deep node to split.")
        return None
        
    base_x = source_node.xpos()
    base_y = source_node.ypos()
    
    # Controller
    ctrl = nuke.nodes.NoOp()
    ctrl['name'].setValue("Deep_Slicer_Ctrl")
    ctrl['label'].setValue("Z-Depth Split")
    ctrl['tile_color'].setValue(int("0x8e44adff", 16))
    k_z = nuke.Double_Knob("split_z", "Split Z-Depth")
    k_z.setRange(0, 1000)
    k_z.setValue(100.0)
    ctrl.addKnob(k_z)
    ctrl.setXYpos(base_x + 150, base_y + 50)
    
    # FG Crop
    fg_crop = nuke.nodes.DeepCrop(inputs=[source_node])
    fg_crop['use_znear'].setValue(False)
    fg_crop['use_zfar'].setValue(True)
    fg_crop['zfar'].setExpression(f"{ctrl.name()}.split_z")
    fg_crop['label'].setValue("Foreground Volume")
    fg_crop.setXYpos(base_x - 100, base_y + 100)
    
    # BG Crop
    bg_crop = nuke.nodes.DeepCrop(inputs=[source_node])
    bg_crop['use_znear'].setValue(True)
    bg_crop['znear'].setExpression(f"{ctrl.name()}.split_z")
    bg_crop['use_zfar'].setValue(False)
    bg_crop['label'].setValue("Background Volume")
    bg_crop.setXYpos(base_x + 100, base_y + 100)
    
    # Convert to Images
    fg_to_image = nuke.nodes.DeepToImage(inputs=[fg_crop])
    fg_to_image.setXYpos(base_x - 100, base_y + 160)
    
    bg_to_image = nuke.nodes.DeepToImage(inputs=[bg_crop])
    bg_to_image.setXYpos(base_x + 100, base_y + 160)
    
    # Roto/2D integration dot
    roto_dot = nuke.nodes.Dot()
    roto_dot['label'].setValue("Merge 2D Character/Element Here")
    roto_dot['note_font_size'].setValue(12)
    roto_dot.setXYpos(base_x + 134, base_y + 240)
    roto_dot.setInput(0, bg_to_image)
    
    # Merge
    merge = nuke.nodes.Merge2(inputs=[roto_dot, fg_to_image])
    merge.setXYpos(base_x, base_y + 300)
    
    # Backdrop
    bd = nuke.nodes.BackdropNode()
    bd['label'].setValue("Deep Volume Split & Holdout")
    bd['note_font_size'].setValue(20)
    bd['xpos'].setValue(base_x - 150)
    bd['ypos'].setValue(base_y + 10)
    bd['bdwidth'].setValue(400)
    bd['bdheight'].setValue(350)
    
    for n in nuke.selectedNodes():
        n.setSelected(False)
    merge.setSelected(True)
    
    return merge


def create_deep_edge_fix(source_node):
    """
    Builds a Deep Artifact Fixer that cleans bad renders (negative Z, NaN alphas).
    """
    if not source_node:
        nuke.message("Please select a Deep node to sanitize.")
        return None
        
    base_x = source_node.xpos()
    base_y = source_node.ypos()
    
    expr = nuke.nodes.DeepExpression(inputs=[source_node])
    expr['label'].setValue("Deep Sanitizer\\nClamps Alpha & Negative Z")
    expr['tile_color'].setValue(int("0xe74c3cff", 16))
    
    # Fix negative depth (which fatally breaks deep merges)
    expr['deep.front'].setExpression("deep.front <= 0 ? 0.0001 : deep.front")
    expr['deep.back'].setExpression("deep.back <= 0 ? 0.0001 : deep.back")
    
    # Fix infinite/NaN/negative alphas
    expr['rgba.alpha'].setExpression("isnan(rgba.alpha) || rgba.alpha < 0 ? 0 : (rgba.alpha > 1 ? 1 : rgba.alpha)")
    expr.setXYpos(base_x, base_y + 80)
    
    # Often, Deep renders have huge bounding boxes, add a format crop to optimize memory
    crop = nuke.nodes.DeepCrop(inputs=[expr])
    crop['use_bbox'].setValue(True)
    crop['bbox'].setValue([0, 0, nuke.root().format().width(), nuke.root().format().height()])
    crop['label'].setValue("Format Crop")
    crop.setXYpos(base_x, base_y + 130)
    
    for n in nuke.selectedNodes():
        n.setSelected(False)
    crop.setSelected(True)
    
    return crop


def create_2d_to_deep_rig(source_node):
    """
    Builds a professional 2D-to-Deep conversion rig.
    Allows artists to inject a Z-depth map into a flat 2D element and convert it to Deep space.
    """
    if not source_node:
        nuke.message("Please select a 2D node to convert to Deep.")
        return None
        
    base_x = source_node.xpos()
    base_y = source_node.ypos()
    
    # 1. Main stream
    main_dot = nuke.nodes.Dot(inputs=[source_node])
    main_dot.setXYpos(base_x + 34, base_y + 100)
    
    # 2. Depth Generator / Input
    z_const = nuke.nodes.Constant()
    z_const['color'].setValue(100.0) # default distance
    z_const['label'].setValue("Default Z-Distance\\n(Fallback)")
    z_const.setXYpos(base_x - 150, base_y + 40)
    
    z_dot = nuke.nodes.Dot(inputs=[z_const])
    z_dot['label'].setValue("Connect Custom Z-Depth\\n(Uses Red Channel)")
    z_dot['note_font_size'].setValue(12)
    z_dot.setXYpos(base_x - 116, base_y + 150)
    
    # 3. Inject Depth (Copy A into B)
    copy_z = nuke.nodes.Copy(inputs=[main_dot, z_dot])
    copy_z['from0'].setValue('rgba.red')
    copy_z['to0'].setValue('depth.Z')
    copy_z.setXYpos(base_x, base_y + 140)
    
    # 4. Premult (Crucial before DeepFromImage so alpha holds bounds)
    premult = nuke.nodes.Premult(inputs=[copy_z])
    premult.setXYpos(base_x, base_y + 190)
    
    # 5. DeepFromImage
    deep_from_image = nuke.nodes.DeepFromImage(inputs=[premult])
    deep_from_image['z'].setValue('depth.Z')
    deep_from_image.setXYpos(base_x, base_y + 240)
    
    # 6. DeepToImage (Preview/Output)
    deep_to_image = nuke.nodes.DeepToImage(inputs=[deep_from_image])
    deep_to_image['label'].setValue("Preview / Back to 2D")
    deep_to_image.setXYpos(base_x, base_y + 340)
    
    # Add a backdrop
    backdrop = nuke.nodes.BackdropNode()
    backdrop['label'].setValue("2D to Deep Rig")
    backdrop['note_font_size'].setValue(20)
    backdrop['xpos'].setValue(base_x - 170)
    backdrop['ypos'].setValue(base_y + 10)
    backdrop['bdwidth'].setValue(300)
    backdrop['bdheight'].setValue(400)
    
    # Deselect all and select the new output
    for n in nuke.selectedNodes():
        n.setSelected(False)
    deep_from_image.setSelected(True)
    
    return deep_from_image


def create_deep_slap_comp(selected_nodes):
    """
    Builds a complete Deep Slap-Comp tree from selected Deep nodes.
    Merges them, flattens to 2D, and adds standard unpremult/grade/premult blocks.
    """
    if not selected_nodes:
        nuke.message("Please select at least one Deep node to build a Slap Comp.")
        return None
        
    # Sort nodes by X position to roughly guess foreground/background intent (left to right)
    sorted_nodes = sorted(selected_nodes, key=lambda n: n.xpos())
    
    base_x = sorted_nodes[0].xpos()
    base_y = max([n.ypos() for n in sorted_nodes]) + 150
    
    # 1. DeepMerge
    if len(sorted_nodes) > 1:
        deep_merge = nuke.nodes.DeepMerge()
        deep_merge.setXYpos(base_x, base_y)
        deep_merge['label'].setValue("Deep Auto-Merge")
        
        # Connect all selected nodes to DeepMerge
        for i, node in enumerate(sorted_nodes):
            deep_merge.setInput(i, node)
            
        last_deep_node = deep_merge
    else:
        # If only one node selected, just pipe it through a Dot
        last_deep_node = nuke.nodes.Dot(inputs=[sorted_nodes[0]])
        last_deep_node.setXYpos(base_x + 34, base_y)
        
    # 2. DeepToImage (Flattening)
    deep_to_image = nuke.nodes.DeepToImage(inputs=[last_deep_node])
    deep_to_image.setXYpos(base_x, base_y + 80)
    
    # 3. Unpremult
    unpremult = nuke.nodes.Unpremult(inputs=[deep_to_image])
    unpremult.setXYpos(base_x, base_y + 130)
    
    # 4. Grade (The CC block)
    grade = nuke.nodes.Grade(inputs=[unpremult])
    grade['label'].setValue("Flat CC")
    grade.setXYpos(base_x, base_y + 180)
    
    # 5. Premult
    premult = nuke.nodes.Premult(inputs=[grade])
    premult.setXYpos(base_x, base_y + 230)
    
    # Backdrop
    bd = nuke.nodes.BackdropNode()
    bd['label'].setValue("Deep Slap-Comp")
    bd['note_font_size'].setValue(20)
    
    # Calculate backdrop width based on inputs if merged
    if len(sorted_nodes) > 1:
        min_x = min([n.xpos() for n in sorted_nodes])
        max_x = max([n.xpos() for n in sorted_nodes])
        bd_width = max(300, (max_x - min_x) + 150)
        bd['xpos'].setValue(min_x - 50)
    else:
        bd_width = 250
        bd['xpos'].setValue(base_x - 70)
        
    bd['ypos'].setValue(base_y - 80)
    bd['bdwidth'].setValue(bd_width)
    bd['bdheight'].setValue(400)
    
    for n in nuke.selectedNodes():
        n.setSelected(False)
    premult.setSelected(True)
    
    return premult


def create_deep_memory_inspector(source_node):
    """
    Builds a Deep Memory & Optimization Inspector rig.
    Scans a DeepRead node and provides frustum/bbox culling and micro-density cleanup
    to slash memory usage for heavy volumetric FX renders.
    """
    if not source_node:
        nuke.message("Please select a Deep node to optimize.")
        return None
        
    base_x = source_node.xpos()
    base_y = source_node.ypos()
    
    # 1. Bounding Box & Frustum Culling
    crop = nuke.nodes.DeepCrop(inputs=[source_node])
    crop['label'].setValue("Frustum / BBox Culling\\n(Clamps out-of-camera data)")
    crop['use_bbox'].setValue(True)
    crop['bbox'].setValue([0, 0, nuke.root().format().width(), nuke.root().format().height()])
    crop['use_znear'].setValue(True)
    crop['znear'].setValue(0.1)
    crop['use_zfar'].setValue(True)
    crop['zfar'].setValue(10000.0)
    crop['tile_color'].setValue(int("0x2980b9ff", 16))
    crop.setXYpos(base_x, base_y + 80)
    
    # 2. Micro-Density Cull
    expr = nuke.nodes.DeepExpression(inputs=[crop])
    expr['label'].setValue("Micro-Density Cull\\n(Zeroes invisible samples)")
    expr['tile_color'].setValue(int("0x27ae60ff", 16))
    expr.addKnob(nuke.Double_Knob("density_threshold", "Density Threshold"))
    expr['density_threshold'].setValue(0.0001)
    
    # If the sample alpha is basically 0, set it to exactly 0 to aid compression/merging
    expr['rgba.alpha'].setExpression("rgba.alpha < density_threshold ? 0.0 : rgba.alpha")
    expr.setXYpos(base_x, base_y + 140)
    
    # 3. Diagnostic QC View
    qc_dot = nuke.nodes.Dot(inputs=[expr])
    qc_dot.setXYpos(base_x + 150, base_y + 145)
    
    deep_to_image = nuke.nodes.DeepToImage(inputs=[qc_dot])
    deep_to_image['label'].setValue("Diagnostic View\\n(Flattened QC)")
    deep_to_image.setXYpos(base_x + 116, base_y + 190)
    
    qc_grade = nuke.nodes.Grade(inputs=[deep_to_image])
    qc_grade['label'].setValue("Density Boost\\n(Visualizes low-weight samples)")
    qc_grade['white'].setValue(10.0)
    qc_grade['gamma'].setValue(0.5)
    qc_grade.setXYpos(base_x + 116, base_y + 240)
    
    bd = nuke.nodes.BackdropNode()
    bd['label'].setValue("Deep Memory Inspector & Optimizer")
    bd['note_font_size'].setValue(20)
    bd['xpos'].setValue(base_x - 50)
    bd['ypos'].setValue(base_y + 20)
    bd['bdwidth'].setValue(320)
    bd['bdheight'].setValue(300)
    
    for n in nuke.selectedNodes():
        n.setSelected(False)
    expr.setSelected(True)
    
    return expr
