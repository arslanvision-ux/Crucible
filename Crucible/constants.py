"""
Crucible — Constants and Enumerations.

Defines AOV types, channel classifications, renderer identifiers,
QC thresholds, and UI color constants used across the toolkit.
"""

from enum import Enum, auto


# ---------------------------------------------------------------------------
# AOV Classification
# ---------------------------------------------------------------------------

class AOVType(Enum):
    """Classification of AOV/render pass types."""
    BEAUTY = auto()
    DIFFUSE = auto()
    DIFFUSE_DIRECT = auto()
    DIFFUSE_INDIRECT = auto()
    DIFFUSE_FILTER = auto()
    SPECULAR = auto()
    SPECULAR_DIRECT = auto()
    SPECULAR_INDIRECT = auto()
    SSS = auto()
    SSS_DIRECT = auto()
    SSS_INDIRECT = auto()
    EMISSION = auto()
    TRANSMISSION = auto()
    TRANSMISSION_DIRECT = auto()
    TRANSMISSION_INDIRECT = auto()
    COAT = auto()
    COAT_DIRECT = auto()
    COAT_INDIRECT = auto()
    SHEEN = auto()
    SHEEN_DIRECT = auto()
    SHEEN_INDIRECT = auto()
    VOLUME = auto()
    VOLUME_DIRECT = auto()
    VOLUME_INDIRECT = auto()
    REFLECTION = auto()
    REFRACTION = auto()
    GI = auto()
    LIGHTING = auto()
    SELF_ILLUMINATION = auto()
    CAUSTICS = auto()
    ATMOSPHERE = auto()
    BACKGROUND = auto()
    # Utility
    DEPTH = auto()
    NORMAL = auto()
    POSITION = auto()
    UV = auto()
    MOTION = auto()
    OBJECT_ID = auto()
    MATERIAL_ID = auto()
    CRYPTOMATTE = auto()
    AMBIENT_OCCLUSION = auto()
    SHADOW = auto()
    FRESNEL = auto()
    # Light groups
    LIGHT_GROUP = auto()
    # Fallbacks
    CUSTOM = auto()
    UNKNOWN = auto()


class AOVCategory(Enum):
    """High-level categories for AOV organization."""
    BEAUTY = auto()
    SHADING = auto()
    UTILITY = auto()
    MATTE = auto()
    LIGHT_GROUP = auto()
    CUSTOM = auto()


class Renderer(Enum):
    """Supported render engines."""
    ARNOLD = "arnold"
    VRAY = "vray"
    REDSHIFT = "redshift"
    RENDERMAN = "renderman"
    KARMA = "karma"
    OCTANE = "octane"
    CYCLES = "cycles"
    EEVEE = "eevee"
    GENERIC = "generic"


# ---------------------------------------------------------------------------
# AOV Categorization Helpers
# ---------------------------------------------------------------------------

# AOV types used in additive beauty reconstruction (in merge order)
ADDITIVE_REBUILD_ORDER = [
    AOVType.DIFFUSE,
    AOVType.GI,
    AOVType.SPECULAR,
    AOVType.REFLECTION,
    AOVType.REFRACTION,
    AOVType.CAUSTICS,
    AOVType.SSS,
    AOVType.COAT,
    AOVType.SHEEN,
    AOVType.TRANSMISSION,
    AOVType.EMISSION,
    AOVType.VOLUME,
]

# Direct/indirect component pairs for renderers that split them
DIRECT_INDIRECT_PAIRS = {
    AOVType.DIFFUSE: (AOVType.DIFFUSE_DIRECT, AOVType.DIFFUSE_INDIRECT),
    AOVType.SPECULAR: (AOVType.SPECULAR_DIRECT, AOVType.SPECULAR_INDIRECT),
    AOVType.SSS: (AOVType.SSS_DIRECT, AOVType.SSS_INDIRECT),
    AOVType.COAT: (AOVType.COAT_DIRECT, AOVType.COAT_INDIRECT),
    AOVType.SHEEN: (AOVType.SHEEN_DIRECT, AOVType.SHEEN_INDIRECT),
    AOVType.TRANSMISSION: (AOVType.TRANSMISSION_DIRECT, AOVType.TRANSMISSION_INDIRECT),
    AOVType.VOLUME: (AOVType.VOLUME_DIRECT, AOVType.VOLUME_INDIRECT),
}

# AOVs that should not have negative values in normal conditions
NON_NEGATIVE_AOVS = {
    AOVType.BEAUTY, AOVType.DIFFUSE, AOVType.SPECULAR,
    AOVType.SSS, AOVType.EMISSION, AOVType.DEPTH,
    AOVType.AMBIENT_OCCLUSION, AOVType.SHADOW,
}

# Utility-class AOV types (not used in additive rebuild)
UTILITY_AOV_TYPES = {
    AOVType.DEPTH, AOVType.NORMAL, AOVType.POSITION,
    AOVType.UV, AOVType.MOTION, AOVType.OBJECT_ID,
    AOVType.MATERIAL_ID, AOVType.CRYPTOMATTE,
    AOVType.AMBIENT_OCCLUSION, AOVType.SHADOW, AOVType.FRESNEL,
}

# Standard channel suffixes
RGBA_SUFFIXES = ('red', 'green', 'blue', 'alpha')
RGB_SUFFIXES = ('red', 'green', 'blue')

# ---------------------------------------------------------------------------
# QC Thresholds
# ---------------------------------------------------------------------------

FIREFLY_SIGMA_THRESHOLD = 6.0
NEGATIVE_VALUE_THRESHOLD = -0.001
MAX_REASONABLE_VALUE = 1000.0

# ---------------------------------------------------------------------------
# Light Mixer Defaults
# ---------------------------------------------------------------------------

LIGHT_MIXER_MIN = 0.0
LIGHT_MIXER_MAX = 100.0
LIGHT_MIXER_DEFAULT = 1.0

# ---------------------------------------------------------------------------
# UI Colors
# ---------------------------------------------------------------------------

UI_COLORS = {
    'bg_dark': '#1a1a2e',
    'bg_medium': '#16213e',
    'bg_light': '#0f3460',
    'accent': '#e94560',
    'accent_secondary': '#533483',
    'text': '#eaeaea',
    'text_dim': '#888888',
    'success': '#2ecc71',
    'warning': '#f39c12',
    'error': '#e74c3c',
    'info': '#3498db',
    'solo_active': '#f1c40f',
    'mute_active': '#e74c3c',
}
