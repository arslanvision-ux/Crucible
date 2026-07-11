import nuke

def _create_integration_group(name, tooltip=""):
    """Helper to create a Group node with basic properties."""
    group = nuke.nodes.Group(name=name)
    group['postage_stamp'].setValue(False)
    if tooltip:
        group['help'].setValue(tooltip)
    return group

def create_chroma_warp(source_node):
    """Creates a Chromatic Aberration node group."""
    if not source_node:
        nuke.message("Select a node to attach the Chroma Warp.")
        return
        
    group = _create_integration_group("Crucible_ChromaWarp")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        # Controls on the Group
        k_tab = nuke.Tab_Knob("Crucible", "Crucible Chroma Warp")
        group.addKnob(k_tab)
        
        k_amount = nuke.Double_Knob("amount", "Amount")
        k_amount.setValue(0.005)
        k_amount.setRange(0, 0.05)
        group.addKnob(k_amount)
        
        # Red Channel
        shuf_r = nuke.nodes.Shuffle2(inputs=[input_node], label="Red")
        shuf_r['in1'].setValue("rgba")
        shuf_r['mappings'].setValue([(0, 'rgba.red', 'rgba.red')])
        
        trans_r = nuke.nodes.Transform(inputs=[shuf_r])
        trans_r['scale'].setExpression("1.0 + parent.amount")
        trans_r['center'].setExpression("input.width/2", 0)
        trans_r['center'].setExpression("input.height/2", 1)
        trans_r['black_outside'].setValue(False)
        
        # Blue Channel
        shuf_b = nuke.nodes.Shuffle2(inputs=[input_node], label="Blue")
        shuf_b['in1'].setValue("rgba")
        shuf_b['mappings'].setValue([(0, 'rgba.blue', 'rgba.blue')])
        
        trans_b = nuke.nodes.Transform(inputs=[shuf_b])
        trans_b['scale'].setExpression("1.0 - parent.amount")
        trans_b['center'].setExpression("input.width/2", 0)
        trans_b['center'].setExpression("input.height/2", 1)
        trans_b['black_outside'].setValue(False)
        
        # Green Channel
        shuf_g = nuke.nodes.Shuffle2(inputs=[input_node], label="Green")
        shuf_g['in1'].setValue("rgba")
        shuf_g['mappings'].setValue([(0, 'rgba.green', 'rgba.green')])
        
        # Merge back
        merge1 = nuke.nodes.Merge2(inputs=[shuf_g, trans_r], operation="plus")
        merge2 = nuke.nodes.Merge2(inputs=[merge1, trans_b], operation="plus")
        
        # Copy Alpha from original
        copy_alpha = nuke.nodes.Copy(inputs=[merge2, input_node], from0="rgba.alpha", to0="rgba.alpha")
        
        output = nuke.nodes.Output(inputs=[copy_alpha])
        
    return group

def create_exponential_glow(source_node):
    """Creates a high-end Optical Exponential Glow."""
    if not source_node:
        nuke.message("Select a node to attach the Glow.")
        return
        
    group = _create_integration_group("Crucible_ExpoGlow")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        k_tab = nuke.Tab_Knob("Crucible", "Exponential Glow")
        group.addKnob(k_tab)
        
        k_intensity = nuke.Double_Knob("intensity", "Intensity")
        k_intensity.setValue(0.5)
        group.addKnob(k_intensity)
        
        k_size = nuke.Double_Knob("size", "Base Size")
        k_size.setValue(10)
        k_size.setRange(1, 100)
        group.addKnob(k_size)
        
        k_falloff = nuke.Double_Knob("falloff", "Falloff")
        k_falloff.setValue(0.5)
        group.addKnob(k_falloff)
        
        # Keyer for highlights
        keyer = nuke.nodes.Keyer(inputs=[input_node], operation="luminance key")
        keyer['range'].setValue([0.8, 1.0, 100.0, 100.0])
        
        premult = nuke.nodes.Premult(inputs=[keyer])
        
        # Exponential Blur Stack
        blurs = []
        mults = []
        for i in range(5):
            multiplier = 2 ** i
            blur = nuke.nodes.Blur(inputs=[premult if i==0 else blurs[-1]])
            blur['size'].setExpression(f"parent.size * {multiplier}")
            
            mult = nuke.nodes.Multiply(inputs=[blur])
            mult['value'].setExpression(f"parent.intensity * pow(parent.falloff, {i+1})")
            
            blurs.append(blur)
            mults.append(mult)
            
        # Merge Blurs
        merge_glow = nuke.nodes.Merge2(inputs=[mults[0], mults[1]], operation="plus")
        for i in range(2, 5):
            merge_glow = nuke.nodes.Merge2(inputs=[merge_glow, mults[i]], operation="plus")
            
        # Merge over input
        final_merge = nuke.nodes.Merge2(inputs=[input_node, merge_glow], operation="plus")
        
        output = nuke.nodes.Output(inputs=[final_merge])
        
    return group

def create_light_wrap(source_node):
    """Generates a physically plausible Smart Light Wrap using an exponential blur stack."""
    if not source_node:
        nuke.message("Select a CG node.")
        return
        
    group = _create_integration_group("Crucible_SmartWrap")
    group.setInput(0, source_node)
    
    with group:
        cg_in = nuke.nodes.Input(name="CG")
        bg_in = nuke.nodes.Input(name="BG")
        
        k_tab = nuke.Tab_Knob("Crucible", "Smart Wrap")
        group.addKnob(k_tab)
        
        k_size = nuke.Double_Knob("size", "Base Bloom Size")
        k_size.setValue(5)
        k_size.setRange(1, 50)
        group.addKnob(k_size)
        
        k_intensity = nuke.Double_Knob("intensity", "Exposure/Intensity")
        k_intensity.setValue(1.0)
        group.addKnob(k_intensity)
        
        # Edge Matte Creation
        edge_matte = nuke.nodes.EdgeDetectWrapper(inputs=[cg_in], erodesize=1, blursize=2)
        
        # Isolate BG luminance using the edge matte
        copy_bg = nuke.nodes.Copy(inputs=[bg_in, edge_matte], from0="rgba.alpha", to0="rgba.alpha")
        premult_bg = nuke.nodes.Premult(inputs=[copy_bg])
        
        # Exponential Blur Stack for realistic optical blooming
        blurs = []
        mults = []
        for i in range(4):
            multiplier = 2 ** i
            blur = nuke.nodes.Blur(inputs=[premult_bg if i==0 else blurs[-1]])
            blur['size'].setExpression(f"parent.size * {multiplier}")
            
            mult = nuke.nodes.Multiply(inputs=[blur])
            mult['value'].setExpression(f"parent.intensity * pow(0.5, {i+1})")
            
            blurs.append(blur)
            mults.append(mult)
            
        merge_glow = nuke.nodes.Merge2(inputs=[mults[0], mults[1]], operation="plus")
        for i in range(2, 4):
            merge_glow = nuke.nodes.Merge2(inputs=[merge_glow, mults[i]], operation="plus")
            
        # Merge over the original CG
        final_merge = nuke.nodes.Merge2(inputs=[cg_in, merge_glow], operation="plus")
        
        # Mask the wrap to stay inside the CG alpha so it doesn't spill onto the plate
        mask_wrap = nuke.nodes.Copy(inputs=[final_merge, cg_in], from0="rgba.alpha", to0="rgba.alpha")
        repremult = nuke.nodes.Premult(inputs=[mask_wrap])
        
        output = nuke.nodes.Output(inputs=[repremult])
        
    return group

def create_vignette(source_node):
    """Creates a Radial Vignette."""
    if not source_node:
        nuke.message("Select a node.")
        return
        
    group = nuke.nodes.Group(name="Crucible_LensVignette")
    group.setInput(0, source_node)
    
    with group:
        in_node = nuke.nodes.Input(name="Input")
        
        k_tab = nuke.Tab_Knob("Crucible", "Vignette")
        group.addKnob(k_tab)
        
        k_darkness = nuke.Double_Knob("darkness", "Darkness")
        k_darkness.setRange(0, 1)
        k_darkness.setValue(0.5)
        group.addKnob(k_darkness)
        
        k_scale = nuke.Double_Knob("scale", "Scale / Size")
        k_scale.setRange(0.1, 3.0)
        k_scale.setValue(1.0)
        group.addKnob(k_scale)
        
        k_softness = nuke.Double_Knob("softness", "Softness")
        k_softness.setRange(0, 1)
        k_softness.setValue(1.0)
        group.addKnob(k_softness)
        
        radial = nuke.nodes.Radial(inputs=[in_node])
        radial['area'].setExpression("(input.width/2) - (input.width * parent.scale)/2", 0)
        radial['area'].setExpression("(input.height/2) - (input.height * parent.scale)/2", 1)
        radial['area'].setExpression("(input.width/2) + (input.width * parent.scale)/2", 2)
        radial['area'].setExpression("(input.height/2) + (input.height * parent.scale)/2", 3)
        radial['softness'].setExpression("parent.softness")
        
        grade = nuke.nodes.Grade(inputs=[radial])
        grade['multiply'].setExpression("parent.darkness")
        grade['add'].setExpression("1.0 - parent.darkness")
        grade['black_clamp'].setValue(False)
        grade['white_clamp'].setValue(False)
        
        merge = nuke.nodes.Merge2(inputs=[in_node, grade], operation="multiply")
        
        output = nuke.nodes.Output(inputs=[merge])
        
    return group

def create_grain_extractor(*args, **kwargs):
    """Creates a True Plate Grain Extractor (Ghost-Free)."""
    nodes = nuke.selectedNodes()
    if len(nodes) == 0:
        nuke.message("Select a CG node and a Plate node to extract grain.")
        return
        
    cg_node = nodes[0]
    plate_node = nodes[1] if len(nodes) > 1 else None
    
    if plate_node and ('cg' in plate_node.name().lower() or 'render' in plate_node.name().lower()):
        cg_node, plate_node = plate_node, cg_node
        
    # Deselect all nodes to prevent rogue auto-wiring
    for n in nodes:
        n.setSelected(False)
        
    group = _create_integration_group("Crucible_GrainExtractor", "Procedural Plate Grain Extraction Pipeline")
    group.setInput(0, cg_node)
    if plate_node:
        group.setInput(1, plate_node)
    
    with group:
        cg_in = nuke.nodes.Input(name="CG")
        plate_in = nuke.nodes.Input(name="Plate")
        
        k_tab = nuke.Tab_Knob("Crucible", "Plate Grain")
        group.addKnob(k_tab)
        
        k_grain = nuke.Boolean_Knob("apply_grain", "Apply Plate Grain")
        k_grain.setValue(True)
        group.addKnob(k_grain)
        
        # Ghost-Free High-Pass Plate Grain Extraction
        hp_blur = nuke.nodes.Blur(inputs=[plate_in])
        hp_blur['size'].setValue(2.0)
        high_pass = nuke.nodes.Merge2(inputs=[plate_in, hp_blur], operation="minus")
        
        edge_detect = nuke.nodes.EdgeDetectWrapper(inputs=[plate_in])
        
        # Safely convert RGB edges to Alpha mask
        edge_expr = nuke.nodes.Expression(inputs=[edge_detect])
        edge_expr['expr3'].setValue("clamp((r+g+b)*3.0)")
        
        dilate_edges = nuke.nodes.Dilate(inputs=[edge_expr])
        dilate_edges['channels'].setValue('rgba.alpha')
        dilate_edges['size'].setValue(4.0)
        
        # Invert edges: 1.0 = flat noise area, 0.0 = sharp detail
        flat_areas = nuke.nodes.Invert(inputs=[dilate_edges], channels="rgba.alpha")
        
        # Mask out edges to get pure plate noise
        pure_grain = nuke.nodes.Merge2(inputs=[high_pass, flat_areas], operation="mask")
        
        # Add grain securely using a masked Merge
        apply_grain = nuke.nodes.Merge2(inputs=[cg_in, pure_grain], operation="plus", maskChannelInput="rgba.alpha", label="Add Grain")
        
        switch_grain = nuke.nodes.Switch(inputs=[cg_in, apply_grain])
        switch_grain['which'].setExpression("parent.apply_grain")
        
        output = nuke.nodes.Output(inputs=[switch_grain])
        
    return group

def create_projection_rig(camera_node):
    """Builds a One-Click 3D Projection Rig."""
    if not camera_node or (camera_node.Class() != 'Camera2' and camera_node.Class() != 'Camera'):
        nuke.message("Select a Camera node.")
        return
        
    frame = nuke.frame()
    
    # Freeze the camera
    frame_hold = nuke.nodes.FrameHold(inputs=[camera_node], first_frame=frame)
    frame_hold['label'].setValue(f"Ref Frame: {frame}")
    
    # Project 3D (Input 0 for image to project)
    project = nuke.nodes.Project3D(inputs=[None, frame_hold]) 
    project['label'].setValue("Connect Image Here ☝️")
    
    # Card
    card = nuke.nodes.Card2()
    card['z'].setValue(-100) # Default depth
    card['label'].setValue("Projection Geo")
    
    # Apply material to geo
    apply_mat = nuke.nodes.ApplyMaterial(inputs=[card, project])
    
    # Scanline Render
    render = nuke.nodes.ScanlineRender(inputs=[None, apply_mat, camera_node]) # obj/scn, cam
    render['projection_mode'].setValue("render camera")
    render['transparent_background'].setValue(True)
    
    # Layout
    x, y = camera_node.xpos(), camera_node.ypos()
    frame_hold.setXYpos(x + 150, y)
    project.setXYpos(x + 150, y + 100)
    card.setXYpos(x + 300, y + 50)
    apply_mat.setXYpos(x + 300, y + 100)
    render.setXYpos(x + 300, y + 200)
    
    return render

def create_auto_color_match():
    """Generates a Grade node linked to a CurveTool for Auto-Color Matching."""
    nodes = nuke.selectedNodes()
    if len(nodes) != 2:
        nuke.message("Select exactly 2 nodes (1 Plate, 1 CG) for Auto-Color Match.")
        return
        
    node_a, node_b = nodes[0], nodes[1]
    
    # Guess which is plate
    plate_node = node_a
    cg_node = node_b
    if 'cg' in node_a.name().lower() or 'render' in node_a.name().lower() or 'beauty' in node_a.name().lower():
        plate_node, cg_node = node_b, node_a
    for n in nodes:
        n.setSelected(False)
        
    group = _create_integration_group("Crucible_AutoColorMatch", "Matches CG black/white points to the Plate.")
    group.setInput(0, cg_node)
    group.setInput(1, plate_node)
    
    with group:
        cg_in = nuke.nodes.Input(name="CG")
        plate_in = nuke.nodes.Input(name="Plate")
        
        k_tab = nuke.Tab_Knob("Crucible", "Auto-Color Match")
        group.addKnob(k_tab)
        
        info = nuke.Text_Knob("info", "", "Click Analyze to match CG black/white levels to the Plate.")
        group.addKnob(info)
        
        py_script = """
n = nuke.thisNode()
with n:
    f = nuke.frame()
    nuke.execute("CurveTool_Plate", f, f)
    nuke.execute("CurveTool_CG", f, f)
    
    p_min = nuke.toNode("CurveTool_Plate")['minlumapixvalue'].value()
    p_max = nuke.toNode("CurveTool_Plate")['maxlumapixvalue'].value()
    c_min = nuke.toNode("CurveTool_CG")['minlumapixvalue'].value()
    c_max = nuke.toNode("CurveTool_CG")['maxlumapixvalue'].value()
    
    grade = nuke.toNode("Grade_Match")
    grade['blackpoint'].setValue(c_min)
    grade['whitepoint'].setValue(c_max)
    grade['black'].setValue(p_min)
    grade['white'].setValue(p_max)
    
    grade['disable'].setValue(False)
"""
        k_btn = nuke.PyScript_Knob("analyze", "Analyze Frame & Match")
        k_btn.setValue(py_script)
        group.addKnob(k_btn)
        
        # Curve tools
        curve_plate = nuke.nodes.CurveTool(inputs=[plate_in], name="CurveTool_Plate", operation="Max Luma Pixel")
        curve_plate['ROI'].setExpression("0", 0)
        curve_plate['ROI'].setExpression("0", 1)
        curve_plate['ROI'].setExpression("input.width", 2)
        curve_plate['ROI'].setExpression("input.height", 3)
        
        curve_cg = nuke.nodes.CurveTool(inputs=[cg_in], name="CurveTool_CG", operation="Max Luma Pixel")
        curve_cg['ROI'].setExpression("0", 0)
        curve_cg['ROI'].setExpression("0", 1)
        curve_cg['ROI'].setExpression("input.width", 2)
        curve_cg['ROI'].setExpression("input.height", 3)
        
        # Grade node - initially disabled until matched
        grade = nuke.nodes.Grade(inputs=[cg_in], name="Grade_Match")
        grade['disable'].setValue(True)
        
        output = nuke.nodes.Output(inputs=[grade])
    
    return group

def create_smart_despill(source_node):
    """Creates a mathematically pure Green/Blue Smart Despill setup."""
    if not source_node:
        nuke.message("Select a greenscreen or bluescreen plate.")
        return
        
    group = _create_integration_group("Crucible_SmartDespill", "Mathematically pure Green/Blue despill.")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        k_tab = nuke.Tab_Knob("Crucible", "Smart Despill")
        group.addKnob(k_tab)
        
        k_screen = nuke.Enumeration_Knob("screen_type", "Screen Type", ["Green", "Blue"])
        group.addKnob(k_screen)
        
        k_algo = nuke.Enumeration_Knob("algorithm", "Algorithm", ["Average", "Minimum"])
        group.addKnob(k_algo)
        
        # Expression node for the math
        expr = nuke.nodes.Expression(inputs=[input_node])
        
        # Green despill
        expr['expr1'].setExpression("parent.screen_type == 0 ? (parent.algorithm == 0 ? (g > (r+b)/2 ? (r+b)/2 : g) : (g > min(r,b) ? min(r,b) : g)) : g")
        
        # Blue despill
        expr['expr2'].setExpression("parent.screen_type == 1 ? (parent.algorithm == 0 ? (b > (r+g)/2 ? (r+g)/2 : b) : (b > min(r,g) ? min(r,g) : b)) : b")
        
        # Spill matte in alpha
        expr['expr3'].setExpression("parent.screen_type == 0 ? g - expr1 : b - expr2")
        expr['label'].setValue("Alpha = Spill Matte")
        
        output = nuke.nodes.Output(inputs=[expr])
        
    return group

def create_shadow_catcher():
    """Builds a CG Shadow & Reflection Catcher."""
    nodes = nuke.selectedNodes()
    if len(nodes) != 3:
        nuke.message("Select exactly 3 nodes: CG Beauty, CG Clean Plate (Ground), Live Action Plate.")
        return
        
    # We won't try to guess perfectly, just connect them and let the user swap
    cg_beauty, cg_clean, plate = nodes[0], nodes[1], nodes[2]
    
    x = plate.xpos()
    y = plate.ypos()
    
    # Shadow extraction: CG Beauty / CG Clean
    divide = nuke.nodes.Merge2(inputs=[cg_clean, cg_beauty], operation="divide", label="Extract Shadows/Reflections")
    divide.setXYpos(x + 150, y + 50)
    
    # Multiply over live plate
    multiply = nuke.nodes.Merge2(inputs=[plate, divide], operation="multiply", label="Apply Shadows")
    multiply.setXYpos(x, y + 150)
    
    nuke.message("Shadow Catcher built! \n\nA = CG Beauty\nB = CG Clean Plate\n\nSwap inputs if needed.")
    return multiply

def create_camera_shake(source_node):
    """Generates procedural camera shake with optical motion blur."""
    if not source_node:
        nuke.message("Select a node to apply camera shake.")
        return
        
    transform = nuke.nodes.Transform(inputs=[source_node])
    transform['label'].setValue("Procedural Handheld Shake")
    
    # Add custom knobs to control shake
    k_tab = nuke.Tab_Knob("Crucible", "Camera Shake")
    transform.addKnob(k_tab)
    
    k_amp = nuke.Double_Knob("amplitude", "Amplitude")
    k_amp.setValue(10.0)
    transform.addKnob(k_amp)
    
    k_freq = nuke.Double_Knob("frequency", "Frequency")
    k_freq.setValue(0.5)
    transform.addKnob(k_freq)
    
    # Expressions using noise
    transform['translate'].setExpression("(noise(frame * frequency, 0) - 0.5) * amplitude * 2", 0)
    transform['translate'].setExpression("(noise(0, frame * frequency) - 0.5) * amplitude * 2", 1)
    
    transform['rotate'].setExpression("(noise(frame * frequency, frame * frequency) - 0.5) * (amplitude/10)")
    
    # Enable motion blur
    transform['shutter'].setValue(0.5)
    transform['motionblur'].setValue(1)
    
    return transform

def create_day_for_night(source_node):
    """Builds a mathematically structured Day-for-Night look dev rig."""
    if not source_node:
        nuke.message("Select a day plate.")
        return
        
    x, y = source_node.xpos(), source_node.ypos()
    
    # 1. Suppress midtones
    lookup = nuke.nodes.ColorLookup(inputs=[source_node], label="Suppress Midtones")
    lookup.setXYpos(x, y + 50)
    
    # 2. Key bright highlights (sky/speculars)
    keyer = nuke.nodes.Keyer(inputs=[lookup], operation="luminance key")
    keyer['range'].setValue([0.6, 0.8, 1.0, 1.0])
    keyer.setXYpos(x + 150, y + 50)
    
    # 3. Night Grade (Blueish)
    grade = nuke.nodes.Grade(inputs=[lookup, keyer])
    grade['multiply'].setValue([0.2, 0.35, 0.6, 1.0]) # Deep moonlight blue
    grade['gamma'].setValue(0.7)
    grade['maskChannelInput'].setValue('rgba.alpha')
    grade['invert_mask'].setValue(True) # Don't tint the bright highlights blue
    grade['label'].setValue("Moonlight Grade")
    grade.setXYpos(x, y + 100)
    
    # 4. Desaturate
    sat = nuke.nodes.Saturation(inputs=[grade])
    sat['saturation'].setValue(0.4) # Scotopic vision (eyes see less color at night)
    sat.setXYpos(x, y + 150)
    
    return sat

def create_ai_denoise(source_node):
    """Builds a production-grade AI Denoise wrapper using Inference with ACEScct management."""
    if not source_node:
        nuke.message("Select a node to apply AI Denoise.")
        return
        
    group = _create_integration_group("Crucible_AIDenoise", "Production-grade AI Denoise with ACEScct management.")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        k_tab = nuke.Tab_Knob("Crucible", "AI Denoise Engine")
        group.addKnob(k_tab)
        
        k_model = nuke.File_Knob("modelFile", "CopyCat Model (.cat)")
        k_model.setTooltip("Path to the Nuke CopyCat model (.cat) or Cattery denoiser.")
        group.addKnob(k_model)
        
        k_log = nuke.Boolean_Knob("use_log", "Process in ACEScct (Log)")
        k_log.setTooltip("Converts to Log space before Inference. Highly recommended for AI models to prevent HDR artifacting (fireflies).")
        k_log.setValue(True)
        group.addKnob(k_log)
        
        k_freq = nuke.Boolean_Knob("freq_sep", "Retain High Frequencies")
        k_freq.setTooltip("Blends original high-frequency details back over the denoised image to prevent plastic/soft results.")
        k_freq.setValue(False)
        group.addKnob(k_freq)
        
        k_detail = nuke.Double_Knob("detail_size", "High Freq Size")
        k_detail.setValue(2.0)
        group.addKnob(k_detail)
        
        k_mix = nuke.Double_Knob("mix", "Overall Mix")
        k_mix.setValue(1.0)
        group.addKnob(k_mix)
        
        # 1. ACEScg to ACEScct
        to_log = nuke.nodes.OCIOColorSpace(inputs=[input_node])
        to_log['in_colorspace'].setValue("ACES - ACEScg")
        to_log['out_colorspace'].setValue("ACES - ACEScct")
        to_log['disable'].setExpression("!parent.use_log")
        
        # 2. AI Inference
        inference = nuke.nodes.Inference(inputs=[to_log])
        inference['modelFile'].setExpression("parent.modelFile")
        
        # Bypass inference if no model is loaded to prevent GUI error
        safe_switch = nuke.nodes.Switch(inputs=[to_log, inference])
        safe_switch['which'].setExpression("parent.modelFile != '' ? 1 : 0")
        
        # 3. ACEScct back to ACEScg
        to_lin = nuke.nodes.OCIOColorSpace(inputs=[safe_switch])
        to_lin['in_colorspace'].setValue("ACES - ACEScct")
        to_lin['out_colorspace'].setValue("ACES - ACEScg")
        to_lin['disable'].setExpression("!parent.use_log")
        
        # 4. Frequency Separation (High Freq extraction from original)
        blur_orig = nuke.nodes.Blur(inputs=[input_node])
        blur_orig['size'].setExpression("parent.detail_size")
        
        high_freq = nuke.nodes.Merge2(inputs=[input_node, blur_orig], operation="minus", label="High Frequencies")
        
        # Re-apply High Freq to the denoised image
        add_freq = nuke.nodes.Merge2(inputs=[to_lin, high_freq], operation="plus", label="Restore Detail")
        
        # Switch to toggle Freq Sep
        switch_freq = nuke.nodes.Switch(inputs=[to_lin, add_freq])
        switch_freq['which'].setExpression("parent.freq_sep")
        
        # 5. Final Mix
        mix_node = nuke.nodes.Dissolve(inputs=[input_node, switch_freq])
        mix_node['which'].setExpression("parent.mix")
        
        output = nuke.nodes.Output(inputs=[mix_node])
        
    return group

def create_auto_light_match():
    """Builds a Procedural Auto Light Matcher (Screen-space Ambient Tint) from the Plate."""
    nodes = nuke.selectedNodes()
    if len(nodes) != 2:
        nuke.message("Select exactly 2 nodes (1 Plate, 1 CG) for Auto Light Match.")
        return
        
    node_a, node_b = nodes[0], nodes[1]
    
    plate_node = node_a
    cg_node = node_b
    if 'cg' in node_a.name().lower() or 'render' in node_a.name().lower() or 'beauty' in node_a.name().lower():
        plate_node, cg_node = node_b, node_a
        
    group = _create_integration_group("Crucible_AutoLightMatch", "Procedurally extracts ambient color from the plate to tint the CG.")
    group.setInput(0, cg_node)
    group.setInput(1, plate_node)
    
    with group:
        cg_in = nuke.nodes.Input(name="CG")
        plate_in = nuke.nodes.Input(name="Plate")
        
        k_tab = nuke.Tab_Knob("Crucible", "Auto Light Match")
        group.addKnob(k_tab)
        
        k_blur = nuke.Double_Knob("blur_size", "Ambient Blur Size")
        k_blur.setValue(300.0)
        k_blur.setRange(50, 1000)
        group.addKnob(k_blur)
        
        k_intensity = nuke.Double_Knob("intensity", "Tint Mix")
        k_intensity.setValue(1.0)
        group.addKnob(k_intensity)
        
        k_preserve = nuke.Boolean_Knob("preserve_luma", "Preserve CG Exposure")
        k_preserve.setTooltip("If true, only the color/chrominance of the plate is applied, maintaining your CG's original exposure/luminance.")
        k_preserve.setValue(True)
        group.addKnob(k_preserve)
        
        # Heavy Blur to extract ambient light
        blur = nuke.nodes.Blur(inputs=[plate_in])
        blur['size'].setExpression("parent.blur_size")
        blur['crop'].setValue(False)
        
        # Luminance extraction (Rec.709/ACEScg luma approx)
        luma_expr = nuke.nodes.Expression(inputs=[blur], label="Luminance")
        luma_formula = "r*0.2126 + g*0.7152 + b*0.0722 + 0.00001"
        luma_expr['expr0'].setValue(luma_formula)
        luma_expr['expr1'].setValue(luma_formula)
        luma_expr['expr2'].setValue(luma_formula)
        
        # Normalize the blurred plate to get pure chrominance (blur / luma)
        # In Nuke, Merge2 divide is A/B, where input 1 is A and input 0 is B.
        norm = nuke.nodes.Merge2(inputs=[luma_expr, blur], operation="divide", label="Pure Chroma")
        
        # Switch to choose normalized (preserve luma) or raw blur
        switch_norm = nuke.nodes.Switch(inputs=[blur, norm])
        switch_norm['which'].setExpression("parent.preserve_luma")
        
        # Tint the CG
        tint_mult = nuke.nodes.Merge2(inputs=[cg_in, switch_norm], operation="multiply", label="Apply Tint")
        
        # Blend with original
        mix = nuke.nodes.Dissolve(inputs=[cg_in, tint_mult])
        mix['which'].setExpression("parent.intensity")
        
        # Mask by CG alpha
        mask_copy = nuke.nodes.Copy(inputs=[mix, cg_in], from0="rgba.alpha", to0="rgba.alpha")
        premult = nuke.nodes.Premult(inputs=[mask_copy])
        
        output = nuke.nodes.Output(inputs=[premult])
        
    return group

def create_lens_match_engine():
    """Builds a comprehensive Optical Lens Match engine (Defocus, Chroma, Glow, Vignette, Synthetic Grain)."""
    nodes = nuke.selectedNodes()
    if len(nodes) == 0:
        nuke.message("Select a CG node to build the LensMatch Engine.")
        return
        
    cg_node = nodes[0]
    plate_node = nodes[1] if len(nodes) > 1 else None
    
    if plate_node and ('cg' in plate_node.name().lower() or 'render' in plate_node.name().lower()):
        cg_node, plate_node = plate_node, cg_node
        
    # Deselect all nodes to prevent Nuke from auto-wiring incorrectly before our python logic
    for n in nodes:
        n.setSelected(False)
        
    group = _create_integration_group("Crucible_LensMatchEngine", "Unified optical Lens matching tool.")
    group.setInput(0, cg_node)
    if plate_node:
        group.setInput(1, plate_node)
        
    with group:
        cg_in = nuke.nodes.Input(name="CG")
        if plate_node:
            plate_in = nuke.nodes.Input(name="Plate")
        
        k_tab = nuke.Tab_Knob("Crucible", "LensMatch Engine")
        group.addKnob(k_tab)
        
        k_defocus = nuke.Double_Knob("defocus", "Optical Defocus")
        k_defocus.setValue(0.0)
        k_defocus.setRange(0, 20)
        group.addKnob(k_defocus)
        
        k_chroma = nuke.Double_Knob("chroma", "Chromatic Aberration")
        k_chroma.setValue(0.0)
        k_chroma.setRange(0, 0.05)
        group.addKnob(k_chroma)
        
        k_glow = nuke.Double_Knob("glow", "Halation / Bloom")
        k_glow.setValue(0.0)
        group.addKnob(k_glow)
        
        k_vignette = nuke.Double_Knob("vignette", "Vignette Darkness")
        k_vignette.setValue(0.0)
        group.addKnob(k_vignette)
        
        if plate_node:
            k_wrap = nuke.Double_Knob("wrap_size", "Light Wrap Bleed")
            k_wrap.setValue(0.0)
            k_wrap.setRange(0, 50)
            group.addKnob(k_wrap)
            
            k_grain = nuke.Boolean_Knob("use_plate_grain", "Extract & Apply Plate Grain")
            k_grain.setValue(True)
            group.addKnob(k_grain)
        else:
            k_grain = nuke.Boolean_Knob("apply_grain", "Apply Synthetic Grain")
            k_grain.setValue(True)
            group.addKnob(k_grain)
        
        last_node = cg_in
        
        # 0. Light Wrap (If Plate exists)
        if plate_node:
            inv_alpha = nuke.nodes.Invert(inputs=[last_node], channels="rgba.alpha")
            blur_inv = nuke.nodes.Blur(inputs=[inv_alpha], channels="rgba.alpha")
            blur_inv['size'].setExpression("parent.wrap_size")
            
            # Inner rim mask
            inner_rim = nuke.nodes.Merge2(inputs=[last_node, blur_inv], operation="mask", Achannels="rgba.alpha", Bchannels="rgba.alpha", output="rgba.alpha")
            
            # Blur Plate
            blur_plate = nuke.nodes.Blur(inputs=[plate_in])
            blur_plate['size'].setExpression("parent.wrap_size")
            
            # Limit plate to rim
            wrap_color = nuke.nodes.Merge2(inputs=[blur_plate, inner_rim], operation="mask")
            
            # Add to CG
            merge_wrap = nuke.nodes.Merge2(inputs=[last_node, wrap_color], operation="plus")
            
            # Bypass if 0
            switch_wrap = nuke.nodes.Switch(inputs=[last_node, merge_wrap])
            switch_wrap['which'].setExpression("parent.wrap_size > 0 ? 1 : 0")
            last_node = switch_wrap
        
        # 1. Defocus
        defocus_node = nuke.nodes.Defocus(inputs=[last_node])
        defocus_node['defocus'].setExpression("parent.defocus")
        last_node = defocus_node
        
        # 2. Chromatic Aberration (Safe RGB Split via Multiply)
        mult_r = nuke.nodes.Multiply(inputs=[last_node], label="Red")
        mult_r['value'].setValue([1.0, 0.0, 0.0, 0.0])
        
        trans_r = nuke.nodes.Transform(inputs=[mult_r])
        trans_r['scale'].setExpression("1.0 + parent.chroma")
        trans_r['center'].setExpression("width/2", 0)
        trans_r['center'].setExpression("height/2", 1)
        trans_r['black_outside'].setValue(False)
        
        mult_g = nuke.nodes.Multiply(inputs=[last_node], label="Green")
        mult_g['value'].setValue([0.0, 1.0, 0.0, 0.0])
        
        mult_b = nuke.nodes.Multiply(inputs=[last_node], label="Blue")
        mult_b['value'].setValue([0.0, 0.0, 1.0, 0.0])
        
        trans_b = nuke.nodes.Transform(inputs=[mult_b])
        trans_b['scale'].setExpression("1.0 - parent.chroma")
        trans_b['center'].setExpression("width/2", 0)
        trans_b['center'].setExpression("height/2", 1)
        trans_b['black_outside'].setValue(False)
        
        merge_chroma1 = nuke.nodes.Merge2(inputs=[mult_g, trans_r], operation="plus")
        merge_chroma2 = nuke.nodes.Merge2(inputs=[merge_chroma1, trans_b], operation="plus")
        
        copy_alpha = nuke.nodes.Merge2(inputs=[merge_chroma2, last_node], operation="copy", Achannels="rgba.alpha", Bchannels="rgba.alpha", output="rgba.alpha", label="Restore Alpha")
        last_node = copy_alpha
        
        # 3. Halation / Bloom
        keyer = nuke.nodes.Keyer(inputs=[last_node], operation="luminance key")
        keyer['range'].setValue([0.8, 1.0, 100.0, 100.0])
        premult = nuke.nodes.Premult(inputs=[keyer])
        
        blur = nuke.nodes.Blur(inputs=[premult])
        blur['size'].setValue(20)
        
        mult = nuke.nodes.Multiply(inputs=[blur])
        mult['value'].setExpression("parent.glow")
        
        merge_glow = nuke.nodes.Merge2(inputs=[last_node, mult], operation="plus")
        last_node = merge_glow
        
        # 4. Vignette
        radial = nuke.nodes.Radial(inputs=[last_node])
        radial['area'].setExpression("0", 0)
        radial['area'].setExpression("0", 1)
        radial['area'].setExpression("width", 2)
        radial['area'].setExpression("height", 3)
        radial['color'].setValue([1.0, 1.0, 1.0, 1.0])
        
        grade_vig = nuke.nodes.Grade(inputs=[radial])
        grade_vig['multiply'].setExpression("parent.vignette")
        grade_vig['add'].setExpression("1.0 - parent.vignette")
        
        merge_vig = nuke.nodes.Merge2(inputs=[last_node, grade_vig], operation="multiply")
        last_node = merge_vig
        
        # 5. Grain (Plate or Synthetic)
        if plate_node:
            # Ghost-Free High-Pass Plate Grain
            hp_blur = nuke.nodes.Blur(inputs=[plate_in])
            hp_blur['size'].setValue(2.0)
            high_pass = nuke.nodes.Merge2(inputs=[plate_in, hp_blur], operation="minus")
            
            edge_detect = nuke.nodes.EdgeDetectWrapper(inputs=[plate_in])
            
            # Safely convert RGB edges to Alpha mask
            edge_expr = nuke.nodes.Expression(inputs=[edge_detect])
            edge_expr['expr3'].setValue("clamp((r+g+b)*3.0)")
            
            dilate_edges = nuke.nodes.Dilate(inputs=[edge_expr])
            dilate_edges['channels'].setValue('rgba.alpha')
            dilate_edges['size'].setValue(4.0)
            
            # Invert edges: 1.0 = flat noise area, 0.0 = sharp detail
            flat_areas = nuke.nodes.Invert(inputs=[dilate_edges], channels="rgba.alpha")
            
            # Mask out edges to get pure plate noise
            pure_grain = nuke.nodes.Merge2(inputs=[high_pass, flat_areas], operation="mask")
            
            # Add grain securely using a masked Merge
            apply_grain = nuke.nodes.Merge2(inputs=[last_node, pure_grain], operation="plus", maskChannelInput="rgba.alpha", label="Add Grain")
            
            switch_grain = nuke.nodes.Switch(inputs=[last_node, apply_grain])
            switch_grain['which'].setExpression("parent.use_plate_grain")
            last_node = switch_grain
        else:
            grain = nuke.nodes.Grain2(inputs=[last_node])
            premult_grain = nuke.nodes.Premult(inputs=[grain])
            
            switch_grain = nuke.nodes.Switch(inputs=[last_node, premult_grain])
            switch_grain['which'].setExpression("parent.apply_grain")
            last_node = switch_grain
        
        output = nuke.nodes.Output(inputs=[last_node])
        
    return group

