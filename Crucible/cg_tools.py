import nuke

def extract_cryptomattes(source_node):
    """Detects Cryptomatte streams and extracts them automatically."""
    if not source_node:
        nuke.message("Select a CG render node.")
        return
        
    channels = source_node.channels()
    crypto_layers = set()
    
    # Identify Cryptomatte layers (they usually end in numbers or have standard names)
    for c in channels:
        if 'crypto' in c.lower() and ('.red' in c or '.00' in c):
            layer = c.split('.')[0]
            crypto_layers.add(layer)
            
    if not crypto_layers:
        nuke.message("No Cryptomatte data detected in this node.")
        return
        
    base_x = source_node.xpos()
    base_y = source_node.ypos() + 150
    
    for i, layer in enumerate(sorted(crypto_layers)):
        try:
            # Nuke 13+ native Cryptomatte node
            crypto_node = nuke.nodes.Cryptomatte(inputs=[source_node])
            crypto_node['cryptoLayer'].setValue(layer)
            crypto_node['label'].setValue(layer)
            crypto_node.setXYpos(base_x + (i * 120) - 100, base_y)
        except Exception as e:
            print(f"Crucible: Failed to create Cryptomatte for {layer} - {e}")
            
    nuke.message(f"Extracted {len(crypto_layers)} Cryptomatte layers!")


def setup_zdefocus(source_node):
    """Creates an Optical Z-Defocus Engine with edge-extension and unpremult/premult to avoid artifacts."""
    if not source_node:
        nuke.message("Select a CG render node.")
        return
        
    channels = source_node.channels()
    depth_layer = None
    
    # Common depth channel names (including Houdini Karma's depth_extra)
    for possible in ['depth_extra.Z', 'depth_extra.z', 'depth_extra', 'depth.Z', 'Z', 'depth.z', 'Z.z']:
        if possible in channels:
            depth_layer = possible
            break
            
    if not depth_layer:
        nuke.message("No Z-Depth channel found.")
        return
        
    x = source_node.xpos()
    y = source_node.ypos()
    
    # Unpremult for clean depth blurring
    unpremult = nuke.nodes.Unpremult(inputs=[source_node])
    unpremult.setXYpos(x, y + 50)
    
    # Edge extend trick to fix sharp CG edges before defocus
    edge_blur = nuke.nodes.Blur(inputs=[unpremult], size=3)
    edge_blur.setXYpos(x - 150, y + 50)
    
    edge_detect = nuke.nodes.EdgeDetectWrapper(inputs=[source_node], erodesize=0, blursize=6)
    edge_detect.setXYpos(x + 150, y + 50)
    
    keymix = nuke.nodes.Keymix(inputs=[unpremult, edge_blur, edge_detect])
    keymix.setXYpos(x, y + 100)
    
    # ZDefocus on the clean extended edges
    zdef = nuke.nodes.ZDefocus2(inputs=[keymix])
    zdef['math'].setValue('depth')
    zdef['z_channel'].setValue(depth_layer.split('.')[0])
    zdef['focal_point'].setValue([source_node.width()/2, source_node.height()/2])
    zdef['label'].setValue("Optical ZDefocus Engine\nPick focal_point in Viewer")
    zdef.setXYpos(x, y + 150)
    
    # Repremult
    premult = nuke.nodes.Premult(inputs=[zdef])
    premult.setXYpos(x, y + 200)
    
    # Show the control panel automatically
    zdef.showControlPanel()
    
    return premult

def create_crypto_grade(source_node):
    """Generates a Grade node pre-masked by a Cryptomatte isolation."""
    if not source_node:
        nuke.message("Select a CG render node with Cryptomatte.")
        return
        
    channels = source_node.channels()
    crypto_layer = None
    
    for c in channels:
        if 'crypto' in c.lower() and ('.red' in c or '.00' in c):
            crypto_layer = c.split('.')[0]
            break
            
    if not crypto_layer:
        nuke.message("No Cryptomatte data detected in this node.")
        return
        
    p = nuke.Panel("Crypto-Grade Generator")
    p.addSingleLineInput("Search String (e.g., *glass*)", "*")
    if not p.show():
        return
        
    search_str = p.value("Search String (e.g., *glass*)")
    
    x = source_node.xpos()
    y = source_node.ypos()
    
    # The Cryptomatte node
    crypto = nuke.nodes.Cryptomatte(inputs=[source_node])
    crypto['cryptoLayer'].setValue(crypto_layer)
    crypto['matteList'].setValue(search_str)
    crypto['label'].setValue(search_str)
    crypto.setXYpos(x + 150, y + 50)
    
    # The Grade node
    grade = nuke.nodes.Grade(inputs=[source_node, crypto])
    grade['label'].setValue(f"Crypto: {search_str}")
    grade.setXYpos(x, y + 100)
    
    return grade


def rebuild_beauty(source_node):
    """Reconstructs the Beauty pass from individual shader AOVs."""
    if not source_node:
        nuke.message("Select a CG render node.")
        return
        
    channels = source_node.channels()
    layers = list(set([c.split('.')[0] for c in channels]))
    
    # Standard shader AOV naming conventions across Arnold, V-Ray, Redshift
    beauty_keywords = ['diffuse', 'specular', 'coat', 'transmission', 'emission', 'sss', 'indirect', 'direct', 'refraction', 'reflection', 'volume']
    
    found_passes = []
    for l in layers:
        for kw in beauty_keywords:
            if kw in l.lower() and l not in found_passes:
                found_passes.append(l)
                
    if not found_passes:
        nuke.message("No standard Beauty AOVs found.")
        return
        
    base_x = source_node.xpos()
    base_y = source_node.ypos() + 150
    
    dot = nuke.nodes.Dot(inputs=[source_node])
    dot.setXYpos(base_x + 34, base_y)
    
    merge_chain = None
    
    for i, pass_name in enumerate(sorted(found_passes)):
        shuffle = nuke.nodes.Shuffle2(inputs=[dot], label=pass_name)
        shuffle['in1'].setValue(pass_name)
        
        mappings = [
            (0, f'{pass_name}.red', 'rgba.red'),
            (0, f'{pass_name}.green', 'rgba.green'),
            (0, f'{pass_name}.blue', 'rgba.blue')
        ]
        
        has_alpha = any(c == f'{pass_name}.alpha' or c == f'{pass_name}.a' for c in channels)
        if has_alpha:
            alpha_name = f'{pass_name}.alpha' if f'{pass_name}.alpha' in channels else f'{pass_name}.a'
            mappings.append((0, alpha_name, 'rgba.alpha'))
            
        try:
            shuffle['mappings'].setValue(mappings)
        except:
            pass
            
        shuffle['postage_stamp'].setValue(False)
        shuffle.setXYpos(base_x + (i * 150), base_y + 50)
        
        grade = nuke.nodes.Grade(inputs=[shuffle], label=pass_name)
        grade['black_clamp'].setValue(False) # Never clamp CG passes!
        grade.setXYpos(base_x + (i * 150), base_y + 100)
        
        if not merge_chain:
            merge_chain = grade
        else:
            merge_chain = nuke.nodes.Merge2(inputs=[merge_chain, grade], operation='plus', label='Beauty Build')
            merge_chain.setXYpos(base_x + (i * 150), base_y + 150)
            
    # Add a backdrop
    nuke.nodes.BackdropNode(
        xpos=base_x - 50,
        ypos=base_y - 20,
        bdwidth=(len(found_passes) * 150) + 50,
        bdheight=250,
        label="Beauty Reconstructor",
        note_font_size=20
    )
    
    return merge_chain

def smart_aov_wrangler(source_node):
    """Automatically extracts and organizes all AOVs from a multi-channel EXR into a color-coded tree."""
    if not source_node:
        nuke.message("Select a CG render node (EXR) to wrangle AOVs.")
        return
        
    channels = source_node.channels()
    layers = sorted(list(set([c.split('.')[0] for c in channels if c.split('.')[0] not in ['rgba', 'rgb', 'alpha']])))
    
    if not layers:
        nuke.message("No AOVs found in the selected node.")
        return
        
    base_x = source_node.xpos()
    base_y = source_node.ypos() + 100
    
    dot_spine = nuke.nodes.Dot(inputs=[source_node])
    dot_spine.setXYpos(base_x + 34, base_y)
    
    current_y = base_y + 50
    
    for i, layer in enumerate(layers):
        # Determine category and color for visual organization
        l_lower = layer.lower()
        color = 0x555555ff # Default gray
        
        if any(x in l_lower for x in ['diffuse', 'specular', 'reflection', 'refraction', 'emission', 'coat', 'sss', 'albedo', 'lighting', 'shadow']):
            color = 0x55aa55ff # Beauty passes - Green
        elif any(x in l_lower for x in ['crypto', 'id', 'mask']):
            color = 0xaaaa55ff # Utility/Crypto - Yellow
        elif any(x in l_lower for x in ['depth', 'z', 'p', 'n', 'uv', 'motion', 'velocity', 'normal']):
            color = 0x5555aaff # Data passes - Blue
            
        shuffle = nuke.nodes.Shuffle2(inputs=[dot_spine], label=layer)
        shuffle['in1'].setValue(layer)
        shuffle['tile_color'].setValue(color)
        
        # Dynamically map channels to handle .x, .y, .z or .red, .green, .blue
        layer_channels = [c for c in channels if c.startswith(layer + '.')]
        
        r_chan = next((c for c in layer_channels if c.endswith('.red') or c.endswith('.x') or c.endswith('.X')), None)
        g_chan = next((c for c in layer_channels if c.endswith('.green') or c.endswith('.y') or c.endswith('.Y')), None)
        b_chan = next((c for c in layer_channels if c.endswith('.blue') or c.endswith('.z') or c.endswith('.Z')), None)
        a_chan = next((c for c in layer_channels if c.endswith('.alpha') or c.endswith('.a') or c.endswith('.A') or c.endswith('.w')), None)
        
        ordered_chans = []
        for chan in [r_chan, g_chan, b_chan, a_chan]:
            if chan: ordered_chans.append(chan)
            
        # Fallback for unusually named channels
        for c in layer_channels:
            if c not in ordered_chans:
                ordered_chans.append(c)
                
        target_rgba = ['rgba.red', 'rgba.green', 'rgba.blue', 'rgba.alpha']
        mappings = []
        for j, c in enumerate(ordered_chans[:4]):
            mappings.append((0, c, target_rgba[j]))
            
        try:
            shuffle['mappings'].setValue(mappings)
        except Exception as e:
            print(f"Crucible: Failed to map channels for {layer} - {e}")
        
        # Stagger left and right for neatness along the dot spine
        offset = 150 if i % 2 == 0 else -150
        
        shuffle.setXYpos(base_x + offset, current_y)
        
        dot_spine = nuke.nodes.Dot(inputs=[dot_spine])
        dot_spine.setXYpos(base_x + 34, current_y + 34)
        current_y += 60
        
    # Group it all in a nice Backdrop
    nuke.nodes.BackdropNode(
        xpos=base_x - 180,
        ypos=base_y - 20,
        bdwidth=400,
        bdheight=(len(layers) * 60) + 100,
        label=f"AOV Wrangler: {source_node.name()}",
        note_font_size=20,
        tile_color=0x333333ff
    )
    
    nuke.message(f"Wrangled {len(layers)} AOVs successfully!")
