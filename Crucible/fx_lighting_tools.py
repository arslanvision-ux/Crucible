import nuke
import math

def _create_integration_group(name, tooltip=""):
    """Helper to create a Group node with basic properties."""
    group = nuke.nodes.Group(name=name)
    group['postage_stamp'].setValue(False)
    if tooltip:
        group['help'].setValue(tooltip)
    return group

def create_volume_slicer(source_node):
    """Procedurally generates a soft depth-slice matte for FX volumes using Z-Depth."""
    if not source_node:
        nuke.message("Select an FX volume node.")
        return
        
    group = _create_integration_group("Crucible_VolumeSlicer", "Z-Depth Volume Slicer")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Volume_In")
        depth_in = nuke.nodes.Input(name="Holdout_Depth")
        
        k_tab = nuke.Tab_Knob("Crucible", "Volume Slicer")
        group.addKnob(k_tab)
        
        k_depth = nuke.Double_Knob("slice_depth", "Slice Depth")
        k_depth.setValue(100.0)
        group.addKnob(k_depth)
        
        k_softness = nuke.Double_Knob("softness", "Edge Softness")
        k_softness.setValue(10.0)
        group.addKnob(k_softness)
        
        # Grade the holdout depth to create a soft matte
        grade = nuke.nodes.Grade(inputs=[depth_in])
        grade['blackpoint'].setExpression("parent.slice_depth - (parent.softness/2.0)")
        grade['whitepoint'].setExpression("parent.slice_depth + (parent.softness/2.0)")
        grade['white_clamp'].setValue(True)
        grade['black_clamp'].setValue(True)
        
        # Multiply the volume's alpha by the generated depth matte
        copy_matte = nuke.nodes.Copy(inputs=[input_node, grade], from0="rgba.red", to0="rgba.alpha")
        premult = nuke.nodes.Premult(inputs=[copy_matte])
        
        output = nuke.nodes.Output(inputs=[premult])
        
    return group

def create_volume_processor(source_node):
    """Builds a physically accurate Additive/Screen merge setup for FX Volumes (Fire/Smoke)."""
    if not source_node:
        nuke.message("Select an FX VDB render node.")
        return
        
    group = _create_integration_group("Crucible_FX_Volume", "FX Emission & Volume Processor")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        bg_node = nuke.nodes.Input(name="BG")
        
        k_tab = nuke.Tab_Knob("Crucible", "Volume Processor")
        group.addKnob(k_tab)
        
        k_emission = nuke.Double_Knob("emission", "Emission Boost")
        k_emission.setValue(1.0)
        group.addKnob(k_emission)
        
        k_density = nuke.Double_Knob("density", "Smoke Density")
        k_density.setValue(1.0)
        group.addKnob(k_density)
        
        # Unpremult to separate color from alpha
        unpremult = nuke.nodes.Unpremult(inputs=[input_node])
        
        # Process Emission (RGB)
        grade_rgb = nuke.nodes.Grade(inputs=[unpremult])
        grade_rgb['multiply'].setExpression("parent.emission")
        grade_rgb['black_clamp'].setValue(False)
        
        # Process Density (Alpha)
        grade_alpha = nuke.nodes.Grade(inputs=[grade_rgb], channels="alpha")
        grade_alpha['multiply'].setExpression("parent.density")
        
        # Repremult
        premult = nuke.nodes.Premult(inputs=[grade_alpha])
        
        # Plus over BG for emission, over for density
        # In reality, a pure Plus merge is used for fire, Over is used for smoke. 
        # A customized merge equation allows both: BG * (1 - Alpha) + RGB
        merge = nuke.nodes.MergeExpression(inputs=[bg_node, premult])
        merge['expr0'].setValue("B.r * (1 - A.a) + A.r")
        merge['expr1'].setValue("B.g * (1 - A.a) + A.g")
        merge['expr2'].setValue("B.b * (1 - A.a) + A.b")
        merge['expr3'].setValue("A.a + B.a - A.a * B.a")
        
        output = nuke.nodes.Output(inputs=[merge])
        
    return group

def create_heat_distortion(source_node):
    """Creates procedural heat distortion with Noise and IDistort."""
    if not source_node:
        nuke.message("Select a plate or element to distort.")
        return
        
    group = _create_integration_group("Crucible_HeatDistortion", "Procedural Heat Distortion")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        k_tab = nuke.Tab_Knob("Crucible", "Heat Distortion")
        group.addKnob(k_tab)
        
        k_amount = nuke.Double_Knob("amount", "Distortion Amount")
        k_amount.setValue(5.0)
        k_amount.setRange(0, 50)
        group.addKnob(k_amount)
        
        k_speed = nuke.Double_Knob("speed", "Heat Speed")
        k_speed.setValue(1.0)
        group.addKnob(k_speed)
        
        k_scale = nuke.Double_Knob("scale", "Noise Scale")
        k_scale.setValue(50.0)
        group.addKnob(k_scale)
        
        # Create procedural noise for UV distortion
        noise = nuke.nodes.Noise()
        noise['size'].setExpression("parent.scale")
        noise['zoffset'].setExpression("frame * parent.speed * 0.01")
        noise['octaves'].setValue(2)
        noise['gamma'].setValue(0.5)
        
        # Copy noise to forward U and V channels
        copy_uv = nuke.nodes.Copy(inputs=[input_node, noise], from0="rgba.red", to0="forward.u", from1="rgba.green", to1="forward.v")
        
        # IDistort
        idistort = nuke.nodes.IDistort(inputs=[copy_uv])
        idistort['uv'].setValue("forward")
        idistort['uv_scale'].setExpression("parent.amount")
        
        output = nuke.nodes.Output(inputs=[idistort])
        
    return group

def create_edge_extend(source_node):
    """Creates a Smart Edge Extend using Premult/Unpremult and Blur."""
    if not source_node:
        nuke.message("Select a premultiplied CG element.")
        return
        
    group = _create_integration_group("Crucible_EdgeExtend", "Smart Edge Extend")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        k_tab = nuke.Tab_Knob("Crucible", "Edge Extend")
        group.addKnob(k_tab)
        
        k_size = nuke.Double_Knob("size", "Extend Size")
        k_size.setValue(2.0)
        k_size.setRange(0, 20)
        group.addKnob(k_size)
        
        # Unpremult
        unpremult = nuke.nodes.Unpremult(inputs=[input_node])
        
        # Edge Blur
        blur = nuke.nodes.Blur(inputs=[unpremult])
        blur['size'].setExpression("parent.size")
        
        # Mask the blur back inside the original alpha using an EdgeDetect trick
        edge = nuke.nodes.EdgeDetectWrapper(inputs=[input_node])
        edge['erodesize'].setValue(0)
        edge['blursize'].setExpression("parent.size * 2")
        
        # Merge the blurred edge over the original
        keymix = nuke.nodes.Keymix(inputs=[unpremult, blur, edge])
        
        # Repremult
        premult = nuke.nodes.Premult(inputs=[keymix])
        
        output = nuke.nodes.Output(inputs=[premult])
        
    return group

def create_physical_depth_fog(source_node):
    """Generates physically accurate exponential depth fog using Beer-Lambert law."""
    if not source_node:
        nuke.message("Select a node with a Z-Depth channel.")
        return
        
    group = _create_integration_group("Crucible_PhysicalFog", "Physically Accurate Z-Depth Atmosphere")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        # ------------------------------------------------------------------
        # NODE GRAPH
        # ------------------------------------------------------------------
        
        # Step 1: Copy the user-selected depth channel into rgba.alpha.
        copy_depth = nuke.nodes.Copy(inputs=[input_node, input_node])
        copy_depth['to0'].setValue("rgba.alpha")
        copy_depth['label'].setValue("Depth -> Alpha")

        # Step 2: Expression - Calculate Fog Mask AND Premultiplied Fog Color
        # We write the calculated mask to Alpha, and the premultiplied color directly to RGB.
        fog_expr = nuke.nodes.Expression(inputs=[copy_depth])
        fog_expr['temp_name0'].setValue("effZ")
        fog_expr['temp_expr0'].setValue("max(0.0, a - parent.start_dist)")
        fog_expr['temp_name1'].setValue("fogAmt")
        # If raw depth (a) is 0, it means 'sky' (no geometry hit). 
        # We give it max_opacity if fog_sky is True, otherwise 0.
        fog_expr['temp_expr1'].setValue("a <= 0.00001 ? (parent.fog_sky ? parent.max_opacity : 0.0) : clamp((1.0 - exp(-effZ * parent.density)) * parent.max_opacity)")
        
        fog_expr['channel0'].setValue("rgba.red")
        fog_expr['expr0'].setValue("parent.fog_color.r * fogAmt")
        
        fog_expr['channel1'].setValue("rgba.green")
        fog_expr['expr1'].setValue("parent.fog_color.g * fogAmt")
        
        fog_expr['channel2'].setValue("rgba.blue")
        fog_expr['expr2'].setValue("parent.fog_color.b * fogAmt")
        
        fog_expr['channel3'].setValue("rgba.alpha")
        fog_expr['expr3'].setValue("fogAmt")
        fog_expr['label'].setValue("Fog Generation")

        # Step 3: Merge (Over) the fog onto the untouched original plate.
        merge = nuke.nodes.Merge2(inputs=[input_node, fog_expr], operation="over")
        merge['label'].setValue("Apply Fog")

        output = nuke.nodes.Output(inputs=[merge])

        # ------------------------------------------------------------------
        # UI CONSTRUCTION
        # ------------------------------------------------------------------
        
        k_tab = nuke.Tab_Knob("Crucible", "Physical Fog")
        group.addKnob(k_tab)
        
        k_density = nuke.Double_Knob("density", "Fog Density")
        k_density.setValue(0.0001)
        k_density.setRange(0.0, 0.001)
        group.addKnob(k_density)
        
        k_start = nuke.Double_Knob("start_dist", "Fog Start Distance")
        k_start.setValue(0.0)
        k_start.setRange(0.0, 1000.0)
        group.addKnob(k_start)
        
        k_max = nuke.Double_Knob("max_opacity", "Max Fog Opacity")
        k_max.setValue(1.0)
        k_max.setRange(0.0, 1.0)
        group.addKnob(k_max)
        
        k_color = nuke.Color_Knob("fog_color", "Fog Color")
        k_color.setValue([0.5, 0.6, 0.7])
        group.addKnob(k_color)
        
        # Add toggle to control if depth=0 (sky) receives maximum fog
        k_sky = nuke.Boolean_Knob("fog_sky", "Apply Fog to Sky (Depth=0)")
        k_sky.setValue(True)
        k_sky.setFlag(nuke.STARTLINE)
        group.addKnob(k_sky)
        
        # Link the internal Copy node's from0 knob to the Group UI
        k_depth = nuke.Link_Knob("depth_channel", "Depth Channel")
        k_depth.makeLink(copy_depth.name(), "from0")
        group.addKnob(k_depth)
        
        # Auto-detect default channel
        detected = "depth.Z"
        if source_node:
            for c in source_node.channels():
                if "extra_depth" in c or "depth_extra" in c:
                    detected = c
                    break
            if detected == "depth.Z":
                if "depth.Z" not in source_node.channels() and "depth.z" in source_node.channels():
                    detected = "depth.z"

        # Apply default
        group['depth_channel'].setValue(detected)

    return group

def create_normals_relighter(source_node):
    """Builds an interactive 2D relighting rig using the Normals (N) AOV."""
    if not source_node:
        nuke.message("Select a node with a Normals (N) channel.")
        return
        
    group = _create_integration_group("Crucible_NormalsRelight", "Interactive 2D Relighting via Normals")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        k_tab = nuke.Tab_Knob("Crucible", "Relighting")
        group.addKnob(k_tab)
        
        k_normals = nuke.Channel_Knob("normals_channel", "Normals Channel")
        k_normals.setValue("N")
        group.addKnob(k_normals)
        
        k_pos = nuke.XY_Knob("light_pos", "Light Direction (XY)")
        k_pos.setValue([1000, 1000])
        group.addKnob(k_pos)
        
        k_z = nuke.Double_Knob("light_z", "Light Z (Elevation)")
        k_z.setValue(500.0)
        k_z.setRange(-1000, 1000)
        group.addKnob(k_z)
        
        k_intensity = nuke.Double_Knob("intensity", "Light Intensity")
        k_intensity.setValue(1.0)
        k_intensity.setRange(0, 10)
        group.addKnob(k_intensity)
        
        k_color = nuke.Color_Knob("light_color", "Light Color")
        k_color.setValue([1.0, 1.0, 1.0])
        group.addKnob(k_color)
        
        # Auto-detect N channel
        detected_n_chan = "rgba.red"
        if source_node:
            for c in source_node.channels():
                if c.startswith("N.") or c.startswith("Normal.") or c.startswith("normals."):
                    detected_n_chan = c
                    break
        detected_n_layer = detected_n_chan.split('.')[0]

        expr = nuke.nodes.Expression(name="NormalsRelight", inputs=[input_node])
        expr['temp_name0'].setValue("Lx")
        expr['temp_expr0'].setValue("parent.light_pos.x - (width/2)")
        expr['temp_name1'].setValue("Ly")
        expr['temp_expr1'].setValue("parent.light_pos.y - (height/2)")
        expr['temp_name2'].setValue("Lz")
        expr['temp_expr2'].setValue("parent.light_z")
        expr['temp_name3'].setValue("Llen")
        expr['temp_expr3'].setValue("sqrt(Lx*Lx + Ly*Ly + Lz*Lz) + 0.00001")
        
        dot_expr = "((%s.x * (Lx/Llen)) + (%s.y * (Ly/Llen)) + (%s.z * (Lz/Llen)))" % (detected_n_layer, detected_n_layer, detected_n_layer)
        rgb_expr = "max(0, %s) * parent.intensity" % dot_expr
        
        expr['channel0'].setValue('rgba')
        expr['expr0'].setValue(rgb_expr)
        expr['expr1'].setValue('')
        expr['expr2'].setValue('')
        expr['expr3'].setValue('')
        
        # Multiply by Light Color
        mult = nuke.nodes.Multiply(inputs=[expr])
        mult['value'].setExpression("parent.light_color.r", 0)
        mult['value'].setExpression("parent.light_color.g", 1)
        mult['value'].setExpression("parent.light_color.b", 2)
        
        merge = nuke.nodes.Merge2(inputs=[input_node, mult], operation="plus", output="rgb")
        output = nuke.nodes.Output(inputs=[merge])

        group['normals_channel'].setValue(detected_n_chan)
        
        kc_n = """
k = nuke.thisKnob()
if k.name() == 'normals_channel':
    val = k.value()
    if val:
        layer = val.split('.')[0]
        e = nuke.toNode('NormalsRelight')
        if e:
            dot = '((%s.x * (Lx/Llen)) + (%s.y * (Ly/Llen)) + (%s.z * (Lz/Llen)))' % (layer,layer,layer)
            e['expr0'].setValue('max(0, %s) * parent.intensity' % dot)
"""
        group['knobChanged'].setValue(kc_n.strip())
        
    return group

def create_smart_lightwrap(fg_node):
    """Builds a Smart Edge Light Wrap engine."""
    if not fg_node:
        nuke.message("Select the Foreground element.")
        return
        
    group = _create_integration_group("Crucible_SmartLightwrap", "Smart Edge Light Wrap Engine")
    group.setInput(0, fg_node)
    
    with group:
        fg_in = nuke.nodes.Input(name="FG")
        bg_in = nuke.nodes.Input(name="BG")
        
        k_tab = nuke.Tab_Knob("Crucible", "Smart Wrap")
        group.addKnob(k_tab)
        
        k_size = nuke.Double_Knob("wrap_size", "Wrap Size")
        k_size.setValue(15.0)
        k_size.setRange(0, 100)
        group.addKnob(k_size)
        
        k_intensity = nuke.Double_Knob("intensity", "Wrap Intensity")
        k_intensity.setValue(1.0)
        k_intensity.setRange(0, 5)
        group.addKnob(k_intensity)
        
        erode = nuke.nodes.FilterErode(inputs=[fg_in])
        erode['channels'].setValue("rgba")
        erode['size'].setExpression("-parent.wrap_size")
        
        edge_matte = nuke.nodes.Merge2(inputs=[fg_in, erode], operation="stencil")
        
        edge_blur = nuke.nodes.Blur(inputs=[edge_matte])
        edge_blur['size'].setExpression("parent.wrap_size / 2.0")
        
        bg_blur = nuke.nodes.Blur(inputs=[bg_in])
        bg_blur['size'].setExpression("parent.wrap_size * 2.0")
        
        wrap_color = nuke.nodes.Merge2(inputs=[bg_blur, edge_blur], operation="mask")
        
        grade = nuke.nodes.Grade(inputs=[wrap_color])
        grade['multiply'].setExpression("parent.intensity")
        
        final_merge = nuke.nodes.Merge2(inputs=[fg_in, grade], operation="plus")
        
        output = nuke.nodes.Output(inputs=[final_merge])
        
    return group

def create_p_matte_relighter(source_node):
    """Builds a 3D spherical matte using the World Position (P) AOV for local relighting."""
    if not source_node:
        nuke.message("Select a node with a World Position (P) channel.")
        return
        
    group = _create_integration_group("Crucible_PMatte", "World Position Relighter")
    group.setInput(0, source_node)
    
    with group:
        input_node = nuke.nodes.Input(name="Input")
        
        k_tab = nuke.Tab_Knob("Crucible", "P-Matte Relight")
        group.addKnob(k_tab)
        
        k_pos = nuke.Channel_Knob("p_channel", "Position Channel")
        group.addKnob(k_pos)
        
        k_center = nuke.XYZ_Knob("center", "3D Center (XYZ)")
        group.addKnob(k_center)
        
        k_radius = nuke.Double_Knob("radius", "Radius")
        k_radius.setValue(100.0)
        k_radius.setRange(0, 1000)
        group.addKnob(k_radius)
        
        k_falloff = nuke.Double_Knob("falloff", "Falloff / Feather")
        k_falloff.setValue(1.0)
        k_falloff.setRange(0.1, 10)
        group.addKnob(k_falloff)
        
        k_color = nuke.Color_Knob("light_color", "Light Tint")
        k_color.setValue([1.0, 1.0, 1.0])
        group.addKnob(k_color)
        
        k_intensity = nuke.Double_Knob("intensity", "Intensity")
        k_intensity.setValue(1.0)
        k_intensity.setRange(0, 10)
        group.addKnob(k_intensity)
        
        expr = nuke.nodes.Expression(name="RelightMath", inputs=[input_node])
        
        # Auto-detect P channel and use .x/.y/.z (standard for non-color AOV layers)
        detected_chan = "rgba.red"
        if source_node:
            for c in source_node.channels():
                if c.startswith("P.") or "Pref." in c or "PWorld." in c or "world_P." in c:
                    detected_chan = c
                    break
                    
        detected_layer = detected_chan.split('.')[0]
        
        expr['temp_name0'].setValue("dist")
        dx = "(%s.x - parent.center.x)" % detected_layer
        dy = "(%s.y - parent.center.y)" % detected_layer
        dz = "(%s.z - parent.center.z)" % detected_layer
        expr['temp_expr0'].setValue("sqrt(%s*%s + %s*%s + %s*%s)" % (dx,dx, dy,dy, dz,dz))
        
        expr['temp_name1'].setValue("matte")
        expr['temp_expr1'].setValue("clamp(1.0 - (dist / (parent.radius + 0.0001)))")
        expr['temp_name2'].setValue("falloff_matte")
        expr['temp_expr2'].setValue("pow(matte, parent.falloff) * parent.intensity")
        
        expr['channel0'].setValue("rgba")
        expr['expr0'].setValue("falloff_matte")
        expr['expr1'].setValue("")
        expr['expr2'].setValue("")
        expr['expr3'].setValue("")
        
        mult = nuke.nodes.Multiply(inputs=[expr])
        mult['value'].setExpression("parent.light_color.r", 0)
        mult['value'].setExpression("parent.light_color.g", 1)
        mult['value'].setExpression("parent.light_color.b", 2)
        
        merge = nuke.nodes.Merge2(inputs=[input_node, mult], operation="plus", output="rgb")
        output = nuke.nodes.Output(inputs=[merge])
        
        group['p_channel'].setValue(detected_chan)
        
        kc_p = """
k = nuke.thisKnob()
if k.name() == 'p_channel':
    val = k.value()
    if val:
        layer = val.split('.')[0]
        e = nuke.toNode('RelightMath')
        if e:
            dx = '(%s.x - parent.center.x)' % layer
            dy = '(%s.y - parent.center.y)' % layer
            dz = '(%s.z - parent.center.z)' % layer
            e['temp_expr0'].setValue('sqrt(%s*%s + %s*%s + %s*%s)' % (dx,dx,dy,dy,dz,dz))
"""
        group['knobChanged'].setValue(kc_p.strip())
        
    return group

def create_true_shadow_catcher(source_node):
    """Builds a physically accurate Shadow and AO integrator."""
    if not source_node:
        nuke.message("Select a Shadow or AO AOV.")
        return
        
    group = _create_integration_group("Crucible_ShadowCatcher", "Physically Accurate Shadow Integrator")
    group.setInput(0, source_node)
    
    with group:
        shadow_in = nuke.nodes.Input(name="Shadow_AOV")
        plate_in  = nuke.nodes.Input(name="Plate_BG")
        
        k_tab = nuke.Tab_Knob("Crucible", "Shadow Catcher")
        group.addKnob(k_tab)
        

        k_invert = nuke.Boolean_Knob("invert_shadow", "Invert Shadow AOV")
        k_invert.setValue(False)
        group.addKnob(k_invert)
        
        k_color = nuke.Color_Knob("shadow_color", "Shadow Tint")
        k_color.setValue([0.2, 0.25, 0.3])
        group.addKnob(k_color)
        
        k_density = nuke.Double_Knob("density", "Shadow Density")
        k_density.setValue(1.0)
        k_density.setRange(0.0, 2.0)
        group.addKnob(k_density)
        
        # Copy selected shadow channel into alpha — use Link_Knob, not setExpression
        # (Copy node from0 does NOT accept Python expressions)
        copy_sh = nuke.nodes.Copy(inputs=[shadow_in, shadow_in])
        copy_sh['to0'].setValue("rgba.alpha")
        copy_sh['label'].setValue("Shadow -> Alpha")
        
        # Link the shadow_channel knob directly to the Copy node
        k_channel = nuke.Link_Knob("shadow_channel", "Shadow Channel")
        k_channel.makeLink(copy_sh.name(), "from0")
        group.addKnob(k_channel)
        # Invert and scale the shadow matte (alpha only)
        grade_sh = nuke.nodes.Grade(inputs=[copy_sh], channels="alpha")
        grade_sh['multiply'].setExpression("parent.density")
        grade_sh['invert'].setExpression("parent.invert_shadow")
        grade_sh['black_clamp'].setValue(True)
        grade_sh['white_clamp'].setValue(True)
        grade_sh['label'].setValue("Shadow Density")
        
        # Tint: darken the plate by the shadow color in the shadow areas
        # Merge2 'multiply' operation: A*B, masked by the shadow alpha
        shadow_tint = nuke.nodes.Grade(inputs=[plate_in])
        shadow_tint['multiply'].setExpression("parent.shadow_color.r", 0)
        shadow_tint['multiply'].setExpression("parent.shadow_color.g", 1)
        shadow_tint['multiply'].setExpression("parent.shadow_color.b", 2)
        shadow_tint['label'].setValue("Shadow Tint Color")
        
        # Keymix for per-pixel blend using the grade_sh alpha mask
        keymix = nuke.nodes.Keymix(inputs=[plate_in, shadow_tint, grade_sh])
        keymix['label'].setValue("Apply Shadow")
        
        output = nuke.nodes.Output(inputs=[keymix])
        
    return group

def create_3d_volume_matte(source_node):
    """Builds an advanced 3D matte generator using World Position (P) data for spherical/cubic masking that sticks to animated geometry."""
    if not source_node:
        nuke.message("Select a node with a World Position (P) channel.")
        return

    group = _create_integration_group("Crucible_3D_Volume_Matte", "Advanced 3D Position Matte Generator")
    group.setInput(0, source_node)

    # Detect channel BEFORE entering the group — channels() works on the real node here
    detected_chan = "P.x"
    for c in source_node.channels():
        if c.startswith("P.") or "Pref." in c or "PWorld." in c or "world_P." in c:
            detected_chan = c
            break
    detected_layer = detected_chan.split('.')[0]

    with group:
        input_node = nuke.nodes.Input(name="Input")

        expr = nuke.nodes.Expression(name="VolumeMath", inputs=[input_node])
        expr['temp_name0'].setValue("dx")
        expr['temp_expr0'].setValue("abs(%s.x - parent.center.x)" % detected_layer)
        expr['temp_name1'].setValue("dy")
        expr['temp_expr1'].setValue("abs(%s.y - parent.center.y)" % detected_layer)
        expr['temp_name2'].setValue("dz")
        expr['temp_expr2'].setValue("abs(%s.z - parent.center.z)" % detected_layer)
        expr['temp_name3'].setValue("dist")
        sphere_math = "(sqrt(dx*dx + dy*dy + dz*dz) / (parent.radius + 0.0001))"
        cube_math   = "max(dx/(parent.size.x/2.0+0.0001), max(dy/(parent.size.y/2.0+0.0001), dz/(parent.size.z/2.0+0.0001)))"
        expr['temp_expr3'].setValue("parent.shape==0 ? %s : %s" % (sphere_math, cube_math))
        expr['channel0'].setValue("rgba")
        expr['expr0'].setValue("pow(clamp(1.0 - dist), parent.falloff)")
        expr['channel1'].setValue("none")
        expr['channel2'].setValue("none")
        expr['channel3'].setValue("none")

        output = nuke.nodes.Output(inputs=[expr])

        k_tab = nuke.Tab_Knob("Crucible", "3D Matte")
        group.addKnob(k_tab)

        k_pos = nuke.Channel_Knob("p_channel", "Position Channel")
        group.addKnob(k_pos)

        k_shape = nuke.Enumeration_Knob("shape", "Mask Shape", ["Sphere (Circular)", "Cube (Rectangular)"])
        group.addKnob(k_shape)

        k_center = nuke.XYZ_Knob("center", "3D Center (XYZ)")
        group.addKnob(k_center)

        k_note = nuke.Text_Knob("note", "", "<i>Switch viewer to P pass, then Ctrl+Shift+Click on your target to sample its 3D coordinates.</i>")
        group.addKnob(k_note)

        k_radius = nuke.Double_Knob("radius", "Sphere Radius")
        k_radius.setValue(100.0)
        k_radius.setRange(0, 1000)
        group.addKnob(k_radius)

        k_size = nuke.XYZ_Knob("size", "Cube Size (XYZ)")
        k_size.setValue([100, 100, 100])
        group.addKnob(k_size)

        k_falloff = nuke.Double_Knob("falloff", "Edge Falloff / Softness")
        k_falloff.setValue(1.0)
        k_falloff.setRange(0.001, 5)
        group.addKnob(k_falloff)

        kc_script = """
k = nuke.thisKnob()
if k.name() == 'p_channel':
    val = k.value()
    if val:
        layer = val.split('.')[0]
        e = nuke.toNode('VolumeMath')
        if e:
            e['temp_expr0'].setValue("abs(%s.x - parent.center.x)" % layer)
            e['temp_expr1'].setValue("abs(%s.y - parent.center.y)" % layer)
            e['temp_expr2'].setValue("abs(%s.z - parent.center.z)" % layer)
"""
        group['knobChanged'].setValue(kc_script.strip())

    # setValue MUST be called after the with block — Nuke ignores it inside
    group['p_channel'].setValue(detected_chan)

    return group

