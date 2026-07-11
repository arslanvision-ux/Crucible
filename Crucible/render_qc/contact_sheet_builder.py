import nuke
import math

def generate_aov_contact_sheet(source_node):
    """
    Scans a node for all available EXR layers/passes and builds a labeled ContactSheet.
    """
    if not source_node:
        nuke.message("Please select a Read or EXR node first.")
        return None
        
    channels = source_node.channels()
    layers = list(set([c.split('.')[0] for c in channels]))
    
    # Sort layers alphabetically, but force 'rgba' to the very front
    layers.sort()
    if 'rgba' in layers:
        layers.remove('rgba')
        layers.insert(0, 'rgba')
        
    if not layers:
        nuke.message("No multi-channel layers found in the selected node.")
        return None
        
    # Calculate optimal grid layout
    count = len(layers)
    cols = int(math.ceil(math.sqrt(count)))
    rows = int(math.ceil(count / float(cols)))
    
    try:
        width = source_node.format().width()
        height = source_node.format().height()
    except AttributeError:
        width = source_node.width() or 1920
        height = source_node.height() or 1080
    
    # Create the ContactSheet node
    cs_node = nuke.nodes.ContactSheet(
        width=width * cols,
        height=height * rows,
        rows=rows,
        columns=cols,
        roworder="TopBottom",
        label="AOV Contact Sheet"
    )
    
    # Position nodes cleanly in the DAG
    start_x = source_node.xpos() - (cols * 50)
    start_y = source_node.ypos() + 150
    
    cs_node.setXYpos(source_node.xpos(), start_y + 150)
    
    for i, layer in enumerate(layers):
        # Create Shuffle to isolate the layer
        shuffle = nuke.nodes.Shuffle2(inputs=[source_node], label=layer)
        shuffle['in1'].setValue(layer)
        
        # Wire the mappings to RGB
        mappings = [
            (0, f'{layer}.red', 'rgba.red'),
            (0, f'{layer}.green', 'rgba.green'),
            (0, f'{layer}.blue', 'rgba.blue')
        ]
        
        # Check if alpha exists in this layer
        has_alpha = any(c == f'{layer}.alpha' or c == f'{layer}.a' for c in channels)
        if has_alpha:
            alpha_name = f'{layer}.alpha' if f'{layer}.alpha' in channels else f'{layer}.a'
            mappings.append((0, alpha_name, 'rgba.alpha'))
        else:
            # If no alpha, set to solid white (1.0) so text renders correctly
            mappings.append((-1, 'none', 'rgba.alpha'))
            
        try:
            shuffle['mappings'].setValue(mappings)
        except Exception:
            pass
            
        # Unbreakable reformat to guarantee exact cell resolution and bbox padding
        reformat_aov = nuke.nodes.Reformat(inputs=[shuffle], type="to box", box_width=width, box_height=height, resize="fit", black_outside=True)
        reformat_aov.setXYpos(start_x + (i * 120), start_y)
        
        # A compositor trick: dropping a default Transform node forces Nuke to evaluate the black_outside filter, completely killing any lingering edge-stretch streaks.
        transform_aov = nuke.nodes.Transform(inputs=[reformat_aov], black_outside=True)
        transform_aov.setXYpos(start_x + (i * 120), start_y + 30)
        
        # Create a text overlay so the artist knows what pass they are looking at
        txt = nuke.nodes.Text2(inputs=[transform_aov])
        txt['message'].setValue(f"[ {layer.upper()} ]")
        
        # Nuke 13+ Text2 scaling and alignment
        txt['global_font_scale'].setValue(0.5)
        txt['box'].setValue([50, 50, width - 50, height - 100])
        txt['xjustify'].setValue("center")
        txt['yjustify'].setValue("bottom")
        
        # Add a sleek semi-transparent background to the text so it's readable over white AOVs
        txt['enable_background'].setValue(True)
        txt['background_color'].setValue([0, 0, 0, 0.7])
        txt['background_border_x'].setValue(20)
        txt['background_border_y'].setValue(20)
        
        txt.setXYpos(start_x + (i * 120), start_y + 50)
        
        # Hook it into the Contact Sheet
        cs_node.setInput(i, txt)
        
    return cs_node

def generate_fml_review_slate(source_node):
    """
    Builds an AppendClip review sequence:
    If sequence: 1:First, 2:Mid, 3:Last, 4:AOVs, 5:Meta
    If single frame: 1:Render, 2:AOVs, 3:Meta
    """
    if not source_node or source_node.Class() != 'Read':
        nuke.message("Please select a Read node to generate an FML Review Slate.")
        return
        
    first = int(source_node['first'].value())
    last = int(source_node['last'].value())
    is_single_frame = (first == last)
    
    try:
        fmt_w = source_node.format().width()
        fmt_h = source_node.format().height()
    except Exception:
        fmt_w = source_node.width()
        fmt_h = source_node.height()
        
    frames_to_extract = []
    
    if is_single_frame:
        frames_to_extract.append(first)
    else:
        # Prompt the user with a Nuke Panel
        p = nuke.Panel("FML Slate Settings")
        p.addEnumerationPulldown("Extraction Mode", "FML Every_Nth_Frame")
        p.addSingleLineInput("Nth Value", "10")
        
        if not p.show():
            return
            
        mode = p.value("Extraction Mode")
        try:
            val = int(p.value("Nth Value"))
        except (ValueError, TypeError):
            nuke.message("Please enter a valid integer for Value.")
            return
            
        if mode == "FML":
            middle = int((first + last) / 2)
            frames_to_extract = [first, middle, last]
        elif mode == "Every_Nth_Frame":
            val = max(1, val)
            frames_to_extract = list(range(first, last + 1, val))
            
    append_inputs = []
    
    # --- 1. Frame Holds ---
    for f in frames_to_extract:
        f_hold = nuke.nodes.FrameHold(inputs=[source_node], first_frame=f)
        f_range = nuke.nodes.FrameRange(inputs=[f_hold], first_frame=f, last_frame=f)
        append_inputs.append(f_range)
        
    representative_frame = frames_to_extract[len(frames_to_extract) // 2]
    
    # --- 2. Contact Sheet ---
    cs_node = generate_aov_contact_sheet(source_node)
    if not cs_node:
        return
    cs_hold = nuke.nodes.FrameHold(inputs=[cs_node], first_frame=representative_frame)
    
    # Create a pure black frame matching the source node format perfectly
    black_bg = nuke.nodes.Reformat(inputs=[source_node], type="to box", box_width=fmt_w, box_height=fmt_h, resize="none", black_outside=True)
    black_bg = nuke.nodes.Grade(inputs=[black_bg], multiply=0, add=0, black_clamp=False)
    
    # Scale contact sheet to box and merge over the exact format
    reformat_cs = nuke.nodes.Reformat(inputs=[cs_hold], type="to box", box_width=fmt_w, box_height=fmt_h, resize="fit", black_outside=True)
    
    # Add a default Transform node after the Reformat node to force Nuke's spatial filter and prevent edge stretching
    transform_cs = nuke.nodes.Transform(inputs=[reformat_cs], black_outside=True)
    
    merge_cs = nuke.nodes.Merge2(inputs=[black_bg, transform_cs], operation="over")
    
    cs_range = nuke.nodes.FrameRange(inputs=[merge_cs], first_frame=representative_frame, last_frame=representative_frame)
    append_inputs.append(cs_range)
    
    # --- 3. Metadata Slate ---
    meta = source_node.metadata()
    meta_lines = ["<b>=== EXR RENDER METADATA ===</b>\n"]
    
    for k, v in sorted(meta.items()):
        if 'manifest' in k.lower() or 'hash' in k.lower() or len(str(v)) > 150:
            continue
        meta_lines.append(f"{k}: {v}")
        
    meta_string = "\n".join(meta_lines)
    
    # Wire directly to black_bg to inherit the exact source format natively
    meta_txt = nuke.nodes.Text2(inputs=[black_bg])
    meta_txt['message'].setValue(meta_string)
    meta_txt['global_font_scale'].setValue(0.2)
    meta_txt['box'].setValue([50, 50, fmt_w - 50, fmt_h - 50])
    meta_txt['xjustify'].setValue("left")
    meta_txt['yjustify'].setValue("top")
    
    meta_hold = nuke.nodes.FrameHold(inputs=[meta_txt], first_frame=representative_frame)
    meta_range = nuke.nodes.FrameRange(inputs=[meta_hold], first_frame=representative_frame, last_frame=representative_frame)
    append_inputs.append(meta_range)
    
    # --- 4. AppendClip ---
    append = nuke.nodes.AppendClip(inputs=append_inputs)
    append['firstFrame'].setValue(first)
    
    num_frames = len(frames_to_extract) + 2
    
    if is_single_frame:
        append['label'].setValue("Review Sequence\n1:Render | 2:AOVs | 3:Meta")
        nuke.message("Single-Frame Review Sequence created!\n\nFrame 1: Render\nFrame 2: AOVs\nFrame 3: Metadata")
    else:
        append['label'].setValue(f"Review Sequence\n1-{len(frames_to_extract)}:Renders | {len(frames_to_extract)+1}:AOVs | {len(frames_to_extract)+2}:Meta")
        nuke.message(f"Review Sequence created!\n\nFrames 1-{len(frames_to_extract)}: Renders\nFrame {len(frames_to_extract)+1}: AOVs\nFrame {num_frames}: Metadata")
        
    # Position nodes nicely
    base_x = source_node.xpos()
    base_y = source_node.ypos() + 400
    
    for idx, node in enumerate(append_inputs):
        node.setXYpos(base_x + (idx * 100) - 200, base_y)
        
    append.setXYpos(base_x, base_y + 100)

    # --- 5. Output Write Node ---
    import os
    import re
    
    script_path = nuke.root().name()
    if script_path and script_path != 'Root':
        script_dir = os.path.dirname(script_path)
        script_name = os.path.splitext(os.path.basename(script_path))[0]
    else:
        # Fallback if script is not saved
        script_dir = os.environ.get("NUKE_TEMP_DIR", os.path.expanduser("~"))
        script_name = "untitled_script"
        
    out_dir = os.path.join(script_dir, "OUT")
    if not os.path.exists(out_dir):
        try:
            os.makedirs(out_dir)
        except OSError as e:
            nuke.tprint(f"Failed to create OUT directory: {e}")
            
    base_filename = f"{script_name}_FML"
    max_v = 0
    if os.path.exists(out_dir):
        for f in os.listdir(out_dir):
            match = re.search(rf"{re.escape(base_filename)}_v(\d+)", f)
            if match:
                v = int(match.group(1))
                max_v = max(max_v, v)
                
    next_v = max_v + 1
    
    # AppendClip starts at frame 1 by default, requiring sequence padding
    file_path = os.path.join(out_dir, f"{base_filename}_v{next_v:03d}.%04d.exr").replace("\\", "/")
    
    write_node = nuke.nodes.Write(inputs=[append])
    write_node['file'].setValue(file_path)
    write_node['file_type'].setValue('exr')
    write_node['datatype'].setValue('16 bit half')
    write_node['compression'].setValue('Zip (1 scanline)')
    write_node['label'].setValue(f"v{next_v:03d}")
    
    # Set explicit frame range for the Write node to match the AppendClip length and start frame
    write_node['first'].setValue(first)
    write_node['last'].setValue(first + num_frames - 1)
    write_node['use_limit'].setValue(True)
    
    write_node.setXYpos(base_x, base_y + 200)

