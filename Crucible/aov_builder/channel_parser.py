"""
Crucible — Channel Parser.

Parses EXR channel structures from Nuke Read nodes, auto-detects the
source renderer, classifies AOVs, and identifies light groups.
"""

from dataclasses import dataclass, field
from typing import Optional

from ..constants import (
    AOVType,
    AOVCategory,
    Renderer,
    UTILITY_AOV_TYPES,
    RGBA_SUFFIXES,
)
from .presets import RENDERER_PRESETS, get_preset
from ..nuke_utils import get_channels_from_node, get_layers_from_channels


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ChannelLayer:
    """Represents a single EXR channel layer with classification."""
    name: str
    suffixes: list = field(default_factory=list)
    aov_type: AOVType = AOVType.UNKNOWN
    category: AOVCategory = AOVCategory.CUSTOM
    light_group: Optional[str] = None
    is_rgba: bool = False

    @property
    def has_alpha(self):
        return 'alpha' in self.suffixes

    @property
    def has_rgb(self):
        return all(s in self.suffixes for s in ('red', 'green', 'blue'))

    @property
    def full_channel_names(self):
        """Return full channel names like ['diffuse.red', 'diffuse.green', ...]."""
        return ['{}.{}'.format(self.name, s) for s in self.suffixes]


@dataclass
class ParsedChannels:
    """Result of parsing a Read node's channel structure."""
    renderer: Renderer = Renderer.GENERIC
    all_layers: list = field(default_factory=list)
    beauty_layer: Optional[ChannelLayer] = None
    shading_layers: list = field(default_factory=list)
    utility_layers: list = field(default_factory=list)
    light_group_layers: list = field(default_factory=list)
    matte_layers: list = field(default_factory=list)
    custom_layers: list = field(default_factory=list)
    light_group_names: list = field(default_factory=list)
    has_direct_indirect: bool = False

    @property
    def total_layers(self):
        return len(self.all_layers)

    @property
    def total_light_groups(self):
        return len(self.light_group_names)


# ---------------------------------------------------------------------------
# Renderer Detection
# ---------------------------------------------------------------------------

def detect_renderer(layer_names):
    """Auto-detect the renderer based on layer naming conventions.

    Uses fingerprint matching — checks for layer names unique to each renderer.

    Args:
        layer_names: Set of lowercase layer names found in the EXR.

    Returns:
        Renderer: The detected renderer enum value.
    """
    lower_names = {n.lower() for n in layer_names}

    best_match = Renderer.GENERIC
    best_score = 0

    for renderer, preset in RENDERER_PRESETS.items():
        if renderer == Renderer.GENERIC:
            continue
        fingerprints = preset.get('fingerprints', set())
        score = len(fingerprints & lower_names) if fingerprints else 0
        
        # Award an extra point if a layer name strongly matches this renderer's light group prefix
        lg_prefix = preset.get('light_group_prefix', '')
        if lg_prefix and any(n.startswith(lg_prefix) and len(n) > len(lg_prefix) for n in lower_names):
            score += 1
            
        if score > best_score:
            best_score = score
            best_match = renderer

    return best_match


# ---------------------------------------------------------------------------
# Light Group Detection
# ---------------------------------------------------------------------------

def _extract_light_group_name(layer_name, prefix):
    """Extract light group name from a layer name given a prefix.

    Handles patterns like:
        - 'RGBA_key' with prefix 'rgba_' → 'key'
        - 'VRayLightSelect_rim' with prefix 'vraylightselect' → 'rim'
        - 'lightgroup_fill' with prefix 'lightgroup' → 'fill'

    Args:
        layer_name: The full layer name.
        prefix: The expected prefix (lowercase).

    Returns:
        str or None: The light group name, or None if not a light group.
    """
    lower_name = layer_name.lower()

    # Check for prefix with various separators
    for sep in ('_', '.', ''):
        full_prefix = prefix + sep if sep else prefix
        if lower_name.startswith(full_prefix) and len(lower_name) > len(full_prefix):
            group_name = layer_name[len(full_prefix):]
            # Strip a leading separator that may have been captured in no-sep case
            group_name = group_name.lstrip('_.')
            if not group_name:
                continue
            if group_name.lower() in (
                'direct', 'indirect', 'filter', 'raw', 'albedo',
                'diffuse', 'specular', 'sss', 'coat', 'sheen',
                'transmission', 'volume', 'reflection', 'refraction',
                'depth', 'motion', 'normal', 'position', 'uv', 'crypto',
                'gi', 'gilighting', 'lighting', 'emission', 'caustics', 'background'
            ):
                return None
            return group_name

    return None


def detect_light_groups(layer_names, renderer, prefix_override=None):
    """Detect light group layers from the channel list.

    Tries the renderer-specific prefix first, then falls back to
    a list of common light group prefixes used across studios
    (e.g., 'rgba_', 'c_light_', 'light_', 'lg_', 'lightgroup_').

    Args:
        layer_names: List of layer names.
        renderer: Detected Renderer enum.
        prefix_override: Optional forced string prefix to use for extraction.

    Returns:
        dict[str, str]: Mapping of layer_name → light_group_name.
    """
    from .presets import COMMON_LG_PREFIXES, REDSHIFT_LG_COMPONENT_PREFIXES
    from ..constants import Renderer

    light_groups = {}

    # 1. Specialized Redshift detector for postfix components (e.g. DiffuseLighting_Key)
    if renderer == Renderer.REDSHIFT:
        for layer_name in layer_names:
            lower_name = layer_name.lower()
            
            # Explicitly add global Emission to the light mixer
            if lower_name == 'emission':
                light_groups[layer_name] = 'Emission'
                continue
                
            for comp in REDSHIFT_LG_COMPONENT_PREFIXES:
                if lower_name.startswith(comp) and len(lower_name) > len(comp):
                    remainder = layer_name[len(comp):]
                    if remainder.startswith('_') or remainder.startswith('.'):
                        group_name = remainder.lstrip('_.')
                        if group_name:
                            light_groups[layer_name] = group_name
                            break

    # 2. General prefix-based detector for everything else (or fallback for RS)
    prefixes_to_try = []
    
    if prefix_override:
        prefixes_to_try.append(prefix_override)
    else:
        preset = get_preset(renderer)
        renderer_prefix = preset.get('light_group_prefix', '')
        if renderer_prefix:
            prefixes_to_try.append(renderer_prefix)
        # Always also try without trailing separator for renderers like Redshift
        if renderer_prefix and renderer_prefix.endswith('_'):
            prefixes_to_try.append(renderer_prefix.rstrip('_'))
        for p in COMMON_LG_PREFIXES:
            if p not in prefixes_to_try:
                prefixes_to_try.append(p)

    for layer_name in layer_names:
        if layer_name in light_groups:
            continue  # Already detected by specialized logic
        for prefix in prefixes_to_try:
            group_name = _extract_light_group_name(layer_name, prefix)
            if group_name:
                light_groups[layer_name] = group_name
                break  # First matching prefix wins

    return light_groups


# ---------------------------------------------------------------------------
# AOV Classification
# ---------------------------------------------------------------------------

def _classify_layer(layer_name, renderer):
    """Classify a single layer by matching against renderer presets.

    Args:
        layer_name: The layer name to classify.
        renderer: The Renderer enum for preset lookup.

    Returns:
        AOVType: The classified AOV type.
    """
    preset = get_preset(renderer)
    aov_map = preset['aov_map']

    lower_name = layer_name.lower()

    # Direct match
    if lower_name in aov_map:
        return aov_map[lower_name]

    # Try generic fallback if renderer-specific didn't match
    if renderer != Renderer.GENERIC:
        generic_map = RENDERER_PRESETS[Renderer.GENERIC]['aov_map']
        if lower_name in generic_map:
            return generic_map[lower_name]

    # Cryptomatte detection (special pattern: crypto_*)
    if lower_name.startswith('crypto'):
        return AOVType.CRYPTOMATTE

    return AOVType.UNKNOWN


def _categorize_aov(aov_type):
    """Assign a high-level category to an AOV type.

    Args:
        aov_type: The AOVType enum.

    Returns:
        AOVCategory: The category.
    """
    if aov_type == AOVType.BEAUTY:
        return AOVCategory.BEAUTY
    if aov_type in UTILITY_AOV_TYPES:
        return AOVCategory.UTILITY
    if aov_type == AOVType.LIGHT_GROUP:
        return AOVCategory.LIGHT_GROUP
    if aov_type in (AOVType.CRYPTOMATTE, AOVType.OBJECT_ID, AOVType.MATERIAL_ID):
        return AOVCategory.MATTE
    if aov_type in (AOVType.CUSTOM, AOVType.UNKNOWN):
        return AOVCategory.CUSTOM
    return AOVCategory.SHADING


# ---------------------------------------------------------------------------
# Main Parser
# ---------------------------------------------------------------------------

def parse_channels(node, prefix_override=None):
    """Parse channels from a Nuke node and return a structured result.

    This is the main entry point for channel analysis. It:
    1. Extracts all channels from the node
    2. Groups them into layers
    3. Auto-detects the source renderer
    4. Classifies each layer as an AOV type
    5. Detects light groups
    6. Organizes layers into categories

    Args:
        node: A Nuke node (typically a Read node) to parse.
        prefix_override: Optional forced string prefix to use for extraction.

    Returns:
        ParsedChannels: Complete parsed and classified channel structure.
    """
    channels = get_channels_from_node(node)
    if not channels:
        return ParsedChannels()

    layers_dict = get_layers_from_channels(channels)
    layer_names = set(layers_dict.keys())

    # Step 1: Detect renderer
    renderer = detect_renderer(layer_names)

    # Step 2: Detect light groups
    light_group_map = detect_light_groups(layer_names, renderer, prefix_override=prefix_override)

    # Step 3: Build ChannelLayer objects
    all_layers = []
    for layer_name, suffixes in sorted(layers_dict.items()):
        layer = ChannelLayer(
            name=layer_name,
            suffixes=suffixes,
        )

        # Check if this is a light group
        if layer_name in light_group_map:
            layer.aov_type = AOVType.LIGHT_GROUP
            layer.category = AOVCategory.LIGHT_GROUP
            layer.light_group = light_group_map[layer_name]
        else:
            layer.aov_type = _classify_layer(layer_name, renderer)
            layer.category = _categorize_aov(layer.aov_type)

        layer.is_rgba = set(suffixes) == set(RGBA_SUFFIXES)
        all_layers.append(layer)

    # Step 4: Organize into result
    result = ParsedChannels(
        renderer=renderer,
        all_layers=all_layers,
    )

    # Check for direct/indirect split
    direct_indirect_types = {AOVType.DIFFUSE_DIRECT, AOVType.DIFFUSE_INDIRECT,
                             AOVType.SPECULAR_DIRECT, AOVType.SPECULAR_INDIRECT}
    found_types = {l.aov_type for l in all_layers}

    for layer in all_layers:
        if layer.category == AOVCategory.BEAUTY:
            result.beauty_layer = layer
        elif layer.category == AOVCategory.SHADING:
            result.shading_layers.append(layer)
        elif layer.category == AOVCategory.UTILITY:
            result.utility_layers.append(layer)
        elif layer.category == AOVCategory.LIGHT_GROUP:
            result.light_group_layers.append(layer)
            if layer.light_group and layer.light_group not in result.light_group_names:
                result.light_group_names.append(layer.light_group)
        elif layer.category == AOVCategory.MATTE:
            result.matte_layers.append(layer)
        else:
            result.custom_layers.append(layer)

    result.has_direct_indirect = bool(direct_indirect_types & found_types)

    return result
