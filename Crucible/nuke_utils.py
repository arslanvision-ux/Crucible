"""
Crucible — Shared Nuke Utilities.

Helper functions for node creation, validation, and graph manipulation
used by both the AOV Builder and Render QC modules.
"""

import nuke


def get_selected_source_node():
    """Return the selected node if it has channels, or None with error.

    Accepts any node type (Read, Shuffle, Grade, Merge, etc.) as long
    as it carries channel data. This allows artists to run Crucible from
    any point in their node graph.

    Returns:
        nuke.Node or None: The selected source node.
    """
    selected = nuke.selectedNodes()
    if not selected:
        nuke.message("Crucible: Please select a node.")
        return None
    if len(selected) > 1:
        nuke.message("Crucible: Please select a single node.")
        return None

    node = selected[0]

    # Validate node has channel data
    try:
        channels = node.channels()
        if not channels:
            nuke.message(
                "Crucible: Selected node '{}' has no channels.\n"
                "Select a node with CG render data (e.g., Read, Shuffle, Merge).".format(
                    node.name()
                )
            )
            return None
    except Exception:
        nuke.message(
            "Crucible: Cannot read channels from '{}'.\n"
            "Select a node with CG render data.".format(node.name())
        )
        return None

    return node


# Backward-compatible alias
get_selected_read_node = get_selected_source_node


def get_channels_from_node(node):
    """Extract all channel names from a node.

    Args:
        node: A Nuke node to query channels from.

    Returns:
        list[str]: Sorted list of full channel names (e.g. 'diffuse.red').
    """
    if node is None:
        return []
    return sorted(node.channels())


def get_layers_from_channels(channels):
    """Group channels into layers.

    Args:
        channels: List of full channel names (e.g. 'diffuse.red').

    Returns:
        dict[str, list[str]]: Mapping of layer name to list of channel suffixes.
            e.g. {'diffuse': ['red', 'green', 'blue'], 'rgba': ['red', 'green', 'blue', 'alpha']}
    """
    layers = {}
    for ch in channels:
        parts = ch.split('.')
        if len(parts) == 2:
            layer_name, suffix = parts
        elif len(parts) == 1:
            # Root-level channel (rare), treat as 'other' layer
            layer_name = 'other'
            suffix = parts[0]
        else:
            # Multi-dot layer name (e.g. 'crypto_object.red')
            layer_name = '.'.join(parts[:-1])
            suffix = parts[-1]

        if layer_name not in layers:
            layers[layer_name] = []
        layers[layer_name].append(suffix)

    return layers


def create_shuffle(source_node, layer_name, label=None, layer_suffixes=None):
    """Create a Shuffle2 node to extract a specific layer.

    Sets in1 to the target layer and uses fromScript to map
    the layer's RGBA channels into the output RGBA. This approach
    is robust across Nuke 13+ versions.

    Args:
        source_node: The node to shuffle from.
        layer_name: The layer to extract (e.g. 'diffuse').
        label: Optional label for the node.
        layer_suffixes: Optional list of suffixes from ChannelLayer.

    Returns:
        nuke.Node: The created Shuffle2 node.
    """
    shuffle = nuke.nodes.Shuffle2(
        inputs=[source_node],
        label=label or layer_name,
    )
    shuffle['in1'].setValue(layer_name)

    if layer_suffixes is not None:
        layer_channels = ['{}.{}'.format(layer_name, s) for s in layer_suffixes]
    else:
        # Walk up the tree to find actual channel data (Dots return empty right after creation)
        eval_node = source_node
        channels = []
        for _ in range(10):  # Safe limit
            try:
                channels = eval_node.channels()
                if channels:
                    break
            except Exception:
                pass
                
            if eval_node.inputs() > 0 and eval_node.input(0):
                eval_node = eval_node.input(0)
            else:
                break
            
        layer_channels = [c for c in channels if c.startswith(layer_name + '.')]
    
    mappings = []
    
    if len(layer_channels) == 1:
        # Single channel pass (e.g., depth.Z or mask.a) -> Map to RGB for grayscale viewing
        single_chan = layer_channels[0]
        mappings.append((0, single_chan, 'rgba.red'))
        mappings.append((0, single_chan, 'rgba.green'))
        mappings.append((0, single_chan, 'rgba.blue'))
        
        # If it's an alpha mask, explicitly map to alpha as well
        if single_chan.endswith('.a') or single_chan.endswith('.alpha'):
            mappings.append((0, single_chan, 'rgba.alpha'))
    else:
        # Multi-channel pass (RGB, XYZ, UV, etc) -> Map only exactly what exists
        r_chan = next((c for c in layer_channels if c.endswith('.red') or c.endswith('.x') or c.endswith('.X') or c.endswith('.u')), None)
        if r_chan: mappings.append((0, r_chan, 'rgba.red'))
        
        g_chan = next((c for c in layer_channels if c.endswith('.green') or c.endswith('.y') or c.endswith('.Y') or c.endswith('.v')), None)
        if g_chan: mappings.append((0, g_chan, 'rgba.green'))
        
        b_chan = next((c for c in layer_channels if c.endswith('.blue') or c.endswith('.z') or c.endswith('.Z')), None)
        if b_chan: mappings.append((0, b_chan, 'rgba.blue'))
        
        a_chan = next((c for c in layer_channels if c.endswith('.alpha') or c.endswith('.a') or c.endswith('.w')), None)
        if a_chan: mappings.append((0, a_chan, 'rgba.alpha'))
    
    try:
        shuffle['mappings'].setValue(mappings)
    except Exception as e:
        print("Crucible: Failed to wire Shuffle2 channels - {}".format(e))

    shuffle['postage_stamp'].setValue(False)
    return shuffle


def create_dot(source_node):
    """Create a Dot node connected to the source.

    Args:
        source_node: The node to connect from.

    Returns:
        nuke.Node: The created Dot node.
    """
    dot = nuke.nodes.Dot(inputs=[source_node])
    return dot


def set_node_position(node, x, y):
    """Set a node's position in the DAG.

    Args:
        node: The Nuke node.
        x: X position.
        y: Y position.
    """
    node.setXYpos(int(x), int(y))


def get_node_center(node):
    """Get the center position of a node.

    Args:
        node: The Nuke node.

    Returns:
        tuple[int, int]: (x, y) center position.
    """
    return (
        node.xpos() + node.screenWidth() // 2,
        node.ypos() + node.screenHeight() // 2,
    )


def create_backdrop(nodes, label, color=None):
    """Create a backdrop node encompassing the given nodes.

    Args:
        nodes: List of nodes to enclose.
        label: Label text for the backdrop.
        color: Optional hex color string (e.g. '#1a1a2e').

    Returns:
        nuke.Node: The created BackdropNode.
    """
    if not nodes:
        return None

    # Calculate bounding box
    padding = 80
    min_x = min(n.xpos() for n in nodes) - padding
    min_y = min(n.ypos() for n in nodes) - padding - 40  # Extra for label
    max_x = max(n.xpos() + n.screenWidth() for n in nodes) + padding
    max_y = max(n.ypos() + n.screenHeight() for n in nodes) + padding

    backdrop = nuke.nodes.BackdropNode(
        xpos=min_x,
        bdwidth=max_x - min_x,
        ypos=min_y,
        bdheight=max_y - min_y,
        label='<center><b>{}</b></center>'.format(label),
        note_font_size=24,
    )

    if color:
        # Convert hex color to Nuke's tile_color integer
        hex_color = color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        tile_color = (r << 24) | (g << 16) | (b << 8) | 255
        backdrop['tile_color'].setValue(tile_color)

    return backdrop


def validate_node_exists(node_name):
    """Check if a node with the given name exists in the script.

    Args:
        node_name: Name of the node to find.

    Returns:
        nuke.Node or None: The node if found, else None.
    """
    try:
        return nuke.toNode(node_name)
    except Exception:
        return None
