"""
Crucible — Tree Builder.

Constructs the multi-pass AOV rebuild node tree in Nuke's DAG.
Supports additive reconstruction for Arnold, V-Ray, Redshift, and Karma,
with automatic direct/indirect merging and light group grade nodes.
"""

import nuke

from ..constants import (
    AOVType,
    AOVCategory,
    Renderer,
    ADDITIVE_REBUILD_ORDER,
    DIRECT_INDIRECT_PAIRS,
)
from .presets import VRAY_REBUILD_ORDER
from .channel_parser import ParsedChannels
from ..nuke_utils import (
    create_shuffle,
    create_dot,
    set_node_position,
    create_backdrop,
)


# ---------------------------------------------------------------------------
# Layout Constants
# ---------------------------------------------------------------------------

COL_WIDTH = 200       # Horizontal spacing between columns
ROW_HEIGHT = 100      # Vertical spacing between rows
MERGE_OFFSET_Y = 60   # Vertical offset for merge nodes below shuffles
LG_COL_WIDTH = 180    # Light group column width


# ---------------------------------------------------------------------------
# Tree Builder
# ---------------------------------------------------------------------------

class AOVTreeBuilder:
    """Builds the multi-pass reconstruction tree in Nuke's node graph.

    This creates:
    1. Shuffle2 nodes for each AOV
    2. Additive Merge tree for beauty reconstruction
    3. Grade nodes for each light group with controllable intensity/tint
    4. Clean layout with backdrops

    Attributes:
        parsed: The ParsedChannels result from channel_parser.
        source_node: The Read node being processed.
        grade_nodes: Dict mapping light group names to their Grade nodes.
    """

    def __init__(self, parsed, source_node):
        """Initialize the tree builder.

        Args:
            parsed: ParsedChannels object from channel_parser.parse_channels().
            source_node: The source Read node in Nuke.
        """
        self.parsed = parsed
        self.source_node = source_node
        self.grade_nodes = {}
        self._all_created_nodes = []
        self._start_x = source_node.xpos()
        self._start_y = source_node.ypos() + 200

    def build(self):
        """Build the complete AOV reconstruction tree.

        Returns:
            dict: Result info containing:
                - 'grade_nodes': dict of light_group_name → Grade node
                - 'rebuild_output': The final Merge node of the rebuild
                - 'lg_output': The final Merge node of the light group rebuild
                - 'all_nodes': list of all created nodes
        """
        result = {
            'grade_nodes': {},
            'rebuild_output': None,
            'lg_output': None,
            'all_nodes': [],
        }

        with nuke.Undo('Crucible: Build Light Mixer Tree'):
            # --- Base AOV Rebuild (Global passes) ---
            if self.parsed.shading_layers:
                rebuild_output, rebuild_nodes = self._build_aov_rebuild()
                result['rebuild_output'] = rebuild_output
                result['all_nodes'].extend(rebuild_nodes)

            # --- Light Group Mixer ---
            if self.parsed.light_group_layers:
                lg_output, lg_nodes, grade_nodes = self._build_light_group_mixer()
                result['lg_output'] = lg_output
                result['grade_nodes'] = grade_nodes
                result['all_nodes'].extend(lg_nodes)
                self.grade_nodes = grade_nodes

            # --- Master Merge (Combine Light Groups with Global Passes) ---
            final_output = None
            if result['rebuild_output'] and result['lg_output']:
                master_merge = nuke.nodes.Merge2(
                    inputs=[result['rebuild_output'], result['lg_output']],
                    operation='plus',
                    label='Master Build',
                )
                
                # Position it cleanly below everything
                lg_x = result['lg_output'].xpos()
                lg_y = result['lg_output'].ypos()
                set_node_position(master_merge, lg_x, lg_y + 80)
                result['all_nodes'].append(master_merge)
                final_output = master_merge
            elif result['lg_output']:
                final_output = result['lg_output']
            elif result['rebuild_output']:
                final_output = result['rebuild_output']

            # --- Restore Original Alpha ---
            if final_output:
                alpha_copy = nuke.nodes.Copy(
                    inputs=[final_output, self.source_node],
                    from0='rgba.alpha',
                    to0='rgba.alpha',
                    label='Restore Alpha'
                )
                set_node_position(alpha_copy, final_output.xpos(), final_output.ypos() + 60)
                result['all_nodes'].append(alpha_copy)
                
            # --- Utility Passes ---
            # User requested not to build utility passes automatically
            # if self.parsed.utility_layers:
            #     util_nodes = self._build_utility_shuffles()
            #     result['all_nodes'].extend(util_nodes)

        return result

    # -----------------------------------------------------------------------
    # AOV Rebuild
    # -----------------------------------------------------------------------

    def _build_aov_rebuild(self):
        """Build the additive AOV reconstruction tree.

        Returns:
            tuple: (output_node, list_of_created_nodes)
        """
        nodes = []
        shading_layers = self.parsed.shading_layers
        renderer = self.parsed.renderer

        # Determine rebuild order based on renderer
        if renderer == Renderer.VRAY:
            rebuild_order = VRAY_REBUILD_ORDER
        else:
            rebuild_order = ADDITIVE_REBUILD_ORDER

        # Create a Dot from the source for clean routing
        dot = create_dot(self.source_node)
        set_node_position(dot, self._start_x + 34, self._start_y)
        nodes.append(dot)

        # Map AOV types to their layers for quick lookup
        type_to_layer = {}
        for layer in shading_layers:
            type_to_layer[layer.aov_type] = layer

        # Collect AOV types that are already handled by light groups
        # This prevents double-adding global passes (like DiffuseLighting) when they
        # are already being fully rebuilt by the Light Mixer block.
        from .channel_parser import _classify_layer
        lg_aov_types = set()
        for layer in self.parsed.light_group_layers:
            # Re-classify the layer name without its light group suffix to find its base AOVType
            # e.g., 'diffuselighting_Key' -> 'diffuselighting' -> AOVType.DIFFUSE
            lg_name = layer.light_group
            if lg_name and layer.name.endswith(f"_{lg_name}"):
                base_name = layer.name[:-len(f"_{lg_name}")]
                base_type = _classify_layer(base_name, renderer)
                lg_aov_types.add(base_type)

        if AOVType.BEAUTY in lg_aov_types or renderer == Renderer.CYCLES:
            # The light groups represent the full beauty pass (e.g. Cycles Combined).
            # Building global shading layers and merging them would double the lighting.
            return None, []

        # Build shuffles and merges in order
        col_idx = 0
        merge_chain = None
        shuffle_nodes = []

        for aov_type in rebuild_order:
            # Skip this pass if the user explicitly broke it out into light groups
            if aov_type in lg_aov_types:
                continue
                
            layer = type_to_layer.get(aov_type)
            if layer is None:
                # Check for direct/indirect pair
                if self.parsed.has_direct_indirect and aov_type in DIRECT_INDIRECT_PAIRS:
                    direct_type, indirect_type = DIRECT_INDIRECT_PAIRS[aov_type]
                    direct_layer = type_to_layer.get(direct_type)
                    indirect_layer = type_to_layer.get(indirect_type)

                    if direct_layer or indirect_layer:
                        x_pos = self._start_x + (col_idx + 1) * COL_WIDTH
                        y_pos = self._start_y + ROW_HEIGHT

                        combined_node, sub_nodes = self._build_direct_indirect_pair(
                            dot, direct_layer, indirect_layer,
                            aov_type.name, x_pos, y_pos
                        )
                        nodes.extend(sub_nodes)
                        shuffle_nodes.append(combined_node)

                        merge_chain = self._merge_into_chain(
                            merge_chain, combined_node, col_idx, nodes
                        )
                        col_idx += 1
                continue

            # Single-layer shuffle
            x_pos = self._start_x + (col_idx + 1) * COL_WIDTH
            y_pos = self._start_y + ROW_HEIGHT

            shuffle = create_shuffle(dot, layer.name, label=layer.name.upper(), layer_suffixes=layer.suffixes)
            set_node_position(shuffle, x_pos, y_pos)
            nodes.append(shuffle)
            shuffle_nodes.append(shuffle)

            merge_chain = self._merge_into_chain(
                merge_chain, shuffle, col_idx, nodes
            )
            col_idx += 1

        # Also handle any shading layers not in the standard order
        handled_types = set(rebuild_order)
        for pair_types in DIRECT_INDIRECT_PAIRS.values():
            handled_types.update(pair_types)

        for layer in shading_layers:
            if layer.aov_type not in handled_types:
                x_pos = self._start_x + (col_idx + 1) * COL_WIDTH
                y_pos = self._start_y + ROW_HEIGHT

                shuffle = create_shuffle(dot, layer.name, label=layer.name, layer_suffixes=layer.suffixes)
                set_node_position(shuffle, x_pos, y_pos)
                nodes.append(shuffle)
                shuffle_nodes.append(shuffle)

                merge_chain = self._merge_into_chain(
                    merge_chain, shuffle, col_idx, nodes
                )
                col_idx += 1

        # Create backdrop for the AOV rebuild section
        if nodes:
            create_backdrop(nodes, 'AOV REBUILD', '#2d3436')

        return merge_chain, nodes

    def _build_direct_indirect_pair(self, source, direct_layer, indirect_layer,
                                     label, x_pos, y_pos):
        """Build a direct + indirect merge pair.

        Args:
            source: Source Dot node.
            direct_layer: ChannelLayer for direct component (or None).
            indirect_layer: ChannelLayer for indirect component (or None).
            label: Label for the combined result.
            x_pos: X position in DAG.
            y_pos: Y position in DAG.

        Returns:
            tuple: (output_node, list_of_nodes)
        """
        nodes = []
        sub_x = x_pos - 80

        if direct_layer and indirect_layer:
            # Shuffle both and merge (plus)
            shuf_direct = create_shuffle(source, direct_layer.name,
                                         label='{} DIRECT'.format(label), layer_suffixes=direct_layer.suffixes)
            set_node_position(shuf_direct, sub_x, y_pos)
            nodes.append(shuf_direct)

            shuf_indirect = create_shuffle(source, indirect_layer.name,
                                           label='{} INDIRECT'.format(label), layer_suffixes=indirect_layer.suffixes)
            set_node_position(shuf_indirect, sub_x + 160, y_pos)
            nodes.append(shuf_indirect)

            merge = nuke.nodes.Merge2(
                inputs=[shuf_direct, shuf_indirect],
                operation='plus',
                label=label,
            )
            set_node_position(merge, sub_x + 80, y_pos + MERGE_OFFSET_Y)
            nodes.append(merge)

            return merge, nodes

        elif direct_layer:
            shuf = create_shuffle(source, direct_layer.name,
                                  label='{} DIRECT'.format(label), layer_suffixes=direct_layer.suffixes)
            set_node_position(shuf, x_pos, y_pos)
            nodes.append(shuf)
            return shuf, nodes

        else:
            shuf = create_shuffle(source, indirect_layer.name,
                                  label='{} INDIRECT'.format(label), layer_suffixes=indirect_layer.suffixes)
            set_node_position(shuf, x_pos, y_pos)
            nodes.append(shuf)
            return shuf, nodes

    def _merge_into_chain(self, current_chain, new_node, col_idx, nodes):
        """Merge a new node into the running merge chain.

        Args:
            current_chain: The current output of the chain (or None for first).
            new_node: The new node to merge in.
            col_idx: Column index for positioning.
            nodes: List to append created nodes to.

        Returns:
            nuke.Node: The new chain output.
        """
        if current_chain is None:
            return new_node

        merge = nuke.nodes.Merge2(
            inputs=[current_chain, new_node],
            operation='plus',
            label='rebuild',
        )
        merge_y = self._start_y + ROW_HEIGHT + MERGE_OFFSET_Y * 2
        merge_x = self._start_x + (col_idx + 1) * COL_WIDTH
        set_node_position(merge, merge_x, merge_y)
        nodes.append(merge)
        return merge

    # -----------------------------------------------------------------------
    # Light Group Mixer
    # -----------------------------------------------------------------------

    def _build_light_group_mixer(self):
        """Build the light group mixer tree with Grade nodes.

        Returns:
            tuple: (output_node, list_of_nodes, dict_of_grade_nodes)
        """
        nodes = []
        grade_nodes = {}
        lg_layers = self.parsed.light_group_layers

        # Group layers by light group name
        grouped_lgs = {}
        for layer in lg_layers:
            group_name = layer.light_group or layer.name
            if group_name not in grouped_lgs:
                grouped_lgs[group_name] = []
            grouped_lgs[group_name].append(layer)

        # Position light groups to the right of the AOV rebuild
        num_shading = len(self.parsed.shading_layers) + 2
        lg_start_x = self._start_x + num_shading * COL_WIDTH + COL_WIDTH
        lg_y = self._start_y + ROW_HEIGHT

        # Source dot for light groups
        dot = create_dot(self.source_node)
        set_node_position(dot, lg_start_x + 34, self._start_y)
        nodes.append(dot)

        merge_chain = None

        for idx, (group_name, layers) in enumerate(grouped_lgs.items()):
            x_pos = lg_start_x + idx * LG_COL_WIDTH

            sum_node = None
            current_y = lg_y
            
            # Shuffle out and sum all layers for this light group
            for layer in layers:
                shuffle = create_shuffle(dot, layer.name,
                                         label=layer.name, layer_suffixes=layer.suffixes)
                set_node_position(shuffle, x_pos, current_y)
                nodes.append(shuffle)
                
                if sum_node is None:
                    sum_node = shuffle
                else:
                    merge_sum = nuke.nodes.Merge2(
                        inputs=[sum_node, shuffle],
                        operation='plus',
                        label='+',
                    )
                    current_y += 40
                    set_node_position(merge_sum, x_pos, current_y)
                    nodes.append(merge_sum)
                    sum_node = merge_sum
                current_y += 40

            # Grade node for intensity/tint control
            grade = nuke.nodes.Grade(
                inputs=[sum_node],
                name='crucible_lg_{}'.format(group_name.replace(' ', '_')),
                label='{}\n[value multiply]'.format(group_name),
            )
            
            # Add state knobs
            k_int = nuke.Double_Knob('lg_intensity', 'Intensity')
            k_int.setValue(1.0)
            k_col = nuke.Color_Knob('lg_color', 'Color')
            k_col.setValue([1.0, 1.0, 1.0])
            k_temp = nuke.Double_Knob('lg_temp', 'Temperature')
            k_temp.setRange(1000, 10000)
            k_temp.setValue(6500)
            k_tint = nuke.Double_Knob('lg_tint', 'Tint')
            k_tint.setRange(-1, 1)
            k_tint.setValue(0.0)
            k_sat = nuke.Double_Knob('lg_sat', 'Saturation')
            k_sat.setRange(0, 2)
            k_sat.setValue(1.0)
            
            for k in [k_int, k_col, k_temp, k_tint, k_sat]:
                grade.addKnob(k)
                
            grade['multiply'].setValue([1.0, 1.0, 1.0, 1.0])
            grade['black_clamp'].setValue(False)
            grade['note_font_size'].setValue(14)
            set_node_position(grade, x_pos, current_y + 40)
            nodes.append(grade)
            
            # Saturation node for desaturating the AOV
            sat = nuke.nodes.Saturation(
                inputs=[grade],
                name='crucible_sat_{}'.format(group_name.replace(' ', '_')),
                label='Sat: [value saturation]'
            )
            # Link saturation to the custom knob on the Grade node
            sat['saturation'].setExpression("{}.lg_sat".format(grade.name()))
            set_node_position(sat, x_pos, current_y + 80)
            nodes.append(sat)

            # Store grade node reference
            grade_nodes[group_name] = grade

            # Merge into chain
            if merge_chain is None:
                merge_chain = sat
            else:
                merge = nuke.nodes.Merge2(
                    inputs=[merge_chain, sat],
                    operation='plus',
                    label='LG Mix',
                )
                set_node_position(merge, x_pos, current_y + 120)
                nodes.append(merge)
                merge_chain = merge

        # Backdrop for light groups
        if nodes:
            create_backdrop(nodes, 'LIGHT GROUPS', '#2d3436')

        return merge_chain, nodes, grade_nodes

    # -----------------------------------------------------------------------
    # Utility Shuffles
    # -----------------------------------------------------------------------

    def _build_utility_shuffles(self):
        """Shuffle out utility passes (depth, normal, motion, etc.) and generate a Contact Sheet.

        Returns:
            list: Created nodes.
        """
        nodes = []
        shuffles = []

        # Position below the main rebuild
        util_y = self._start_y + ROW_HEIGHT * 4
        util_x = self._start_x

        dot = create_dot(self.source_node)
        set_node_position(dot, util_x + 34, util_y)
        nodes.append(dot)

        for idx, layer in enumerate(self.parsed.utility_layers):
            x_pos = util_x + (idx + 1) * COL_WIDTH

            shuffle = create_shuffle(dot, layer.name, label=layer.name.upper(), layer_suffixes=layer.suffixes)
            set_node_position(shuffle, x_pos, util_y + ROW_HEIGHT)
            nodes.append(shuffle)
            shuffles.append(shuffle)
            
        if shuffles:
            import math
            num_inputs = len(shuffles)
            cols = int(math.ceil(math.sqrt(num_inputs)))
            rows = int(math.ceil(num_inputs / float(cols)))
            
            contact = nuke.nodes.ContactSheet(inputs=shuffles)
            contact['width'].setExpression("input.width * {}".format(cols))
            contact['height'].setExpression("input.height * {}".format(rows))
            contact['rows'].setValue(rows)
            contact['columns'].setValue(cols)
            contact['roworder'].setValue("TopBottom")
            
            # Position the contact sheet underneath the center of the shuffles
            mid_idx = num_inputs // 2
            contact_x = util_x + (mid_idx + 1) * COL_WIDTH
            contact_y = util_y + int(ROW_HEIGHT * 2.5)
            set_node_position(contact, contact_x, contact_y)
            nodes.append(contact)

        if nodes:
            create_backdrop(nodes, 'UTILITY PASSES', '#636e72')

        return nodes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_aov_tree(parsed, source_node):
    """Build the complete AOV tree from parsed channels.

    This is the main entry point for tree construction.

    Args:
        parsed: ParsedChannels from channel_parser.parse_channels().
        source_node: The source Read node.

    Returns:
        dict: Build result containing grade_nodes, outputs, and node lists.
    """
    builder = AOVTreeBuilder(parsed, source_node)
    return builder.build()
