"""
Crucible — Renderer Presets.

Maps renderer-specific AOV naming conventions to standardized AOVType
classifications. Supports Arnold, V-Ray, Redshift, Karma, and generic
fallback patterns for automatic renderer detection.
"""

from ..constants import AOVType, Renderer


# ---------------------------------------------------------------------------
# Arnold
# ---------------------------------------------------------------------------

ARNOLD_AOV_MAP = {
    'rgba': AOVType.BEAUTY,
    'beauty': AOVType.BEAUTY,
    'diffuse': AOVType.DIFFUSE,
    'diffuse_direct': AOVType.DIFFUSE_DIRECT,
    'diffuse_indirect': AOVType.DIFFUSE_INDIRECT,
    'diffuse_albedo': AOVType.DIFFUSE_FILTER,
    'specular': AOVType.SPECULAR,
    'specular_direct': AOVType.SPECULAR_DIRECT,
    'specular_indirect': AOVType.SPECULAR_INDIRECT,
    'sss': AOVType.SSS,
    'sss_direct': AOVType.SSS_DIRECT,
    'sss_indirect': AOVType.SSS_INDIRECT,
    'coat': AOVType.COAT,
    'coat_direct': AOVType.COAT_DIRECT,
    'coat_indirect': AOVType.COAT_INDIRECT,
    'sheen': AOVType.SHEEN,
    'sheen_direct': AOVType.SHEEN_DIRECT,
    'sheen_indirect': AOVType.SHEEN_INDIRECT,
    'emission': AOVType.EMISSION,
    'transmission': AOVType.TRANSMISSION,
    'transmission_direct': AOVType.TRANSMISSION_DIRECT,
    'transmission_indirect': AOVType.TRANSMISSION_INDIRECT,
    'volume': AOVType.VOLUME,
    'volume_direct': AOVType.VOLUME_DIRECT,
    'volume_indirect': AOVType.VOLUME_INDIRECT,
    'background': AOVType.BACKGROUND,
    'z': AOVType.DEPTH,
    'depth': AOVType.DEPTH,
    'zdepth': AOVType.DEPTH,
    'extra_depth': AOVType.DEPTH,
    'depth_extra': AOVType.DEPTH,
    'n': AOVType.NORMAL,
    'normal': AOVType.NORMAL,
    'p': AOVType.POSITION,
    'pworld': AOVType.POSITION,
    'position': AOVType.POSITION,
    'uv': AOVType.UV,
    'motionvector': AOVType.MOTION,
    'motion': AOVType.MOTION,
    'mv': AOVType.MOTION,
    'id': AOVType.OBJECT_ID,
    'ao': AOVType.AMBIENT_OCCLUSION,
    'occlusion': AOVType.AMBIENT_OCCLUSION,
    'shadow': AOVType.SHADOW,
    'shadow_matte': AOVType.SHADOW,
}

# Arnold light group naming: RGBA_<lightgroup_name>
ARNOLD_LIGHT_GROUP_PREFIX = 'rgba_'

# Fingerprint layers that strongly indicate Arnold
ARNOLD_FINGERPRINTS = {'diffuse_direct', 'diffuse_indirect', 'coat', 'sheen'}


# ---------------------------------------------------------------------------
# V-Ray
# ---------------------------------------------------------------------------

VRAY_AOV_MAP = {
    'rgba': AOVType.BEAUTY,
    'rgb': AOVType.BEAUTY,
    'vraylighting': AOVType.LIGHTING,
    'vraylightingraw': AOVType.LIGHTING,
    'vraydiffusefilter': AOVType.DIFFUSE_FILTER,
    'vrayglobalillumination': AOVType.GI,
    'vraygi': AOVType.GI,
    'vrayreflection': AOVType.REFLECTION,
    'vrayrefraction': AOVType.REFRACTION,
    'vrayspecular': AOVType.SPECULAR,
    'vraysss2': AOVType.SSS,
    'vrayselfillumination': AOVType.SELF_ILLUMINATION,
    'vraycaustics': AOVType.CAUSTICS,
    'vrayatmosphere': AOVType.ATMOSPHERE,
    'vraybackground': AOVType.BACKGROUND,
    'vraynormals': AOVType.NORMAL,
    'vrayzdepth': AOVType.DEPTH,
    'vrayvelocity': AOVType.MOTION,
    'vrayobjectid': AOVType.OBJECT_ID,
    'vraymaterialid': AOVType.MATERIAL_ID,
    'vrayshadows': AOVType.SHADOW,
}

VRAY_LIGHT_GROUP_PREFIX = 'vraylightselect'
VRAY_FINGERPRINTS = {'vraylighting', 'vrayglobalillumination', 'vrayreflection'}


# ---------------------------------------------------------------------------
# Redshift
# ---------------------------------------------------------------------------

REDSHIFT_AOV_MAP = {
    'rgba': AOVType.BEAUTY,
    'beautyaux': AOVType.BEAUTY,
    'diffusefilter': AOVType.DIFFUSE_FILTER,
    'diffuselighting': AOVType.DIFFUSE,
    'diffuselightingraw': AOVType.DIFFUSE,
    'specularlighting': AOVType.SPECULAR,
    'reflections': AOVType.REFLECTION,
    'refractions': AOVType.REFRACTION,
    'gilighting': AOVType.GI,
    'gi': AOVType.GI,
    'sss': AOVType.SSS,
    'subsurfacescatter': AOVType.SSS,
    'emission': AOVType.EMISSION,
    'caustics': AOVType.CAUSTICS,
    'volume': AOVType.VOLUME,
    'volumelighting': AOVType.VOLUME,
    'z': AOVType.DEPTH,
    'depth': AOVType.DEPTH,
    'zdepth': AOVType.DEPTH,
    'extra_depth': AOVType.DEPTH,
    'depth_extra': AOVType.DEPTH,
    'n': AOVType.NORMAL,
    'p': AOVType.POSITION,
    'puzzlematte': AOVType.OBJECT_ID,
    'motionvectors': AOVType.MOTION,
    'objectid': AOVType.OBJECT_ID,
    'ao': AOVType.AMBIENT_OCCLUSION,
    'shadows': AOVType.SHADOW,
}

REDSHIFT_LIGHT_GROUP_PREFIX = 'lightgroup'
# Expanded fingerprints: catch setups that only have light AOVs + standard RS passes
REDSHIFT_FINGERPRINTS = {
    'diffusefilter', 'diffuselighting', 'specularlighting',
    'diffuselightingraw', 'reflections', 'refractions', 'gilighting',
    'beautyaux', 'puzzlematte',
}

REDSHIFT_LG_COMPONENT_PREFIXES = frozenset([
    'diffuselighting', 'diffuselightingraw',
    'specularlighting',
    'reflections', 'refractions',
    'gilighting', 'gi',
    'sss', 'subsurfacescatter',
    'emission',
    'caustics',
    'volume', 'volumelighting',
    'shadows',
])


# ---------------------------------------------------------------------------
# Karma (Houdini/Solaris)
# ---------------------------------------------------------------------------

KARMA_AOV_MAP = {
    'c': AOVType.BEAUTY,
    'rgba': AOVType.BEAUTY,
    'direct_diffuse': AOVType.DIFFUSE_DIRECT,
    'indirect_diffuse': AOVType.DIFFUSE_INDIRECT,
    'direct_specular': AOVType.SPECULAR_DIRECT,
    'indirect_specular': AOVType.SPECULAR_INDIRECT,
    'direct_coat': AOVType.COAT_DIRECT,
    'indirect_coat': AOVType.COAT_INDIRECT,
    'sss': AOVType.SSS,
    'emission': AOVType.EMISSION,
    'direct_emission': AOVType.EMISSION,
    'diffuse_albedo': AOVType.DIFFUSE_FILTER,
    'n': AOVType.NORMAL,
    'p': AOVType.POSITION,
    'z': AOVType.DEPTH,
    'depth': AOVType.DEPTH,
    'zdepth': AOVType.DEPTH,
    'extra_depth': AOVType.DEPTH,
    'depth_extra': AOVType.DEPTH,
    'motionvector': AOVType.MOTION,
    'v': AOVType.MOTION,
    'ao': AOVType.AMBIENT_OCCLUSION,
    'uv': AOVType.UV,
}

KARMA_LIGHT_GROUP_PREFIX = 'lpe_'
KARMA_FINGERPRINTS = {'direct_diffuse', 'indirect_diffuse', 'direct_specular'}


# ---------------------------------------------------------------------------
# Cycles (Blender)
# ---------------------------------------------------------------------------

CYCLES_AOV_MAP = {
    'combined': AOVType.BEAUTY,
    'rgba': AOVType.BEAUTY,
    'diffcol': AOVType.DIFFUSE_FILTER,
    'diffdir': AOVType.DIFFUSE_DIRECT,
    'diffind': AOVType.DIFFUSE_INDIRECT,
    'glosscol': AOVType.SPECULAR,
    'glossdir': AOVType.SPECULAR_DIRECT,
    'glossind': AOVType.SPECULAR_INDIRECT,
    'transcol': AOVType.TRANSMISSION,
    'transdir': AOVType.TRANSMISSION_DIRECT,
    'transind': AOVType.TRANSMISSION_INDIRECT,
    'emit': AOVType.EMISSION,
    'env': AOVType.BACKGROUND,
    'volumedir': AOVType.VOLUME_DIRECT,
    'volumeind': AOVType.VOLUME_INDIRECT,
    'ao': AOVType.AMBIENT_OCCLUSION,
    'shadow': AOVType.SHADOW,
    'depth': AOVType.DEPTH,
    'z': AOVType.DEPTH,
    'normal': AOVType.NORMAL,
    'uv': AOVType.UV,
    'vector': AOVType.MOTION,
    'indexob': AOVType.OBJECT_ID,
    'indexma': AOVType.MATERIAL_ID,
    'cryptomatte': AOVType.CRYPTOMATTE,
}

CYCLES_LIGHT_GROUP_PREFIX = 'combined_'
CYCLES_FINGERPRINTS = {'combined', 'diffcol', 'diffdir', 'diffind', 'glossdir', 'glossind', 'transdir', 'emit', 'indexob', 'indexma'}


# ---------------------------------------------------------------------------
# Generic / Fallback
# ---------------------------------------------------------------------------

GENERIC_AOV_MAP = {
    'rgba': AOVType.BEAUTY,
    'rgb': AOVType.BEAUTY,
    'beauty': AOVType.BEAUTY,
    'combined': AOVType.BEAUTY,
    'diffuse': AOVType.DIFFUSE,
    'diff': AOVType.DIFFUSE,
    'specular': AOVType.SPECULAR,
    'spec': AOVType.SPECULAR,
    'reflection': AOVType.REFLECTION,
    'refl': AOVType.REFLECTION,
    'refraction': AOVType.REFRACTION,
    'refr': AOVType.REFRACTION,
    'sss': AOVType.SSS,
    'emission': AOVType.EMISSION,
    'coat': AOVType.COAT,
    'transmission': AOVType.TRANSMISSION,
    'volume': AOVType.VOLUME,
    'z': AOVType.DEPTH,
    'depth': AOVType.DEPTH,
    'zdepth': AOVType.DEPTH,
    'extra_depth': AOVType.DEPTH,
    'depth_extra': AOVType.DEPTH,
    'n': AOVType.NORMAL,
    'normal': AOVType.NORMAL,
    'p': AOVType.POSITION,
    'position': AOVType.POSITION,
    'uv': AOVType.UV,
    'motion': AOVType.MOTION,
    'mv': AOVType.MOTION,
    'velocity': AOVType.MOTION,
    'id': AOVType.OBJECT_ID,
    'ao': AOVType.AMBIENT_OCCLUSION,
    'shadow': AOVType.SHADOW,
    'gi': AOVType.GI,
    # C_ prefixed variants (common studio convention)
    'c_emission': AOVType.EMISSION,
    'c_diffuse': AOVType.DIFFUSE,
    'c_specular': AOVType.SPECULAR,
    'c_sss': AOVType.SSS,
    'c_coat': AOVType.COAT,
    'c_transmission': AOVType.TRANSMISSION,
    'c_volume': AOVType.VOLUME,
    'c_reflection': AOVType.REFLECTION,
    'c_refraction': AOVType.REFRACTION,
}


# ---------------------------------------------------------------------------
# Common Light Group Prefixes (tried as fallback for any renderer)
# ---------------------------------------------------------------------------

COMMON_LG_PREFIXES = [
    'rgba_',
    'c_light_',
    'light_',
    'lg_',
    'lightgroup_',
    'lightgroup',
    'lpe_c',
    'lpe_',
    'c_',
]


# ---------------------------------------------------------------------------
# Master Registry
# ---------------------------------------------------------------------------

RENDERER_PRESETS = {
    Renderer.ARNOLD: {
        'aov_map': ARNOLD_AOV_MAP,
        'light_group_prefix': ARNOLD_LIGHT_GROUP_PREFIX,
        'fingerprints': ARNOLD_FINGERPRINTS,
    },
    Renderer.VRAY: {
        'aov_map': VRAY_AOV_MAP,
        'light_group_prefix': VRAY_LIGHT_GROUP_PREFIX,
        'fingerprints': VRAY_FINGERPRINTS,
    },
    Renderer.REDSHIFT: {
        'aov_map': REDSHIFT_AOV_MAP,
        'light_group_prefix': REDSHIFT_LIGHT_GROUP_PREFIX,
        'fingerprints': REDSHIFT_FINGERPRINTS,
    },
    Renderer.KARMA: {
        'aov_map': KARMA_AOV_MAP,
        'light_group_prefix': KARMA_LIGHT_GROUP_PREFIX,
        'fingerprints': KARMA_FINGERPRINTS,
    },
    Renderer.CYCLES: {
        'aov_map': CYCLES_AOV_MAP,
        'light_group_prefix': CYCLES_LIGHT_GROUP_PREFIX,
        'fingerprints': CYCLES_FINGERPRINTS,
    },
    Renderer.GENERIC: {
        'aov_map': GENERIC_AOV_MAP,
        'light_group_prefix': 'light_',
        'fingerprints': set(),
    },
}


# ---------------------------------------------------------------------------
# V-Ray Additive Rebuild Order (component-based, not direct/indirect)
# ---------------------------------------------------------------------------

VRAY_REBUILD_ORDER = [
    AOVType.LIGHTING,
    AOVType.GI,
    AOVType.REFLECTION,
    AOVType.REFRACTION,
    AOVType.SPECULAR,
    AOVType.SSS,
    AOVType.SELF_ILLUMINATION,
    AOVType.CAUSTICS,
    AOVType.ATMOSPHERE,
]


def get_preset(renderer):
    """Return the preset dict for the given Renderer enum value."""
    return RENDERER_PRESETS.get(renderer, RENDERER_PRESETS[Renderer.GENERIC])
